"""Контроллер загрузки манги и авторизации на сайтах — для QML-диалогов."""

import os
import re
import json
import logging
import threading
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtWidgets import QFileDialog

from comx_downloader import ComXDownloadThread
from group_downloader import GroupDownloadThread, GROUP_DOMAINS
from mangahub_downloader import MangaHubDownloadThread
from mangalib_downloader import MangaLibDownloadThread
from app.ui.base import Bag, P

MANGALIB_DOMAINS = ("mangalib.me", "mangalib.org", "hentailib.me", "hentailib.org", "shlib.life", "slashlib.me")
SITES = ["MangaLib", "Com-X.life", "ReadManga/MintManga", "MangaHub.ru"]
DATA = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader'


def parse_cookie_file(raw):
    """[{"name","value"}] из JSON-списка (Cookie-Editor) или Netscape cookies.txt."""
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            cookies = [{"name": c["name"], "value": c["value"]} for c in data
                       if isinstance(c, dict) and "name" in c and "value" in c]
            if cookies:
                return cookies
    except (json.JSONDecodeError, TypeError):
        pass
    cookies = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or (line.startswith('#') and not line.startswith('#HttpOnly_')):
            continue
        if line.startswith('#HttpOnly_'):
            line = line[len('#HttpOnly_'):]
        parts = line.split('\t')
        if len(parts) >= 7:
            cookies.append({"name": parts[5], "value": parts[6]})
    return cookies


def _safe_domain(domain):
    return re.sub(r'[^a-zA-Z0-9.]', '_', domain)


