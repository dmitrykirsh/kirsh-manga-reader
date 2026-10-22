import os
import re
import time
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import logging
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from download_base import BaseDownloadThread

class MangaLibDownloadThread(BaseDownloadThread):
    def __init__(self, url, dest_root, token="", output_format="Папки с картинками", chapter_filter=None):
        super().__init__(url, dest_root, output_format=output_format, chapter_filter=chapter_filter)
        self.token = token

        if 'hentailib' in url:
            self.api_url = "https://hapi.hentaicdn.org/api/manga"
            self.img_domains = ["img3h.hentaicdn.org"]
            self.site_id = "4"
        elif 'shlib' in url:
            # SlashLIB/YaoiLib — тот же движок и API, что у HentaiLib
            # (тоже hapi.hentaicdn.org), только свой Site-Id и картинки
            # лежат на img3.hentaicdn.org (без "h" в имени поддомена).
            # Токен — тот же аккаунт MangaLib, полученный через "Получить токен".
            self.api_url = "https://hapi.hentaicdn.org/api/manga"
            self.img_domains = ["img3.hentaicdn.org"]
            self.site_id = "2"
        else:
            self.api_url = "https://api.cdnlibs.org/api/manga"
            # Запасной список на случай, если /api/constants недоступен (см. _load_image_servers).
            self.img_domains = ["img3.cdnlibs.org", "img2.imglib.info"]
            self.site_id = "1"

    # Порядок серверов как в настройках читалки сайта; "crop" — обрезанные страницы, не берём.
    _SERVER_PRIORITY = ("download", "compress", "main", "secondary")

    def _load_image_servers(self, headers):
        """Актуальные серверы картинок из /api/constants. Сайт периодически меняет домены
        (img4–img8.cdnlibs.org и img3.mixlib.me уже не существуют), а на мёртвых доменах
        каждая страница сначала ждала ошибки DNS/503 и только потом шла на рабочий."""
        try:
            resp = self._api_get(self.api_url.rsplit('/', 1)[0] + "/constants", headers,
                                 params={"fields[]": "imageServers"})
            servers = resp.json().get('data', {}).get('imageServers', []) if resp.status_code == 200 else []
        except Exception as e:
            logging.warning(f"MangaLib: не удалось получить список серверов картинок: {e}")
            return
        site = int(self.site_id)
        hosts = []
        for server_id in self._SERVER_PRIORITY:
            for s in servers:
                host = urlparse(s.get('url') or '').netloc
                if s.get('id') == server_id and site in (s.get('site_ids') or []) and host and host not in hosts:
                    hosts.append(host)
        if hosts:
            self.img_domains = hosts + [d for d in self.img_domains if d not in hosts]
            logging.info(f"MangaLib: серверы картинок {self.img_domains}")

    def pack_to_cbz(self, manga_folder, volume_name, chapters_in_volume):
        """Упаковывает том в CBZ с сохранением структуры глав внутри"""
        import shutil

        chapter_folders = [manga_folder / volume_name / chapter for chapter in chapters_in_volume]
        if not any(f.exists() for f in chapter_folders):
            # Ни одна глава тома не скачалась — пустой CBZ не нужен, а папки тома
            # может и не быть (раньше rmtree на ней обрывал всё скачивание).
            return None
        cbz_path = self.pack_chapters_to_cbz(
            manga_folder / f"{volume_name}.cbz",
            chapter_folders,
            lambda folder: f"Глава {folder.name}"
        )
        self.remove_empty_dirs(manga_folder / volume_name)
        return cbz_path

    def _api_get(self, url, headers, params=None):
        """GET к API с повтором при 429/5xx: API ограничивает частоту запросов, и раньше
        глава с ответом 429 просто молча пропускалась."""
        resp = None
        for attempt in range(5):
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code != 429 and resp.status_code < 500:
                return resp
            wait = resp.headers.get('Retry-After', '')
            time.sleep(min(float(wait), 30) if wait.isdigit() else 2 * (attempt + 1))
        return resp

    def _slug(self):
        m = re.search(r'/manga/([^/?#]+)', self.url)
        return re.sub(r'[^a-zA-Z0-9\-_]', '', m.group(1)) if m else ''

    def _headers(self):
        headers = {
            "Origin": "https://mangalib.me",
            "Referer": "https://mangalib.me/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Site-Id": self.site_id,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _fetch_chapters(self, slug, headers):
        """(HTTP-статус, [{'key', 'vol', 'num', 'name', 'title'}]) — главы от первой к последней."""
        resp = self._api_get(f"{self.api_url}/{slug}/chapters", headers)
        if resp.status_code != 200:
            return resp.status_code, []
        data = resp.json()
        chapters_list = []
        if isinstance(data, dict):
            if isinstance(data.get('data'), list):
                chapters_list = data['data']
            elif isinstance(data.get('chapters'), list):
                chapters_list = data['chapters']
        chapters = []
        for ch in chapters_list:
            if not isinstance(ch, dict):
                continue
            vol = str(ch.get('volume', '0'))
            num = str(ch.get('number', '0'))
            chapters.append({
                'key': f"{vol}|{num}",
                'vol': vol,
                'num': num,
                'name': f"Vol.{vol} Ch.{num}",
                'title': (ch.get('name') or '').strip(),
            })
        return 200, chapters

    def list_chapters(self):
        slug = self._slug()
        if not slug:
            raise ValueError("Нужна ссылка на страницу манги вида https://mangalib.me/ru/manga/…")
        status, chapters = self._fetch_chapters(slug, self._headers())
        if status != 200:
            raise RuntimeError(f"сайт вернул HTTP {status}" + ("" if self.token else " — возможно, нужен вход"))
        if not chapters and not self.token:
            raise RuntimeError("глав не видно без входа — войдите в аккаунт MangaLib")
        return [{"key": c['key'],
                 "label": f"Том {c['vol']} · Глава {c['num']}" + (f" — {c['title']}" if c['title'] else ""),
                 "number": c['num']} for c in chapters]

    def run(self):
        try:
            self.status.emit("Получение информации...")
            
            slug = self._slug()
            if not slug:
                self.error.emit("Нужна ссылка на страницу манги вида https://mangalib.me/ru/manga/…")
                return

            headers = self._headers()
            resp = self._api_get(f"{self.api_url}/{slug}", headers)
            if resp.status_code != 200:
                self.error.emit(f"Манга не найдена (HTTP {resp.status_code}). Возможно, нужен токен.")
                return

            self._load_image_servers(headers)

            manga_name = resp.json().get('data', {}).get('name', 'Unknown')
            manga_name = re.sub(r'[\\/*?:"<>|]', '_', manga_name)
            manga_name = re.sub(r'[×★✓✔✘®™©]', '_', manga_name)

            status, all_chapters = self._fetch_chapters(slug, headers)
            if status != 200:
                self.error.emit(f"Не удалось получить главы (HTTP {status}). Возможно, нужен токен.")
                return
            if not all_chapters:
                if not self.token:
                    self.error.emit("Для этой манги нужна авторизация. Войдите в аккаунт MangaLib.")
                else:
                    self.error.emit("Не удалось найти главы")
                return

            chapters = self.filter_chapters(all_chapters, lambda c: c['num'], lambda c: c['key'])
            if self.chapter_filter:
                self.status.emit(f"Выбрано глав: {len(chapters)}")
            if not chapters:
                self.error.emit(f"Не найдено: {self.describe_filter()}. На сайте главы "
                                f"{all_chapters[0]['num']}–{all_chapters[-1]['num']}.")
                return

            volumes = {}
            for ch in chapters:
                vol = ch['vol']
                if vol not in volumes:
                    volumes[vol] = []
                volumes[vol].append(ch['num'])
            
            manga_path = Path(self.dest_root) / manga_name
            total_volumes = len(volumes)
            current_volume = 0
            failed_chapters = []
            saved_chapters = 0

            for vol_num, chapters_in_vol in volumes.items():
                current_volume += 1
                self.status.emit(f"Том {vol_num} ({current_volume}/{total_volumes})")

                for idx, ch in enumerate([c for c in chapters if c['vol'] == vol_num], 1):
                    if self._cancel_requested:
                        self.status.emit("Скачивание отменено")
                        return
                    total_in_vol = len(chapters_in_vol)

                    self.progress.emit(idx, total_in_vol, ch['name'])

                    self.status.emit(f"Скачивание: {ch['name']}")

                    resp = self._api_get(f"{self.api_url}/{slug}/chapter", headers,
                                         params={'volume': ch['vol'], 'number': ch['num']})

                    if resp.status_code != 200:
                        logging.error(f"Глава {ch['name']}: API вернул HTTP {resp.status_code}")
                        failed_chapters.append(ch['name'])
                        continue

                    pages = resp.json().get('data', {}).get('pages', [])

                    if not pages:
                        logging.error(f"Глава {ch['name']}: API вернул пустой список страниц. Ответ: {resp.text[:500]}")
                        failed_chapters.append(ch['name'])
                        continue
                    
                    folder = manga_path / f"vol{vol_num}" / ch['num']
                    folder.mkdir(parents=True, exist_ok=True)
                    
                    logging.info(f"Глава {ch['name']}: пример сырых данных страницы: {pages[0]}")
                    
                    saved_count = 0
                    for j, page in enumerate(pages, 1):
                        page_url = page.get('url', '') if isinstance(page, dict) else str(page)
                        
                        if page_url.startswith('http://') or page_url.startswith('https://'):
                            img_url = page_url
                            try:
                                img_resp = requests.get(img_url, timeout=30, verify=False, headers={
                                    'Referer': 'https://mangalib.me/',
                                    'User-Agent': 'Mozilla/5.0'
                                })
                                if img_resp.status_code == 200:
                                    (folder / f"{j:03d}.jpg").write_bytes(img_resp.content)
                                    saved_count += 1
                                else:
                                    logging.error(f"Глава {ch['name']}, страница {j}: HTTP {img_resp.status_code} при скачивании {img_url}")
                                time.sleep(0.2)
                            except Exception as e:
                                logging.error(f"Глава {ch['name']}, страница {j}: ошибка запроса {img_url}: {e}")
                                continue
                        else:
                            page_url = page_url.lstrip('/')
                            downloaded = False
                            for domain in self.img_domains:
                                img_url = f"https://{domain}/{page_url}"
                                logging.info(f"Пробую: {img_url}")
                                
                                img_headers = {
                                    'Referer': 'https://mangalib.me/',
                                    'Origin': 'https://mangalib.me',
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
                                    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                                    'Accept-Language': 'ru-RU,ru;q=0.5',
                                    'Accept-Encoding': 'gzip, deflate, br, zstd',
                                    'Cache-Control': 'no-cache',
                                    'Pragma': 'no-cache',
                                    'Priority': 'u=1, i',
                                    'Sec-Ch-Ua': '"NotA=Brand";v="8", "Chromium";v="150", "Brave";v="150"',
                                    'Sec-Ch-Ua-Mobile': '?0',
                                    'Sec-Ch-Ua-Platform': '"Windows"',
                                    'Sec-Fetch-Dest': 'image',
                                    'Sec-Fetch-Mode': 'no-cors',
                                    'Sec-Fetch-Site': 'cross-site',
                                    'Sec-Gpc': '1',
                                    'Connection': 'keep-alive',
                                }
                                
                                try:
                                    img_resp = requests.get(img_url, timeout=30, verify=False, headers=img_headers)
                                    if img_resp.status_code == 200:
                                        ext = '.jpg'
                                        if 'content-type' in img_resp.headers:
                                            ct = img_resp.headers['content-type']
                                            if 'png' in ct:
                                                ext = '.png'
                                            elif 'webp' in ct:
                                                ext = '.webp'
                                        (folder / f"{j:03d}{ext}").write_bytes(img_resp.content)
                                        saved_count += 1
                                        downloaded = True
                                        if domain != self.img_domains[0]:
                                            # Следующие страницы сразу с рабочего сервера.
                                            self.img_domains.remove(domain)
                                            self.img_domains.insert(0, domain)
                                        break
                                    else:
                                        logging.warning(f"HTTP {img_resp.status_code} на {img_url}")
                                except Exception as e:
                                    logging.error(f"Ошибка: {e}")
                                time.sleep(0.3)
                            
                            if not downloaded:
                                logging.error(f"Страница {j} не скачалась")
                                continue
                            time.sleep(0.2)
                    
                    if saved_count == 0:
                        # Пустая папка главы в библиотеке выглядела бы как скачанная глава.
                        logging.error(f"Глава {ch['name']}: скачано 0 из {len(pages)} страниц")
                        failed_chapters.append(ch['name'])
                        shutil.rmtree(folder, ignore_errors=True)
                    else:
                        saved_chapters += 1

                    time.sleep(0.5)

                if self.output_format == "CBZ (архив)":
                    self.status.emit(f"Упаковка тома {vol_num} в CBZ...")
                    self.pack_to_cbz(manga_path, f"vol{vol_num}", chapters_in_vol)

            if saved_chapters == 0:
                self.remove_empty_dirs(manga_path)
                self.error.emit("Не удалось скачать ни одной главы. Возможно, манга доступна только "
                                "после входа — получите токен и повторите скачивание.")
                return

            if failed_chapters:
                sample = "; ".join(failed_chapters[:5]) + ("…" if len(failed_chapters) > 5 else "")
                self.warning.emit(f"Не скачалось {len(failed_chapters)} из {len(chapters)} глав ({sample}). "
                                  "Остальное скачано — повторите скачивание позже для недостающих глав.")

            self.finished.emit(manga_name, str(manga_path))
            
        except Exception as e:
            self.error.emit(str(e))