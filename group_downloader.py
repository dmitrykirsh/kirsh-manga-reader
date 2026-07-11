import os
import re
import time
import random
import json
import shutil
import logging
from http.client import IncompleteRead
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from download_base import BaseDownloadThread

# Домены на движке ReadManga/MintManga (рид-читалка на rm_h.readerInit).
# Сайты этой сети периодически меняют/добавляют зеркала — список можно
# дополнять новыми доменами без изменения остальной логики загрузчика.
GROUP_DOMAINS = [
    "readmanga.live", "mintmanga.live",
    "web.usagi.one", "1.seimanga.me", "a.zazaza.me",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class GroupDownloadThread(BaseDownloadThread):
    """Загрузчик для ReadManga/MintManga и их зеркал.

    Список глав, название манги и сами страницы главы (скрипт
    rm_h.readerInit) получаются обычным HTTP-запросом через requests —
    сайт отдаёт всё нужное в серверном HTML без выполнения JS. Проверено
    вручную: headless Chrome тут не нужен и только вредит — движок сайта
    палит автоматизированный браузер и отдаёт 404 на страницах глав, а
    обычный requests.get() с корректными User-Agent/Referer открывает те
    же страницы без проблем. Браузер используется только один раз — для
    интерактивного входа в аккаунт (см. auth_via_browser).
    Авторизация — через куки, сохранённые после входа в браузере
    (аналогично Com-X.life).
    """

    def __init__(self, url, dest_root, output_format="Папки с картинками"):
        # Без этого при ссылке с завершающим "/" (".../slug/") построение
        # ссылок на главы дублирует слаг манги (".../slug/slug/vol1/1") —
        # url.rsplit('/', 1)[0] в этом случае не отрезает последний сегмент,
        # а только пустую строку после финального слэша.
        url = url.rstrip('/')
        super().__init__(url, dest_root, output_format=output_format)
        self.domain = urlparse(url).netloc

        referer_sep = "&" if "?" in url else "?"
        self.headers = {
            "accept": "*/*",
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "referer": f"{url}{referer_sep}mtr=true",
            "User-Agent": USER_AGENT,
        }
        self.headers_img = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "User-Agent": USER_AGENT,
        }

        self.manga_name = None
        self.links = []

        self._cookies_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader'
        self._cookies_dir.mkdir(parents=True, exist_ok=True)
        self._cookies_file = self._cookies_file_for(self.domain)
        self._cookies_loaded = False

    def _cookies_file_for(self, domain):
        safe_domain = re.sub(r'[^a-zA-Z0-9.]', '_', domain)
        return self._cookies_dir / f'group_cookies_{safe_domain}.json'

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
                logging.error(f"Не удалось загрузить куки {self.domain}: {e}")
        return False

    # Кука, по которой сайты этого движка обычно помечают вход в аккаунт.
    # Названия могут отличаться между зеркалами/версиями движка, поэтому
    # проверяем сразу несколько + всегда даём кнопку "уже вошёл" на случай,
    # если ни одно из этих имён не подойдёт для конкретного сайта.
    KNOWN_AUTH_COOKIES = ('dle_user_id', 'dle_password', 'user_id', 'auth_key', 'member_id',
                          'remember_me')

    def confirm_manual_auth(self):
        """Вызывается из UI (кнопка "Я вошёл — продолжить"), когда
        автоматическое определение куки авторизации не сработало."""
        self._manual_confirm = True

    def auth_via_browser(self):
        """Открывает браузер для входа. Ждём появления одной из известных
        куки авторизации (см. KNOWN_AUTH_COOKIES) ИЛИ ручного подтверждения
        через confirm_manual_auth() — у разных зеркал этого движка кука
        может называться по-разному, автоопределение не универсально.
        Отменяется через request_cancel() в любой момент ожидания."""
        from browser_driver import launch_authenticated_browser

        self._manual_confirm = False
        self._cancel_requested = False
        driver = None
        try:
            self.status.emit("Открываю браузер для авторизации...")
            driver, browser_name = launch_authenticated_browser()

            # Некоторые зеркала отдают 404/блокировку при прямом заходе на
            # домен без referer (защита от ботов) — подставляем referer от
            # Google, как будто пришли из поисковой выдачи.
            try:
                driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                    'headers': {'Referer': 'https://www.google.com/'}
                })
            except Exception as e:
                logging.debug(f"Не удалось выставить Referer через CDP: {e}")

            driver.get(f"https://{self.domain}")

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
                        # Пользователь закрыл окно браузера вручную — сообщаем
                        # явно, а не молча ждём оставшиеся 180 секунд.
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

            # Некоторые из GROUP_DOMAINS — мёртвые алиасы, вход на них сайт
            # сам перекидывает на реально работающее зеркало (например
            # 3.readmanga.ru -> a.zazaza.me). Сохраняем куки под тем доменом,
            # на котором реально оказался пользователь после входа.
            try:
                final_domain = urlparse(driver.current_url).netloc
            except Exception:
                final_domain = self.domain
            if final_domain and final_domain != self.domain:
                self.status.emit(f"Сайт перенаправил на {final_domain} — сохраняю куки для него")
                self.domain = final_domain
                self._cookies_file = self._cookies_file_for(self.domain)

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

    def _adopt_redirect(self, resp):
        """Некоторые из GROUP_DOMAINS — уже мёртвые алиасы, сайт сам
        редиректит их на реально работающее зеркало (например
        2.mintmanga.one -> 1.seimanga.me). requests это делает прозрачно,
        но дальше нужно строить ссылки на главы уже от реального домена,
        а не от изначально введённого."""
        new_url = resp.url.rstrip('/')
        if new_url != self.url:
            logging.info(f"{self.url} перенаправлен на {new_url}, использую его для дальнейших запросов")
            self.url = new_url
            self.domain = urlparse(self.url).netloc
            referer_sep = "&" if "?" in self.url else "?"
            self.headers["referer"] = f"{self.url}{referer_sep}mtr=true"

    def get_manga_data(self):
        resp = self.session.get(self.url, headers=self.headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Сервер вернул {resp.status_code}")
        self._adopt_redirect(resp)
        page = BeautifulSoup(resp.content, 'html.parser')
        title_div = page.find('div', class_="py-1")
        name = title_div.text.strip() if title_div else "Unknown"
        self.manga_name = re.sub(r'[\\/*?:"<>|]', '_', name)

    def get_chapter_links(self):
        resp = self.session.get(self.url, headers=self.headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Сервер вернул {resp.status_code}")
        self._adopt_redirect(resp)
        page = BeautifulSoup(resp.content, 'html.parser')
        links = [
            link['href']
            for div in page.find_all('div', class_="chapters")
            for link in div.find_all('a', class_="chapter-link")
        ]
        links.reverse()
        self.links = links

    @staticmethod
    def _parse_vol_chapter(link):
        """Разбирает ссылку на главу вида "/slug/vol1/12" или "/slug/12"
        (не у всех манг есть тома) на номер тома и номер главы."""
        parts = [p for p in link.split('/') if p]
        tail = parts[1:]  # без слага манги
        if len(tail) >= 2 and re.match(r'^vol\d+$', tail[0]):
            vol = re.sub(r'^\D+', '', tail[0]) or '0'
            ch = tail[1]
        elif tail:
            vol, ch = '0', tail[0]
        else:
            vol, ch = '0', '0'
        return vol, ch

    def _download_chapter_pages(self, full_url, chapter_folder):
        script_text = None
        for attempt in range(4):
            try:
                resp = self.session.get(f"{full_url}?mtr=true", headers=self.headers, timeout=20)
                # Сайт иногда отдаёт валидную страницу читалки со статусом
                # 404 (это не намеренная блокировка — проверено вручную), так
                # что ориентируемся на само содержимое, а не на код ответа.
                if "rm_h.readerInit" in resp.text:
                    script_text = resp.text
                    break
                logging.warning(f"Глава {full_url}: HTTP {resp.status_code} (попытка {attempt + 1}/4)")
            except Exception as e:
                logging.warning(f"Глава {full_url}: ошибка запроса {e} (попытка {attempt + 1}/4)")
            time.sleep(2.5)

        if not script_text:
            return 0

        match = re.search(r"rm_h\.readerInit\(.*?\);", script_text, re.DOTALL)
        matches = re.findall(r"\['(https?://[^']+/)','',\"([^\"]+)\"", match.group(0) if match else script_text)
        page_urls = [domain + path for domain, path in matches]

        saved = 0
        for i, src in enumerate(page_urls, 1):
            # У ссылок есть query-параметры (?t=...&h=...) — расширение нужно
            # брать из пути, а не из хвоста строки, иначе "png?t=..." не
            # распознаётся и всё сохраняется как .jpg.
            ext = src.split("?")[0].split(".")[-1][:4].lower()
            if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
                ext = "jpg"

            for attempt in range(10):
                try:
                    resp = requests.get(src, headers=self.headers_img, timeout=30)

                    while resp.status_code in (429, 522):
                        time.sleep(1)
                        resp = requests.get(src, headers=self.headers_img, timeout=30)

                    if resp.status_code in (300, 502):
                        # CDN-хранилище картинок иногда не принимает подписанные
                        # query-параметры (?t=...&u=...&h=...) — без них отдаёт
                        # картинку нормально.
                        src = src.split("?", 1)[0]
                        resp = requests.get(src, headers=self.headers_img, timeout=30)

                    if resp.status_code != 200:
                        logging.warning(f"Страница {i} ({src}): HTTP {resp.status_code}")
                        break

                    (chapter_folder / f"{i}.{ext}").write_bytes(resp.content)
                    saved += 1
                    time.sleep(random.uniform(0.25, 0.35))
                    break
                except (IncompleteRead, requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.ConnectionError):
                    # Обрыв соединения на середине скачивания — сервер картинок
                    # (sei/mm.one-way.work) время от времени рвёт соединение,
                    # со второй попытки обычно отдаёт файл целиком.
                    time.sleep(0.5)
                except Exception as e:
                    logging.error(f"Ошибка скачивания страницы {src}: {e}")
                    break

        return saved

    def run(self):
        try:
            if not self._load_cookies():
                self.status.emit("Куки не найдены. Требуется авторизация.")
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

            self.status.emit("Получение информации о манге...")
            self.get_manga_data()
            self.get_chapter_links()

            if not self.links:
                self.error.emit("Не удалось найти главы")
                return

            manga_path = Path(self.dest_root) / self.manga_name
            manga_path.mkdir(parents=True, exist_ok=True)

            chapter_folders = []
            total = len(self.links)
            for idx, link in enumerate(self.links, 1):
                if self._cancel_requested:
                    self.status.emit("Скачивание отменено")
                    return
                vol, ch = self._parse_vol_chapter(link)
                chapter_name = f"Том {vol} Глава {ch}"
                self.progress.emit(idx, total, chapter_name)
                self.status.emit(f"Скачивание: {chapter_name}")

                full_url = self.url.rsplit('/', 1)[0] + link
                chapter_folder = manga_path / f"vol{vol}" / ch
                chapter_folder.mkdir(parents=True, exist_ok=True)
                chapter_folders.append(chapter_folder)

                saved = self._download_chapter_pages(full_url, chapter_folder)
                if saved == 0:
                    logging.error(f"Глава {chapter_name}: не удалось скачать ни одной страницы")

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