class DownloadController(Bag):
    groupDomains = GROUP_DOMAINS
    sites = SITES

    authStatusChanged = pyqtSignal()
    authBusyChanged = pyqtSignal()
    authDialogChanged = pyqtSignal()
    runningChanged = pyqtSignal()
    percentChanged = pyqtSignal()
    statusTextChanged = pyqtSignal()
    chapterTextChanged = pyqtSignal()
    finishedOk = pyqtSignal(str, str)
    failed = pyqtSignal(str)
    warned = pyqtSignal(str)

    authStatus = P("QVariantMap", "authStatus", authStatusChanged, {})
    authBusy = P(bool, "authBusy", authBusyChanged, False)
    authDialog = P("QVariantMap", "authDialog", authDialogChanged, {})
    running = P(bool, "running", runningChanged, False)
    percent = P(int, "percent", percentChanged, 0)
    statusText = P(str, "statusText", statusTextChanged, "")
    chapterText = P(str, "chapterText", chapterTextChanged, "")

    def __init__(self, backend):
        super().__init__(backend)
        self._backend = backend
        self._loader = None
        self._auth_loader = None
        self._auth_thread = None
        self._auth_timer = None
        self._auth_after = None
        self._v.update(authStatus={}, authBusy=False, authDialog={"visible": False, "site": "", "message": ""},
                       running=False, percent=0, statusText="", chapterText="")

    @pyqtSlot(result="QVariantList")
    def siteList(self):
        return SITES

    @pyqtSlot(result="QVariantList")
    def domainList(self):
        return list(GROUP_DOMAINS)

    # -- определение сайта по ссылке
    @pyqtSlot(str, result="QVariantMap")
    def detect(self, url):
        domain = urlparse(url.strip()).netloc if url.strip() else ""
        site = ""
        if domain:
            if any(d in domain for d in MANGALIB_DOMAINS):
                site = "MangaLib"
            elif "com-x.life" in domain:
                site = "Com-X.life"
            elif "mangahub.ru" in domain:
                site = "MangaHub.ru"
            elif any(d in domain for d in GROUP_DOMAINS) or domain.startswith(("readmanga", "mintmanga", "seimanga")):
                site = "ReadManga/MintManga"
        return {"site": site, "domain": domain}

    # -- статус авторизации
    @pyqtSlot(str, str)
    def checkAuth(self, site, domain):
        ok = lambda text, btn: {"kind": "ok", "text": text, "button": btn}
        if "MangaLib" in site:
            token = ""
            path = DATA / 'mangalib_token.json'
            if path.exists():
                try:
                    token = json.loads(path.read_text(encoding='utf-8')).get("token", "")
                except Exception as e:
                    logging.error(f"Не удалось прочитать токен MangaLib: {e}")
            st = ok("Токен сохранён. Можно скачивать 18+.", "Обновить токен") if token else \
                {"kind": "warn", "text": "Токена нет. Для 18+ войдите в аккаунт.", "button": "Войти в аккаунт"}
        elif "Com-X" in site:
            st = ok("Вход выполнен.", "Обновить вход") if (DATA / 'comx_cookies.json').exists() else \
                {"kind": "error", "text": "Вы не вошли. Большинство манг требуют входа.", "button": "Войти в аккаунт"}
        elif "MangaHub" in site:
            st = ok("Вход выполнен.", "Обновить вход") if (DATA / 'mangahub_cookies.json').exists() else \
                {"kind": "info", "text": "Вход нужен только для закрытого и 18+ контента.", "button": "Войти в аккаунт"}
        else:
            domain = (domain or "").strip()
            if not domain:
                st = {"kind": "info", "text": "Выберите сайт или вставьте ссылку на мангу.", "button": "Войти в аккаунт"}
            elif (DATA / f'group_cookies_{_safe_domain(domain)}.json').exists():
                st = ok(f"Вход на {domain} выполнен.", "Обновить вход")
            else:
                st = {"kind": "error", "text": f"Вы не вошли на {domain}. Это нужно для 18+ и части глав.",
                      "button": "Войти в аккаунт"}
        self.set("authStatus", st)

    # -- вход в аккаунт
    @pyqtSlot(str, str)
    def startAuth(self, site, domain):
        if "MangaLib" in site:
            self._auth_mangalib()
            return
        if "ReadManga" in site:
            domain = (domain or "").strip()
            if not domain:
                self._backend.toast("warn", "Выберите сайт или вставьте ссылку на мангу, затем нажмите «Войти в аккаунт».")
                return
            loader, label = GroupDownloadThread(f"https://{domain}/", ""), domain
        elif "Com-X" in site:
            loader, label = ComXDownloadThread("https://com-x.life", ""), "com-x.life"
        else:
            loader, label = MangaHubDownloadThread("https://mangahub.ru/", ""), "mangahub.ru"
        self.set("authBusy", True)
        self._run_auth(loader, label, lambda: (self.set("authBusy", False), self.checkAuth(site, domain)))

    def _run_auth(self, loader, label, after):
        self._auth_loader = loader
        self._auth_after = after
        loader.status.connect(self._on_auth_status)
        self.set("authDialog", {"visible": True, "site": label, "message": f"Открываю браузер для входа на {label}…"})
        self._auth_thread = threading.Thread(target=loader.auth_via_browser, daemon=True)
        self._auth_thread.start()
        self._auth_timer = QTimer(self)
        self._auth_timer.timeout.connect(self._poll_auth)
        self._auth_timer.start(300)

    def _on_auth_status(self, text):
        d = dict(self.get("authDialog", {}))
        d["message"] = text
        self.set("authDialog", d)

    def _poll_auth(self):
        if self._auth_thread and self._auth_thread.is_alive():
            return
        self._auth_timer.stop()
        self.set("authDialog", {"visible": False, "site": "", "message": ""})
        after, self._auth_after = self._auth_after, None
        if after:
            after()

    @pyqtSlot()
    def confirmAuth(self):
        if self._auth_loader:
            self._auth_loader.confirm_manual_auth()

    @pyqtSlot()
    def cancelAuth(self):
        if self._auth_loader:
            self._auth_loader.request_cancel()
        if self._loader is not None and self._loader.isRunning():
            # Вход всплыл посреди скачивания — без него скачивание не продолжить.
            self._loader.request_cancel()
            self.set("running", False)

    def _auth_mangalib(self):
        self.set("authBusy", True)
        result = {"token": None}

        def worker():
            from browser_driver import launch_authenticated_browser
            import time
            token, driver = None, None
            try:
                driver, name = launch_authenticated_browser()
                logging.info(f"Авторизация MangaLib через {name}")
                driver.get("https://mangalib.me")
                for _ in range(120):
                    time.sleep(1)
                    try:
                        token = driver.execute_script(
                            "try{var a=localStorage.getItem('auth');if(a){return JSON.parse(a).token.access_token;}}"
                            "catch(e){} return null;")
                        if token:
                            break
                    except Exception:
                        pass
            except Exception:
                token = None
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
            result["token"] = token

        self._backend.toast("info", "Открываю браузер. Войдите в аккаунт на mangalib.me — токен сохранится автоматически.")
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        timer = QTimer(self)

        def poll():
            if thread.is_alive():
                return
            timer.stop()
            self.set("authBusy", False)
            if result["token"]:
                DATA.mkdir(parents=True, exist_ok=True)
                (DATA / 'mangalib_token.json').write_text(json.dumps({"token": result["token"]}), encoding='utf-8')
                self._backend.toast("success", "Токен сохранён.")
            else:
                self._backend.toast("error", "Не удалось получить токен. Повторите вход и дождитесь загрузки сайта.")
            self.checkAuth("MangaLib", "")

        timer.timeout.connect(poll)
        timer.start(500)

    @pyqtSlot(str)
    def importCookies(self, domain):
        domain = (domain or "").strip()
        if not domain:
            self._backend.toast("warn", "Сначала выберите сайт или вставьте ссылку на мангу.")
            return
        path, _ = QFileDialog.getOpenFileName(None, "Выберите файл с куки", "", "Куки (*.json *.txt);;Все файлы (*.*)")
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding='utf-8')
        except Exception as e:
            self._backend.toast("error", f"Не удалось прочитать файл: {e}")
            return
        cookies = parse_cookie_file(raw)
        if not cookies:
            self._backend.toast("error", "Не удалось распознать куки. Нужен JSON-список (Cookie-Editor) "
                                         "или cookies.txt в формате Netscape.")
            return
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / f'group_cookies_{_safe_domain(domain)}.json').write_text(json.dumps(cookies), encoding='utf-8')
        self._backend.toast("success", f"Куки для {domain} импортированы: {len(cookies)}.")
        self.checkAuth("ReadManga/MintManga", domain)

    # -- скачивание
    @pyqtSlot(str, str, str)
    def start(self, site, url, output_format):
        url = (url or "").strip()
        root = self._backend.config.get("root_dir")
        if not url:
            self._backend.toast("warn", "Вставьте ссылку на мангу.")
            return
        if not root or not os.path.exists(root):
            self._backend.toast("warn", "Сначала выберите папку с мангой в настройках.")
            return
        if "MangaLib" in site:
            token = ""
            path = DATA / 'mangalib_token.json'
            if path.exists():
                try:
                    token = json.loads(path.read_text(encoding='utf-8')).get("token", "")
                except Exception as e:
                    logging.error(f"Не удалось прочитать токен MangaLib: {e}")
            loader = MangaLibDownloadThread(url, root, token=token, output_format=output_format)
        elif "ReadManga" in site:
            loader = GroupDownloadThread(url, root, output_format=output_format)
            loader.need_auth.connect(lambda: self._on_need_auth(loader, loader.domain))
        elif "MangaHub" in site:
            loader = MangaHubDownloadThread(url, root, output_format=output_format)
            loader.need_auth.connect(lambda: self._on_need_auth(loader, "mangahub.ru"))
        else:
            loader = ComXDownloadThread(url, root, output_format=output_format)
            loader.need_auth.connect(lambda: self._on_need_auth(loader, "com-x.life"))
        self._loader = loader
        self.set("percent", 0)
        self.set("statusText", "Подготовка…")
        self.set("chapterText", "")
        self.set("running", True)
        loader.progress.connect(self._on_progress)
        loader.status.connect(lambda t: self.set("statusText", t))
        loader.finished.connect(self._on_finished)
        loader.error.connect(self._on_error)
        loader.warning.connect(lambda m: self.warned.emit(m))
        loader.start()

    def _on_need_auth(self, loader, label):
        if loader is self._loader:
            self._run_auth(loader, label, None)

    def _on_progress(self, current, total, name):
        self.set("percent", int(current / total * 100) if total > 0 else 0)
        self.set("chapterText", f"Глава {current} из {total}: {name}")

    def _on_finished(self, title, folder):
        self.set("running", False)
        self.finishedOk.emit(title, folder)

    def _on_error(self, msg):
        self.set("running", False)
        self.failed.emit(msg)

    @pyqtSlot()
    def cancel(self):
        loader = self._loader
        self.set("running", False)
        if loader is not None and loader.isRunning():
            loader.request_cancel()
            if not loader.wait(3000):
                loader.terminate()
                loader.wait()
