"""Контроллер загрузки манги и авторизации на сайтах — для QML-диалогов."""

import os
import re
import json
import logging
import shutil
import threading
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtWidgets import QApplication, QFileDialog

from comx_downloader import ComXDownloadThread
from group_downloader import GroupDownloadThread, GROUP_DOMAINS, is_group_domain
from mangabuff_downloader import MangaBuffDownloadThread
from mangahub_downloader import MangaHubDownloadThread
from mangalib_downloader import MangaLibDownloadThread
import book_export
import site_search
from app.ui.base import Bag, P
from app.ui.network import qml_image_url
from app.ui.tasks import run_async

MANGALIB_DOMAINS = ("mangalib.me", "mangalib.org", "hentailib.me", "hentailib.org", "shlib.life", "slashlib.me")
SITES = ["MangaLib", "Com-X.life", "ReadManga/MintManga", "MangaHub.ru", "MangaBuff"]
# Загрузчики умеют только CBZ и папки; EPUB/PDF собираются из папок после скачивания.
EXPORT_FORMATS = ("EPUB", "PDF")
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


def _num(text):
    """Номер главы из поля ввода ("12", "7.5", "7,5") или None для пустого поля.
    ValueError — если введено не число."""
    text = str(text or "").strip().replace(",", ".")
    if not text:
        return None
    value = float(text)
    if value < 0:
        raise ValueError(text)
    return value


