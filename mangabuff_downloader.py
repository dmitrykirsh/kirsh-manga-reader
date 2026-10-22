import os
import re
import time
import json
import shutil
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from download_base import BaseDownloadThread

BASE_URL = "https://mangabuff.ru"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)
IMG_EXTS = ('jpg', 'jpeg', 'png', 'webp', 'gif')


class MangaBuffDownloadThread(BaseDownloadThread):
    """Загрузчик для mangabuff.ru.

    Сайт на Laravel за DDoS-Guard, но обычные запросы через requests он пропускает —
    браузер не нужен. Страница манги (/manga/<slug>) отдаёт в HTML первые ~100 глав
    (a.chapters__item, от новых к старым), остальные страница догружает через
    POST /chapters/load {manga_id} с CSRF-токеном из <meta name="csrf-token"> — делаем
    так же. Читалка (/manga/<slug>/<том>/<глава>) — серверный HTML, картинки лежат
    в .reader__item img (первые в src, остальные лениво в data-src) на c*.mangabuff.ru
    и скачиваются без Referer и кук. Вход нужен только для закрытого/18+ контента —
    просим его, только если страницы главы оказались пусты (как у MangaHub).
    """

    def __init__(self, url, dest_root, output_format="Папки с картинками", chapter_filter=None):
        super().__init__(url.strip().rstrip('/'), dest_root, output_format=output_format,
                         chapter_filter=chapter_filter)
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": BASE_URL + "/",
        })
        self.manga_name = None
        self.chapters = []  # [{'key', 'url', 'vol', 'num', 'name'}] от первой главы к последней

        cookies_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader'
        cookies_dir.mkdir(parents=True, exist_ok=True)
        self._cookies_file = cookies_dir / 'mangabuff_cookies.json'
        self._cookies_loaded = False

    # -- куки и вход

    def _load_cookies(self):
        if self._cookies_file.exists():
            try:
                with open(self._cookies_file, 'r', encoding='utf-8') as f:
                    for c in json.load(f):
                        self.session.cookies.set(c['name'], c['value'])
                self._cookies_loaded = True
                return True
            except Exception as e:
                logging.error(f"Не удалось загрузить куки mangabuff.ru: {e}")
        return False

    # Laravel ставит remember_web_<hash> при входе с «Запомнить меня»; имя сессии гостю
    # тоже выдаётся, поэтому по нему вход не определить — есть кнопка «Я вошёл».
    def _is_auth_cookie(self, name):
        return (name or '').startswith('remember_web')

    def confirm_manual_auth(self):
        """Вызывается из UI (кнопка "Я вошёл — продолжить")."""
        self._manual_confirm = True

    def auth_via_browser(self):
        from browser_driver import launch_authenticated_browser

        self._manual_confirm = False
        self._cancel_requested = False
        driver = None
        try:
            self.status.emit("Открываю браузер для авторизации...")
            driver, _name = launch_authenticated_browser()
            driver.get(f"{BASE_URL}/login")

            self.status.emit("Войдите в аккаунт в браузере. Программа ждёт...")
            for i in range(180):
                time.sleep(1)
                if self._cancel_requested:
                    self.status.emit("Авторизация отменена")
                    self._cookies_loaded = False
                    return False
                if self._manual_confirm:
                    self.status.emit("Подтверждено вручную, сохраняю куки...")
                    break
                try:
                    cookies = driver.get_cookies()
                except Exception as e:
                    err_text = str(e).lower()
                    if 'no such window' in err_text or 'target window' in err_text or 'disconnected' in err_text:
                        self.status.emit("Окно браузера закрыто. Авторизация отменена.")
                        self._cookies_loaded = False
                        return False
                    cookies = []
                if any(self._is_auth_cookie(c.get('name')) for c in cookies):
                    self.status.emit("Авторизация обнаружена!")
                    break
                if i % 10 == 0 and i > 0:
                    self.status.emit(f"Ожидание входа... {i} сек (или нажмите «Я вошёл»)")
            else:
                self.status.emit("Время ожидания истекло")
                self._cookies_loaded = False
                return False

            cookies = driver.get_cookies()
            with open(self._cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f)
            for c in cookies:
                self.session.cookies.set(c['name'], c['value'])
            self.status.emit("Куки сохранены")
            self._cookies_loaded = True
            return True

        except Exception as e:
            self.status.emit(f"Ошибка: {str(e)[:100]}")
            self.error.emit(f"Ошибка авторизации. {str(e)[:200]}")
            self._cookies_loaded = False
            return False
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # -- запросы

    def _get(self, url, **kwargs):
        """GET с повтором при 429/5xx и обрывах соединения (DDoS-Guard иногда отвечает 5xx)."""
        resp, last_error = None, None
        timeout = kwargs.pop('timeout', 30)
        for attempt in range(4):
            try:
                resp = self.session.get(url, timeout=timeout, **kwargs)
                if resp.status_code != 429 and resp.status_code < 500:
                    return resp
            except requests.RequestException as e:
                last_error = e
            time.sleep(1.5 * (attempt + 1))
        if resp is None:
            raise last_error
        return resp

    def _slug(self):
        m = re.search(r'mangabuff\.ru/manga/([^/?#]+)', self.url)
        return m.group(1) if m else ''

    # -- главы

    @staticmethod
    def _parse_chapter(a):
        """a.chapters__item -> {'key', 'url', 'vol', 'num', 'name'}."""
        href = a.get('href') or ''
        url = href if href.startswith('http') else BASE_URL + href
        parts = [p for p in urlparse(url).path.split('/') if p]  # manga, slug, том, глава
        vol = parts[2] if len(parts) >= 4 else '0'
        num = (a.get('data-chapter') or (parts[3] if len(parts) >= 4 else '')).strip()
        if not num:
            value = a.select_one('.chapters__value span')
            num = value.get_text(strip=True) if value else '0'
        name_el = a.select_one('.chapters__name')
        name = name_el.get_text(" ", strip=True) if name_el else ''
        return {'key': url, 'url': url, 'vol': vol, 'num': num, 'name': name}

    def fetch_manga(self):
        """Название и полный список глав (с догрузкой через /chapters/load)."""
        slug = self._slug()
        if not slug:
            raise ValueError("Нужна ссылка на страницу манги вида https://mangabuff.ru/manga/…")
        page_url = f"{BASE_URL}/manga/{slug}"
        resp = self._get(page_url)
        if resp.status_code == 404:
            raise RuntimeError("Манга не найдена — проверьте ссылку.")
        if resp.status_code != 200:
            raise RuntimeError(f"Сайт вернул HTTP {resp.status_code}")
        page = BeautifulSoup(resp.text, 'html.parser')

        h1 = page.select_one('h1.manga__name') or page.find('h1')
        name = h1.get_text(" ", strip=True) if h1 else slug
        name = re.sub(r'[\\/*?:"<>|]', '_', name)
        self.manga_name = re.sub(r'[×★✓✔✘®™©]', '_', name).strip(' .') or slug

        items = page.select('.chapters__list a.chapters__item') or page.select('a.chapters__item')
        manga_el = page.select_one('.manga[data-id]')
        csrf = page.select_one('meta[name="csrf-token"]')
        if manga_el and csrf and page.select_one('.load-chapters-trigger'):
            more = self.session.post(f"{BASE_URL}/chapters/load", data={"manga_id": manga_el['data-id']},
                                     headers={"X-CSRF-TOKEN": csrf.get('content', ''),
                                              "X-Requested-With": "XMLHttpRequest",
                                              "Accept": "application/json",
                                              "Referer": page_url},
                                     timeout=30)
            if more.status_code == 200:
                try:
                    html = more.json().get('content') or ''
                    items += BeautifulSoup(html, 'html.parser').select('a.chapters__item')
                except ValueError:
                    logging.warning("MangaBuff: /chapters/load вернул не JSON")
            else:
                logging.warning(f"MangaBuff: /chapters/load вернул HTTP {more.status_code}")

        chapters, seen = [], set()
        for a in items:
            ch = self._parse_chapter(a)
            if ch['key'] in seen:
                continue
            seen.add(ch['key'])
            chapters.append(ch)
        chapters.reverse()  # сайт отдаёт от новых глав к старым
        self.chapters = chapters

    def list_chapters(self):
        self._load_cookies()
        self.fetch_manga()
        result = []
        for ch in self.chapters:
            label = f"Том {ch['vol']} · Глава {ch['num']}"
            if ch['name']:
                label += f" — {ch['name']}"
            result.append({"key": ch['key'], "label": label, "number": ch['num']})
        return result

    # -- скачивание

    def _page_urls(self, chapter_url):
        resp = self._get(chapter_url, headers={"Referer": self.url})
        if resp.status_code != 200:
            logging.error(f"MangaBuff: {chapter_url}: HTTP {resp.status_code}")
            return []
        page = BeautifulSoup(resp.text, 'html.parser')
        urls = []
        for img in page.select('.reader__pages .reader__item img') or page.select('.reader__item img'):
            src = (img.get('data-src') or img.get('src') or '').strip()
            if not src or src.startswith('data:'):
                continue
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = BASE_URL + src
            urls.append(src)
        return urls

    def _download_chapter(self, chapter, folder):
        """Скачивает страницы главы в folder. Возвращает (скачано, всего)."""
        urls = self._page_urls(chapter['url'])
        if not urls:
            return 0, 0
        folder.mkdir(parents=True, exist_ok=True)
        saved = 0
        for i, src in enumerate(urls, 1):
            if self._cancel_requested:
                break
            ext = src.split('?')[0].rsplit('.', 1)[-1].lower()
            if ext not in IMG_EXTS:
                ext = 'jpg'
            try:
                img = self._get(src, headers={"Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}, timeout=60)
                if img.status_code == 200 and img.content:
                    (folder / f"{i:03d}.{ext}").write_bytes(img.content)
                    saved += 1
                else:
                    logging.warning(f"MangaBuff: страница {i} ({src}): HTTP {img.status_code}")
            except Exception as e:
                logging.warning(f"MangaBuff: страница {i} ({src}): {e}")
            time.sleep(0.15)
        return saved, len(urls)

    def _wait_for_auth(self):
        """Ждёт входа через UI (need_auth). False — отмена или таймаут."""
        self.need_auth.emit()
        waited = 0
        while not self._cookies_loaded:
            if self._cancel_requested:
                return False
            time.sleep(0.5)
            waited += 0.5
            if waited >= 180:
                return False
        return True

    def run(self):
        try:
            self._load_cookies()
            self.status.emit("Получение информации о манге...")
            try:
                self.fetch_manga()
            except ValueError as e:
                self.error.emit(str(e))
                return

            if not self.chapters:
                self.error.emit("На странице манги нет глав.")
                return
            chapters = self.filter_chapters(self.chapters, lambda c: c['num'], lambda c: c['key'])
            if not chapters:
                self.error.emit(f"Не найдено: {self.describe_filter()}. На сайте главы "
                                f"{self.chapters[0]['num']}–{self.chapters[-1]['num']}.")
                return

            manga_path = Path(self.dest_root) / self.manga_name
            manga_path.mkdir(parents=True, exist_ok=True)

            volumes = {}  # том -> [папки глав]
            failed = []
            total = len(chapters)
            asked_auth = False
            for idx, ch in enumerate(chapters, 1):
                if self._cancel_requested:
                    self.status.emit("Скачивание отменено")
                    return
                title = f"Том {ch['vol']} Глава {ch['num']}"
                self.progress.emit(idx, total, title)
                self.status.emit(f"Скачивание: {title}")

                folder = manga_path / f"vol{ch['vol']}" / ch['num']
                saved, pages = self._download_chapter(ch, folder)
                if pages == 0 and not self._cookies_loaded and not asked_auth:
                    # Пустая читалка у гостя — обычно закрытая/18+ глава: просим вход один раз.
                    asked_auth = True
                    self.status.emit("Глава недоступна без входа — войдите в аккаунт")
                    if not self._wait_for_auth():
                        if self._cancel_requested:
                            self.status.emit("Скачивание отменено")
                            return
                    else:
                        saved, pages = self._download_chapter(ch, folder)
                if self._cancel_requested:
                    shutil.rmtree(folder, ignore_errors=True)
                    self.status.emit("Скачивание отменено")
                    return

                if saved == 0:
                    logging.error(f"MangaBuff: {title}: скачано 0 из {pages} страниц")
                    failed.append(title)
                    shutil.rmtree(folder, ignore_errors=True)
                    try:
                        folder.parent.rmdir()  # том, если в нём больше ничего нет
                    except OSError:
                        pass
                else:
                    if saved < pages:
                        failed.append(f"{title} ({saved}/{pages} стр.)")
                    volumes.setdefault(ch['vol'], []).append(folder)
                time.sleep(0.3)

            if not volumes:
                try:
                    manga_path.rmdir()  # только если пусто — ранее скачанное не трогаем
                except OSError:
                    pass
                self.error.emit("Не удалось скачать ни одной главы. Возможно, они закрыты для гостей — "
                                "войдите в аккаунт MangaBuff и повторите.")
                return

            if failed:
                sample = "; ".join(failed[:5]) + ("…" if len(failed) > 5 else "")
                self.warning.emit(f"Скачано не полностью: {len(failed)} из {total} глав ({sample}). "
                                  "Повторите скачивание позже для недостающих глав.")

            if self.output_format == "CBZ (архив)":
                self.status.emit("Упаковка в CBZ...")
                for vol, folders in volumes.items():
                    self.pack_chapters_to_cbz(manga_path / f"vol{vol}.cbz", folders,
                                              lambda folder: f"Глава {folder.name}")
                    try:
                        (manga_path / f"vol{vol}").rmdir()
                    except OSError:
                        pass

            self.finished.emit(self.manga_name, str(manga_path))

        except Exception as e:
            logging.exception("MangaBuff: ошибка загрузки")
            self.error.emit(str(e))
