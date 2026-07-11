import os
import re
import time
import json
import requests
import logging
import zipfile
import shutil
from pathlib import Path

from download_base import BaseDownloadThread


class ComXDownloadThread(BaseDownloadThread):
    def __init__(self, url, dest_root, output_format="Папки с картинками"):
        super().__init__(url, dest_root, output_format=output_format)

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://com-x.life/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        self.manga_title = None
        self.chapters = []
        self._cookies_loaded = False
        self._cookies_file = None
        
        localappdata = os.environ.get('LOCALAPPDATA', '')
        cookies_dir = Path(localappdata) / 'KirshMangaReader'
        cookies_dir.mkdir(parents=True, exist_ok=True)
        self._cookies_file = cookies_dir / 'comx_cookies.json'
    
    def _load_cookies(self):
        if self._cookies_file.exists():
            try:
                with open(self._cookies_file, 'r') as f:
                    cookies = json.load(f)
                    for c in cookies:
                        self.session.cookies.set(c['name'], c['value'])
                return True
            except Exception as e:
                logging.error(f"Не удалось загрузить куки Com-X: {e}")
        return False
    
    def confirm_manual_auth(self):
        """Вызывается из UI (кнопка "Я вошёл — продолжить"), когда
        автоматическое определение куки авторизации не сработало."""
        self._manual_confirm = True

    def auth_via_browser(self):
        import sys
        import os
        import traceback
        from browser_driver import launch_authenticated_browser

        if getattr(sys, 'frozen', False):
            log_dir = os.path.dirname(sys.executable)
        else:
            log_dir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(log_dir, "auth_debug.log")

        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("=== auth_via_browser START ===\n")
                f.write(f"frozen: {getattr(sys, 'frozen', False)}\n")
                f.write(f"executable: {sys.executable}\n")
                f.write(f"log_dir: {log_dir}\n")
        except Exception as e:
            logging.error(f"Не удалось создать auth_debug.log: {e}")

        driver = None

        try:
            self.status.emit("Открываю браузер для авторизации...")

            driver, browser_name = launch_authenticated_browser()

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Драйвер создан ({browser_name}), открываю сайт\n")

            driver.get("https://com-x.life")
            
            self.status.emit("Войдите в аккаунт в браузере. Программа ждёт...")
            
            self._cancel_requested = False
            self._manual_confirm = False
            cookies = None
            for i in range(120):
                time.sleep(1)
                if self._cancel_requested:
                    self.status.emit("Авторизация отменена")
                    if driver:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                    self._cookies_loaded = False
                    return False
                if self._manual_confirm:
                    self.status.emit("Подтверждено вручную, сохраняю куки...")
                    cookies = driver.get_cookies()
                    break
                try:
                    cookies = driver.get_cookies()
                    if any(c.get('name') == 'dle_user_id' for c in cookies):
                        self.status.emit("Авторизация обнаружена!")
                        with open(log_file, 'a', encoding='utf-8') as f:
                            f.write(f"Авторизация на {i} секунде\n")
                        break
                except Exception as e:
                    err_text = str(e).lower()
                    if 'no such window' in err_text or 'target window' in err_text or 'disconnected' in err_text:
                        self.status.emit("Окно браузера закрыто. Авторизация отменена.")
                        self._cookies_loaded = False
                        return False
                    logging.debug(f"Проверка куки не удалась (это нормально во время ожидания): {e}")
                if i % 10 == 0 and i > 0:
                    self.status.emit(f"Ожидание входа... {i} сек (или нажмите «Я вошёл»)")
            else:
                self.status.emit("Время ожидания истекло")
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write("Таймаут ожидания\n")
                if driver:
                    driver.quit()
                self._cookies_loaded = False
                return False
            
            with open(self._cookies_file, 'w') as f:
                json.dump(cookies, f)
            
            for c in cookies:
                self.session.cookies.set(c['name'], c['value'])
            
            if driver:
                driver.quit()
            
            self.status.emit("Куки сохранены")
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write("Успех!\n")
            self._cookies_loaded = True
            return True
            
        except Exception as e:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n=== ОШИБКА ===\n")
                f.write(f"Тип: {type(e).__name__}\n")
                f.write(f"Сообщение: {str(e)}\n")
                f.write(f"Traceback:\n{traceback.format_exc()}\n")
            
            self.status.emit(f"Ошибка: {str(e)[:100]}")
            self.error.emit(f"Ошибка авторизации. Подробности в auth_debug.log\n{str(e)[:200]}")
            
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logging.error(f"Ошибка при закрытии браузера: {e}")
            
            self._cookies_loaded = False
            return False
            
    def pack_all_to_cbz(self, manga_folder):
        """Упаковывает все главы в один CBZ"""
        if not manga_folder.exists():
            self.status.emit("Ошибка: папка с мангой не найдена")
            return None

        chapter_folders = sorted([f for f in manga_folder.iterdir() if f.is_dir()],
                                 key=lambda x: int(re.search(r'\d+', x.name).group()) if re.search(r'\d+', x.name) else 0)

        cbz_path = self.pack_chapters_to_cbz(
            manga_folder.parent / f"{manga_folder.name}.cbz",
            chapter_folders,
            lambda folder: folder.name
        )

        if manga_folder.exists():
            shutil.rmtree(manga_folder)

        return cbz_path

    def run(self):
        import sys
        import os
        import traceback
        
                                      
        if getattr(sys, 'frozen', False):
            log_dir = os.path.dirname(sys.executable)
        else:
            log_dir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(log_dir, "run_debug.log")
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("=== НАЧАЛО RUN ===\n")
                f.write(f"frozen: {getattr(sys, 'frozen', False)}\n")
                f.write(f"executable: {sys.executable}\n")
                f.write(f"log_dir: {log_dir}\n")
                f.write(f"url: {self.url}\n")
        except Exception as e:
            pass
        try:
            if not self._load_cookies():
                self.status.emit("Куки не найдены. Требуется авторизация.")
                self.need_auth.emit()
                
                max_wait_seconds = 180  # 3 минуты максимум на всю авторизацию
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
                
                if not self._cookies_loaded:
                    self.error.emit("Авторизация не выполнена")
                    return
            
            time.sleep(2)
            
            self.status.emit("Получение списка глав...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://com-x.life/',
                'Connection': 'keep-alive',
            }
            
            resp = self.session.get(self.url, headers=headers)
            resp.encoding = 'utf-8'
            
            match = re.search(r'window\.__DATA__\s*=\s*({.+?});', resp.text, re.DOTALL)
            if not match:
                self.error.emit("Не найден блок с данными")
                return
            
            data = json.loads(match.group(1))
            self.manga_title = re.sub(r'[\\/*?:"<>|]', '_', data.get('title', 'Unknown'))
            self.manga_title = re.sub(r'[×★✓✔✘®™©]', '_', self.manga_title)
            
            chapters = data.get('chapters', [])
            chapters.sort(key=lambda x: x.get('posi', 0))
            
            manga_id = re.search(r'/(\d+)-', self.url).group(1)
            
            manga_path = Path(self.dest_root) / self.manga_title
            manga_path.mkdir(parents=True, exist_ok=True)
            
            total = len(chapters)
            for i, ch in enumerate(chapters, 1):
                self.progress.emit(i, total, ch.get('title', f"Глава {ch.get('posi', 0)}"))
                default_chapter_title = f"Глава {ch.get('posi', 0)}"
                chapter_title = ch.get('title', default_chapter_title)
                self.status.emit(f"Скачивание: {chapter_title}")
                
                api_url = "https://com-x.life/engine/ajax/controller.php?mod=api&action=chapters/download"
                resp = self.session.post(api_url, 
                                         data=f"chapter_id={ch['id']}&news_id={manga_id}",
                                         headers={'Content-Type': 'application/x-www-form-urlencoded'})
                
                if resp.status_code != 200:
                    self.status.emit(f"Ошибка API: {resp.status_code}")
                    continue
                
                archive_url = resp.json().get('data')
                if not archive_url:
                    self.status.emit("API не вернул ссылку")
                    continue
                
                if archive_url.startswith('//'):
                    archive_url = 'https:' + archive_url
                
                download_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': self.url,
                }
                arc_resp = self.session.get(archive_url, headers=download_headers, stream=True)
                if arc_resp.status_code != 200:
                    self.status.emit(f"Ошибка скачивания: {arc_resp.status_code}")
                    continue
                
                chapter_folder = manga_path / f"Ch_{ch['posi']:03d}"
                chapter_folder.mkdir(parents=True, exist_ok=True)
                
                temp_zip = chapter_folder / "temp.zip"
                with open(temp_zip, 'wb') as f:
                    for chunk in arc_resp.iter_content(8192):
                        f.write(chunk)
                
                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    zf.extractall(chapter_folder)
                
                temp_zip.unlink()
                
                images = []
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                    images.extend(chapter_folder.glob(ext))
                
                numbered = []
                for img in images:
                    nums = re.findall(r'\d+', img.stem)
                    if nums:
                        numbered.append((int(nums[0]), img))
                
                numbered.sort(key=lambda x: x[0])
                
                for idx, (_, old) in enumerate(numbered, 1):
                    new = chapter_folder / f"{idx:03d}{old.suffix}"
                    old.rename(new)
                
                time.sleep(0.5)
            
            if self.output_format == "CBZ (архив)":
                self.status.emit("Упаковка всех глав в CBZ...")
                if manga_path.exists():
                    self.pack_all_to_cbz(manga_path)                  
                else:
                    self.status.emit("Ошибка: папка с мангой не найдена")
            
            self.finished.emit(self.manga_title, str(manga_path))
            
        except Exception as e:
            self.error.emit(str(e))