def chapter_filter_from(selection):
    """Выбор глав из окна скачивания -> (chapter_filter для загрузчика, текст ошибки).
    selection: {"mode": "all" | "one" | "range" | "pick", "one", "from", "to", "keys"}."""
    selection = selection or {}
    mode = selection.get("mode") or "all"
    try:
        if mode == "one":
            n = _num(selection.get("one"))
            if n is None:
                return None, "Укажите номер главы."
            return {"start": n, "end": n}, ""
        if mode == "range":
            start, end = _num(selection.get("from")), _num(selection.get("to"))
            if start is None and end is None:
                return None, "Укажите хотя бы одну границу диапазона глав."
            if start is not None and end is not None and start > end:
                start, end = end, start
            return {"start": start, "end": end}, ""
    except ValueError:
        return None, "Номер главы — это число, например 12 или 7.5."
    if mode == "pick":
        keys = [str(k) for k in (selection.get("keys") or [])]
        if not keys:
            return None, "Отметьте в списке хотя бы одну главу."
        return {"keys": keys}, ""
    return None, ""


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
    searchResultsChanged = pyqtSignal()
    searchBusyChanged = pyqtSignal()
    searchNoteChanged = pyqtSignal()
    chapterListChanged = pyqtSignal()
    chapterListBusyChanged = pyqtSignal()
    chapterListNoteChanged = pyqtSignal()
    exportProgress = pyqtSignal(int, int)   # из потока сборки EPUB/PDF

    authStatus = P("QVariantMap", "authStatus", authStatusChanged, {})
    authBusy = P(bool, "authBusy", authBusyChanged, False)
    authDialog = P("QVariantMap", "authDialog", authDialogChanged, {})
    running = P(bool, "running", runningChanged, False)
    percent = P(int, "percent", percentChanged, 0)
    statusText = P(str, "statusText", statusTextChanged, "")
    chapterText = P(str, "chapterText", chapterTextChanged, "")
    searchResults = P("QVariantList", "searchResults", searchResultsChanged, [])
    searchBusy = P(bool, "searchBusy", searchBusyChanged, False)
    searchNote = P(str, "searchNote", searchNoteChanged, "")
    # Главы для выбора: [{"key", "label", "number"}]; chapterListUrl — для какой ссылки загружены.
    chapterList = P("QVariantList", "chapterList", chapterListChanged, [])
    chapterListBusy = P(bool, "chapterListBusy", chapterListBusyChanged, False)
    chapterListNote = P(str, "chapterListNote", chapterListNoteChanged, "")
    chapterListUrl = P(str, "chapterListUrl", chapterListChanged, "")

    def __init__(self, backend):
        super().__init__(backend)
        self._backend = backend
        self._loader = None
        self._auth_loader = None
        self._auth_thread = None
        self._auth_timer = None
        self._auth_after = None
        self._v.update(authStatus={}, authBusy=False, authDialog={"visible": False, "site": "", "message": ""},
                       running=False, percent=0, statusText="", chapterText="",
                       searchResults=[], searchBusy=False, searchNote="",
                       chapterList=[], chapterListBusy=False, chapterListNote="", chapterListUrl="")
        self._search_gen = 0
        self._chapters_gen = 0
        self._search_pending = {}
        self._search_failed = []
        self._export_format = None
        self._export_stop = False
        self._warned_run = False
        self.exportProgress.connect(self._on_export_progress)

    @pyqtSlot(result="QVariantList")
    def siteList(self):
        return SITES

    @pyqtSlot(result="QVariantList")
    def domainList(self):
        return list(GROUP_DOMAINS)

    # -- буфер обмена
    @pyqtSlot(result=str)
    def clipboardLink(self):
        """Ссылка из буфера обмена, если это страница поддерживаемого сайта, иначе пустая строка."""
        text = (QApplication.clipboard().text() or "").strip()
        if not text.startswith(("http://", "https://")) or any(c.isspace() for c in text):
            return ""
        return text if self.detect(text)["site"] else ""

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
            elif "mangabuff.ru" in domain:
                site = "MangaBuff"
            elif is_group_domain(domain):
                site = "ReadManga/MintManga"
        return {"site": site, "domain": domain}

    # -- поиск по сайтам
    @pyqtSlot(str)
    def search(self, query):
        """Ищет на всех сайтах параллельно; результаты добавляются по мере ответов."""
        query = (query or "").strip()
        if len(query) < 2:
            self._backend.toast("warn", "Введите хотя бы два символа для поиска.")
            return
        self._search_gen += 1
        gen = self._search_gen
        self._search_pending = {site: label for site, (label, _fn) in site_search.SEARCHERS.items()}
        self._search_failed = []
        self.set("searchResults", [])
        self.set("searchBusy", True)
        self._update_search_note()
        for site, (label, fn) in site_search.SEARCHERS.items():
            run_async(lambda fn=fn: fn(query),
                      lambda res, err, site=site, label=label: self._on_search_part(gen, site, label, res, err), self)

    @pyqtSlot()
    def clearSearch(self):
        self._search_gen += 1
        self._search_pending = {}
        self.set("searchResults", [])
        self.set("searchBusy", False)
        self.set("searchNote", "")

    def _on_search_part(self, gen, site, label, results, error):
        if gen != self._search_gen:
            return  # ответ на устаревший запрос
        self._search_pending.pop(site, None)
        if error is not None:
            logging.warning(f"Поиск на {label} не удался: {error}")
            self._search_failed.append(label)
        elif results:
            items = list(self.get("searchResults", []))
            items.extend(dict(r, site=site, siteLabel=label, cover=qml_image_url(r.get("cover") or ""))
                         for r in results)
            self.set("searchResults", items)
        if not self._search_pending:
            self.set("searchBusy", False)
        self._update_search_note()

    def _update_search_note(self):
        found = len(self.get("searchResults", []))
        parts = [f"Найдено: {found}" if found else ("Ничего не найдено" if not self._search_pending else "")]
        if self._search_pending:
            parts.append("ищу на " + ", ".join(self._search_pending.values()) + "…")
        if self._search_failed:
            parts.append("не ответили: " + ", ".join(self._search_failed))
        self.set("searchNote", " · ".join(p for p in parts if p))

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
            logged_in = False
            try:
                cookies = json.loads((DATA / 'comx_cookies.json').read_text(encoding='utf-8'))
                logged_in = any(c.get("name") == "dle_user_id" for c in cookies)
            except Exception:
                pass
            st = ok("Вход выполнен.", "Обновить вход") if logged_in else \
                {"kind": "error", "text": "Вы не вошли. Скачивание с Com-X работает только после входа.", "button": "Войти в аккаунт"}
        elif "MangaHub" in site:
            st = ok("Вход выполнен.", "Обновить вход") if (DATA / 'mangahub_cookies.json').exists() else \
                {"kind": "info", "text": "Вход нужен только для закрытого и 18+ контента.", "button": "Войти в аккаунт"}
        elif "MangaBuff" in site:
            st = ok("Вход выполнен.", "Обновить вход") if (DATA / 'mangabuff_cookies.json').exists() else \
                {"kind": "info", "text": "Вход не обязателен — нужен только для закрытых и 18+ глав.",
                 "button": "Войти в аккаунт"}
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
        elif "MangaBuff" in site:
            loader, label = MangaBuffDownloadThread("https://mangabuff.ru/", ""), "mangabuff.ru"
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

    # -- выбор глав
    @pyqtSlot(str, str)
    def loadChapters(self, site, url):
        """Загружает список глав манги для окна выбора (в фоне)."""
        url = (url or "").strip()
        if not url:
            self._backend.toast("warn", "Вставьте ссылку на мангу.")
            return
        self._chapters_gen += 1
        gen = self._chapters_gen
        loader = self._make_loader(site, url, "", "Папки с картинками", None)
        self._v["chapterListUrl"] = url
        self.set("chapterList", [])
        self.chapterListChanged.emit()
        self.set("chapterListBusy", True)
        note = "Загружаю список глав…"
        if "Com-X" in site:
            note = "Загружаю список глав через браузер без окна — это займёт несколько секунд…"
        self.set("chapterListNote", note)
        run_async(loader.list_chapters, lambda res, err: self._on_chapters(gen, res, err), self)

    def _on_chapters(self, gen, chapters, error):
        if gen != self._chapters_gen:
            return  # ответ для другой ссылки
        self.set("chapterListBusy", False)
        if error is not None:
            self.set("chapterList", [])
            self.set("chapterListNote", f"Не удалось получить главы: {error}")
            return
        chapters = [{"key": str(c["key"]), "label": str(c["label"]), "number": str(c.get("number") or "")}
                    for c in (chapters or [])]
        self.set("chapterList", chapters)
        self.set("chapterListNote", f"Глав: {len(chapters)}" if chapters else "На странице манги нет глав.")

    @pyqtSlot()
    def clearChapters(self):
        self._chapters_gen += 1
        self._v["chapterListUrl"] = ""
        self.set("chapterList", [])
        self.chapterListChanged.emit()
        self.set("chapterListBusy", False)
        self.set("chapterListNote", "")

    # -- скачивание
    def _make_loader(self, site, url, root, output_format, chapter_filter):
        if "MangaLib" in site:
            token = ""
            path = DATA / 'mangalib_token.json'
            if path.exists():
                try:
                    token = json.loads(path.read_text(encoding='utf-8')).get("token", "")
                except Exception as e:
                    logging.error(f"Не удалось прочитать токен MangaLib: {e}")
            return MangaLibDownloadThread(url, root, token=token, output_format=output_format,
                                          chapter_filter=chapter_filter)
        if "ReadManga" in site:
            return GroupDownloadThread(url, root, output_format=output_format, chapter_filter=chapter_filter)
        if "MangaHub" in site:
            return MangaHubDownloadThread(url, root, output_format=output_format, chapter_filter=chapter_filter)
        if "MangaBuff" in site:
            return MangaBuffDownloadThread(url, root, output_format=output_format, chapter_filter=chapter_filter)
        return ComXDownloadThread(url, root, output_format=output_format, chapter_filter=chapter_filter)

    @pyqtSlot(str, str, str, "QVariantMap")
    def start(self, site, url, output_format, selection):
        url = (url or "").strip()
        root = self._backend.config.get("root_dir")
        if not url:
            self._backend.toast("warn", "Вставьте ссылку на мангу.")
            return
        if not root or not os.path.exists(root):
            self._backend.toast("warn", "Сначала выберите папку с мангой в настройках.")
            return
        chapter_filter, problem = chapter_filter_from(selection)
        if problem:
            self._backend.toast("warn", problem)
            return
        if chapter_filter and "keys" in chapter_filter and self.get("chapterListUrl") != url:
            self._backend.toast("warn", "Список глав загружен для другой ссылки — загрузите его заново.")
            return
        # EPUB/PDF: качаем папками, а после загрузки собираем книгу (см. _on_finished).
        self._export_format = output_format if output_format in EXPORT_FORMATS else None
        self._export_stop = False
        self._warned_run = False
        if self._export_format:
            output_format = "Папки с картинками"
        loader = self._make_loader(site, url, root, output_format, chapter_filter)
        if "ReadManga" in site:
            loader.need_auth.connect(lambda: self._on_need_auth(loader, loader.domain))
        elif "MangaHub" in site:
            loader.need_auth.connect(lambda: self._on_need_auth(loader, "mangahub.ru"))
        elif "MangaBuff" in site:
            loader.need_auth.connect(lambda: self._on_need_auth(loader, "mangabuff.ru"))
        elif "Com-X" in site:
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
        loader.warning.connect(self._on_warning)
        loader.start()

    def _on_warning(self, msg):
        self._warned_run = True
        self.warned.emit(msg)

    def _on_need_auth(self, loader, label):
        if loader is self._loader:
            self._run_auth(loader, label, None)

    def _on_progress(self, current, total, name):
        self.set("percent", int(current / total * 100) if total > 0 else 0)
        self.set("chapterText", f"Глава {current} из {total}: {name}")

    def _on_finished(self, title, folder):
        fmt = self._export_format
        if not fmt or not os.path.isdir(folder):
            self.set("running", False)
            self.finishedOk.emit(title, folder)
            return
        # Скачано не всё (было предупреждение) — папки оставляем: повторный запуск докачает недостающее.
        keep_folder = self._warned_run
        out_path = str(Path(folder).parent / f"{Path(folder).name}.{fmt.lower()}")
        self.set("percent", 0)
        self.set("statusText", f"Сборка {fmt}…")
        self.set("chapterText", "")

        def job():
            return book_export.export_book(folder, out_path, title, fmt,
                                           progress=lambda d, t: self.exportProgress.emit(d, t),
                                           should_stop=lambda: self._export_stop)

        def done(_result, error):
            if isinstance(error, book_export.ExportCancelled):
                return
            self.set("running", False)
            if error is not None:
                self.failed.emit(f"не удалось собрать {fmt}: {error}. Главы остались в папке {folder}")
                return
            if keep_folder:
                self.warned.emit(f"{fmt} собран из скачанных глав. Папка с главами сохранена, чтобы можно было докачать остальное.")
            else:
                shutil.rmtree(folder, ignore_errors=True)
            self.finishedOk.emit(title, out_path)

        run_async(job, done, self)

    def _on_export_progress(self, done, total):
        self.set("percent", int(done / total * 100) if total > 0 else 0)
        self.set("chapterText", f"Страница {done} из {total}")

    def _on_error(self, msg):
        self.set("running", False)
        self.failed.emit(msg)

    @pyqtSlot()
    def cancel(self):
        loader = self._loader
        self._export_stop = True
        self.set("running", False)
        if loader is not None and loader.isRunning():
            loader.request_cancel()
            if not loader.wait(3000):
                loader.terminate()
                loader.wait()
