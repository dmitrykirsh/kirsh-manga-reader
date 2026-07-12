import os
import re
import time
import json
import shutil
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from download_base import BaseDownloadThread

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class MangaHubDownloadThread(BaseDownloadThread):
    """Загрузчик для mangahub.ru.

    В отличие от MangaLib, это не SPA с отдельным API-доменом и Bearer-
    токеном — список глав и сама читалка отдаются обычным серверным HTML
    (проверено вручную requests.get() без JS: и /title/<slug>/chapters, и
    /read/<id> уже содержат готовые данные). Картинки лежат на *.statichub.org
    и скачиваются без Referer и без кук. Поэтому авторизация тут нужна не
    как у MangaLib (токен для каждого запроса), а как у ReadManga/Com-X —
    опциональные куки для приватного/18+ контента. Раз для проверенных манг
    ничего скачивать без входа не потребовалось, вход запрашиваем только
    если список глав реально оказался пуст, а не всегда наперёд.
    """

    def __init__(self, url, dest_root, output_format="Папки с картинками"):
        url = url.rstrip('/')
        super().__init__(url, dest_root, output_format=output_format)

        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://mangahub.ru/",
        }

        self.manga_name = None
        self.chapters = []  # [{'id', 'vol', 'num', 'name'}]

        cookies_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader'
        cookies_dir.mkdir(parents=True, exist_ok=True)
        self._cookies_file = cookies_dir / 'mangahub_cookies.json'
        self._cookies_loaded = False

    def _load_cookies(self):
        if self._cookies_file.exists():
            try:
                with open(self._cookies_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                for c in cookies:
                    self.session.cookies.set(c['name'], c['value'])
                self._cookies_loaded = True
                return True
            except Exception as e:
                logging.error(f"Не удалось загрузить куки mangahub.ru: {e}")
        return False

    # Как и в ReadManga/MintManga, конкретное имя куки авторизации заранее
    # не известно — держим кнопку "Я вошёл" как надёжный запасной вариант.
    KNOWN_AUTH_COOKIES = ('remember_web', 'mhub_session', 'session', 'auth_token')

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
            driver, browser_name = launch_authenticated_browser()
            driver.get("https://mangahub.ru/login")

            self.status.emit("Войдите в аккаунт в браузере. Программа ждёт...")
            for i in range(180):
                time.sleep(1)
                if self._cancel_requested:
                    self.status.emit("Авторизация отменена")
                    try:
                        driver.quit()
                    except Exception:
                        pass
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
                if any(c.get('name') in self.KNOWN_AUTH_COOKIES for c in cookies):
                    self.status.emit("Авторизация обнаружена!")
                    break
                if i % 10 == 0 and i > 0:
                    self.status.emit(f"Ожидание входа... {i} сек (или нажмите «Я вошёл»)")
            else:
                self.status.emit("Время ожидания истекло")
                try:
                    driver.quit()
                except Exception as e:
                    logging.debug(f"driver.quit() после таймаута: {e}")
                self._cookies_loaded = False
                return False

            cookies = driver.get_cookies()
            with open(self._cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f)
            for c in cookies:
                self.session.cookies.set(c['name'], c['value'])
            try:
                driver.quit()
            except Exception as e:
                logging.debug(f"driver.quit() после успешной авторизации: {e}")

            self.status.emit("Куки сохранены")
            self._cookies_loaded = True
            return True

        except Exception as e:
            self.status.emit(f"Ошибка: {str(e)[:100]}")
            self.error.emit(f"Ошибка авторизации. {str(e)[:200]}")
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            self._cookies_loaded = False
            return False

    def get_manga_name(self, slug):
        resp = self.session.get(f"https://mangahub.ru/title/{slug}", headers=self.headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Сервер вернул {resp.status_code}")
        page = BeautifulSoup(resp.content, 'html.parser')
        h1 = page.find('h1', class_="mb-1")
        name = h1.get_text(strip=True) if h1 else slug
        name = re.sub(r'[\\/*?:"<>|]', '_', name)
        self.manga_name = re.sub(r'[×★✓✔✘®™©]', '_', name)

    def get_chapters(self, slug):
        resp = self.session.get(f"https://mangahub.ru/title/{slug}/chapters", headers=self.headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Сервер вернул {resp.status_code}")
        page = BeautifulSoup(resp.content, 'html.parser')

        chapters = []
        for div in page.find_all('div', class_="detail-chapter"):
            bookmark = div.find('bookmark-progress')
            if not bookmark or not bookmark.get('item-id'):
                continue
            chapter_id = bookmark['item-id']
            num = bookmark.get('item-number', '0')

            a_tag = div.find('a', href=re.compile(r'^/read/\d+$'))
            title_text = a_tag.get_text(" ", strip=True) if a_tag else f"Глава {num}"
            vol_match = re.search(r'Том\s*(\d+)', title_text)
            vol = vol_match.group(1) if vol_match else '0'

            chapters.append({'id': chapter_id, 'vol': vol, 'num': num, 'name': title_text})

        chapters.reverse()  # страница отдаёт от новых глав к старым
        self.chapters = chapters

    def _confirm_age_gate(self, url, page):
        """18+ тайтлы вместо читалки отдают страницу "Подтверждение
        возраста" — обычную форму с CSRF-токеном (см. confirm_age[_token]),
        а не проверку логина. Отправляем её сами через POST с
        dismissAlways=1; сайт в ответ ставит куку confirm_age в self.session,
        и дальше все страницы читалки в рамках этого запуска открываются
        нормально — заходить в аккаунт для этого не нужно."""
        token_input = page.find('input', attrs={'name': 'confirm_age[_token]'})
        if not token_input or not token_input.get('value'):
            return page

        self.session.post(url, headers=self.headers, timeout=20, data={
            'confirm_age[_token]': token_input['value'],
            'confirm_age[dismissAlways]': '1',
        })
        resp = self.session.get(url, headers=self.headers, timeout=20)
        return BeautifulSoup(resp.content, 'html.parser')

    def _download_chapter_pages(self, chapter_id, folder):
        url = f"https://mangahub.ru/read/{chapter_id}"
        resp = self.session.get(url, headers=self.headers, timeout=20)
        if resp.status_code != 200:
            logging.error(f"Глава {chapter_id}: HTTP {resp.status_code}")
            return 0

        page = BeautifulSoup(resp.content, 'html.parser')
        scans = page.find_all('reader-scan')
        if not scans:
            page = self._confirm_age_gate(url, page)
            scans = page.find_all('reader-scan')

        saved = 0
        for i, scan in enumerate(scans, 1):
            img = scan.find('img')
            src = (img.get('data-src') or img.get('src')) if img else None
            if not src:
                continue
            if src.startswith('//'):
                src = 'https:' + src

            ext = src.split('?')[0].split('.')[-1][:4].lower()
            if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
                ext = 'jpg'

            for attempt in range(5):
                try:
                    img_resp = requests.get(src, headers=self.headers, timeout=30)
                    if img_resp.status_code == 200:
                        (folder / f"{i:03d}.{ext}").write_bytes(img_resp.content)
                        saved += 1
                        break
                    logging.warning(f"Страница {i} ({src}): HTTP {img_resp.status_code}")
                except Exception as e:
                    logging.warning(f"Страница {i} ({src}): {e}")
                time.sleep(1)
            time.sleep(0.2)

        return saved

    def run(self):
        try:
            self._load_cookies()

            slug = self.url.split('/title/')[1].split('/')[0].split('?')[0]
            slug = re.sub(r'[^a-zA-Z0-9_\-]', '', slug)

            self.status.emit("Получение информации о манге...")
            self.get_manga_name(slug)
            self.get_chapters(slug)

            if not self.chapters and not self._cookies_loaded:
                self.status.emit("Главы не найдены — возможно, нужна авторизация")
                self.need_auth.emit()

                max_wait_seconds = 180
                waited_seconds = 0
                while not self._cookies_loaded:
                    if self._cancel_requested:
                        self.status.emit("Скачивание отменено")
                        return
                    time.sleep(0.5)
                    waited_seconds += 0.5
                    if waited_seconds >= max_wait_seconds:
                        self.error.emit("Время ожидания авторизации истекло. Попробуйте снова.")
                        return

                self.get_chapters(slug)

            if not self.chapters:
                self.error.emit("Главы не найдены")
                return

            manga_path = Path(self.dest_root) / self.manga_name
            manga_path.mkdir(parents=True, exist_ok=True)

            chapter_folders = []
            total = len(self.chapters)
            for idx, ch in enumerate(self.chapters, 1):
                if self._cancel_requested:
                    self.status.emit("Скачивание отменено")
                    return
                self.progress.emit(idx, total, ch['name'])
                self.status.emit(f"Скачивание: {ch['name']}")

                chapter_folder = manga_path / f"vol{ch['vol']}" / ch['num']
                chapter_folder.mkdir(parents=True, exist_ok=True)
                chapter_folders.append(chapter_folder)

                saved = self._download_chapter_pages(ch['id'], chapter_folder)
                if saved == 0:
                    logging.error(f"Глава {ch['name']}: не удалось скачать ни одной страницы")

                time.sleep(0.3)

            if self.output_format == "CBZ (архив)":
                self.status.emit("Упаковка в CBZ...")
                self.pack_chapters_to_cbz(
                    manga_path.parent / f"{self.manga_name}.cbz",
                    chapter_folders,
                    lambda folder: f"{folder.parent.name}/{folder.name}"
                )
                if manga_path.exists():
                    shutil.rmtree(manga_path, ignore_errors=True)

            self.finished.emit(self.manga_name, str(manga_path))

        except Exception as e:
            self.error.emit(str(e))
