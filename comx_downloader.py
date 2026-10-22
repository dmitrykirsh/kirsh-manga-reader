import os
import re
import time
import json
import requests
import logging
import zipfile
import shutil
from pathlib import Path
from urllib.parse import urlparse

from download_base import BaseDownloadThread


class ComXDownloadThread(BaseDownloadThread):
    def __init__(self, url, dest_root, output_format="Папки с картинками", chapter_filter=None):
        super().__init__(url, dest_root, output_format=output_format, chapter_filter=chapter_filter)

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
        self._saved_cookies = []
    
    def _load_cookies(self):
        """Читает сохранённые куки. True — только если в них есть вход в аккаунт
        (dle_user_id): без него API отвечает «Доступно только авторизованным»."""
        self._saved_cookies = []
        if self._cookies_file.exists():
            try:
                with open(self._cookies_file, 'r') as f:
                    self._saved_cookies = json.load(f)
                for c in self._saved_cookies:
                    self.session.cookies.set(c['name'], c['value'])
                return any(c.get('name') == 'dle_user_id' for c in self._saved_cookies)
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

        self.remove_empty_dirs(manga_folder)

        return cbz_path

    # -- работа через настоящий браузер ------------------------------------------------
    # Com-X закрыт JS-проверкой (__guard): обычные запросы получают заглушку вместо страницы.
    # Поэтому страницу и вызовы API делаем из браузера, который проверку проходит.

    def _open_manga_page(self):
        """Запускает браузер, подставляет сохранённые куки и дожидается window.__DATA__.
        Возвращает (driver, data) или (None, None)."""
        from browser_driver import launch_authenticated_browser

        self.status.emit("Открываю браузер для доступа к сайту...")
        driver, name = launch_authenticated_browser()
        try:
            driver.get("https://com-x.life/")
            time.sleep(2)
            for c in self._saved_cookies:
                try:
                    driver.add_cookie({k: v for k, v in c.items()
                                       if k in ('name', 'value', 'domain', 'path', 'expiry', 'secure', 'httpOnly')})
                except Exception as e:
                    logging.debug(f"Куки {c.get('name')} не добавлена: {e}")
            driver.get(self.url)
            self.status.emit("Получение списка глав...")
            for _ in range(90):
                if self._cancel_requested:
                    driver.quit()
                    return None, None
                if driver.execute_script("return typeof window.__DATA__ !== 'undefined' && !!window.__DATA__"):
                    data = driver.execute_script("return window.__DATA__")
                    return driver, data
                time.sleep(1)
            self.error.emit("Не найден блок с данными. Сайт не отдал страницу манги — "
                            "проверьте ссылку или обновите вход в аккаунт.")
        except Exception:
            try:
                driver.quit()
            except Exception:
                pass
            raise
        try:
            driver.quit()
        except Exception:
            pass
        return None, None

    @staticmethod
    def _chapter_number(ch):
        """Номер главы. Поле number в __DATA__ бывает неверным (у «# 2» и «# 3» встречалось 7),
        поэтому сначала берём номер из названия главы («# 12», «Глава 12»)."""
        m = re.search(r'(?:#|глава)\s*(\d+(?:[.,]\d+)?)', str(ch.get('title') or ''), re.IGNORECASE)
        if m:
            return m.group(1).replace(',', '.')
        return ch.get('number') if ch.get('number') not in (None, '') else ch.get('posi')

    def list_chapters(self):
        """Список глав из window.__DATA__ — он есть и у гостя, поэтому хватает браузера без окна."""
        from browser_driver import launch_headless_browser

        driver = launch_headless_browser()
        try:
            driver.get(self.url)
            data = None
            for _ in range(60):
                if driver.execute_script("return typeof window.__DATA__ !== 'undefined' && !!window.__DATA__"):
                    data = driver.execute_script("return window.__DATA__")
                    break
                time.sleep(0.5)
        finally:
            try:
                driver.quit()
            except Exception:
                pass
        if not data:
            raise RuntimeError("сайт не отдал страницу манги — проверьте ссылку")
        chapters = sorted(data.get('chapters') or [], key=lambda x: x.get('posi', 0))
        result = []
        for ch in chapters:
            num = self._chapter_number(ch)
            title = (ch.get('title') or '').strip()
            label = f"Глава {num}" if num is not None else title
            if title and title.lstrip('#').strip() != str(num):
                label += f" — {title}"
            result.append({"key": str(ch.get('id')), "label": label, "number": str(num) if num is not None else ""})
        return result

    @staticmethod
    def _rmdir_if_empty(folder):
        """Убирает папку манги, если в неё ничего не скачалось (иначе в библиотеке остаётся пустышка)."""
        try:
            for sub in folder.iterdir():
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
            folder.rmdir()
        except OSError:
            pass

    def _sync_session(self, driver):
        """Переносит куки и User-Agent из браузера в requests-сессию (для скачивания архивов)."""
        self.session.headers['User-Agent'] = driver.execute_script("return navigator.userAgent")
        for c in driver.get_cookies():
            self.session.cookies.set(c['name'], c['value'], domain=c.get('domain'))

    # Новый механизм Com-X (bulk-download.js): getImages отдаёт ссылки на страницы глав пачкой,
    # картинки качаются с CDN, а commit подтверждает скачанные главы и списывает суточную квоту.
    _API = "https://com-x.life/engine/ajax/controller.php?mod=api&action="
    _IMG_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

    class _Cancelled(Exception):
        pass

    @staticmethod
    def _browser_form_post(driver, action, params):
        """POST form-urlencoded из браузера (сессия, защита и user_hash — как у самой страницы).
        params: список пар (ключ, значение); user_hash подставляется из dle_login_hash."""
        driver.set_script_timeout(90)
        return driver.execute_async_script(
            """const cb = arguments[arguments.length - 1];
            const p = new URLSearchParams();
            p.append('user_hash', typeof dle_login_hash !== 'undefined' ? dle_login_hash : '');
            (arguments[1] || []).forEach(kv => p.append(kv[0], String(kv[1])));
            fetch(arguments[0], {method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest'},
                body: p.toString()})
            .then(r => r.text().then(t => cb({status: r.status, text: t})))
            .catch(e => cb({status: 0, text: String(e)}));""",
            ComXDownloadThread._API + action, [list(kv) for kv in params])

    @staticmethod
    def _browser_fetch_bytes(driver, url):
        import base64
        driver.set_script_timeout(180)
        res = driver.execute_async_script(
            """const cb = arguments[arguments.length - 1];
            fetch(arguments[0], {credentials: 'omit'})
            .then(r => r.ok ? r.arrayBuffer() : Promise.reject('HTTP ' + r.status))
            .then(buf => {
                let bin = '', bytes = new Uint8Array(buf);
                for (let i = 0; i < bytes.length; i += 32768)
                    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
                cb(btoa(bin));
            }).catch(e => cb('ERR:' + e));""", url)
        if not res or res.startswith('ERR:'):
            raise RuntimeError(res or 'пустой ответ')
        return base64.b64decode(res)

    def _download_page(self, driver, url):
        """Байты одной страницы: сначала обычным запросом, при отказе — через браузер."""
        try:
            r = self.session.get(url, headers={'Referer': 'https://com-x.life/'}, timeout=60)
            if r.status_code == 200 and r.content:
                return r.content
            logging.warning(f"Com-X: страница через requests не получена ({r.status_code}), пробую через браузер")
        except Exception as e:
            logging.warning(f"Com-X: ошибка скачивания страницы через requests: {e}")
        return self._browser_fetch_bytes(driver, url)

    def _request_manifest(self, driver, news_id, chapter_ids):
        """Ссылки на страницы глав пачки. Бросает RuntimeError с понятным текстом при отказе сайта."""
        params = [('news_id', news_id)] + [('chapter_ids[]', cid) for cid in chapter_ids]
        resp = self._browser_form_post(driver, "bulkdl/getImages", params)
        if resp.get('status') != 200:
            raise RuntimeError(f"сайт ответил HTTP {resp.get('status')}")
        try:
            payload = json.loads(resp['text'])
        except ValueError:
            raise RuntimeError("сайт вернул не JSON: " + str(resp.get('text'))[:100])
        if payload.get('requires_captcha'):
            raise RuntimeError("сайт просит ввести капчу. Откройте Com-X в браузере, скачайте любую главу "
                               "вручную и пройдите проверку, затем повторите.")
        if not payload.get('success'):
            raise RuntimeError(payload.get('error') or "сайт отказал в выдаче ссылок")
        data = payload.get('data') or {}
        if not isinstance(data.get('chapters'), list):
            raise RuntimeError("некорректный ответ сайта")
        return data

    def _commit(self, driver, chapter_ids):
        """Подтверждает скачанные главы — сайт списывает их из суточной квоты."""
        if not chapter_ids:
            return
        try:
            self._browser_form_post(driver, "bulkdl/commit", [('chapter_ids[]', cid) for cid in chapter_ids])
        except Exception as e:
            logging.warning(f"Com-X: не удалось подтвердить главы {chapter_ids}: {e}")

    def _save_chapter(self, driver, folder, pages):
        """Скачивает страницы главы в <folder>.part и переименовывает папку, когда главa целиком готова."""
        part = folder.with_name(folder.name + ".part")
        if part.exists():
            shutil.rmtree(part)
        part.mkdir(parents=True)
        for n, url in enumerate(pages, 1):
            if self._cancel_requested:
                raise self._Cancelled()
            ext = os.path.splitext(urlparse(url).path)[1].lower()
            if ext not in self._IMG_EXTS:
                ext = '.jpg'
            content = self._download_page(driver, url)
            (part / f"{n:03d}{ext}").write_bytes(content)
        if folder.exists():
            shutil.rmtree(folder)
        part.rename(folder)

    @staticmethod
    def _has_images(folder):
        return folder.is_dir() and any(f.suffix.lower() in ComXDownloadThread._IMG_EXTS for f in folder.iterdir())

    def run(self):
        driver = None
        try:
            if not self._load_cookies():
                self.status.emit("Нужен вход в аккаунт Com-X.")
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
                self._load_cookies()

            driver, data = self._open_manga_page()
            if driver is None:
                return
            self._sync_session(driver)

            self.manga_title = re.sub(r'[\\/*?:"<>|]', '_', data.get('title', 'Unknown'))
            self.manga_title = re.sub(r'[×★✓✔✘®™©]', '_', self.manga_title)

            chapters = data.get('chapters') or []
            chapters.sort(key=lambda x: x.get('posi', 0))
            if not chapters:
                self.error.emit("На странице нет списка глав.")
                return
            all_chapters = chapters
            chapters = self.filter_chapters(all_chapters, self._chapter_number, lambda ch: ch.get('id'))
            if not chapters:
                self.error.emit(f"Не найдено: {self.describe_filter()}. На сайте главы "
                                f"{self._chapter_number(all_chapters[0])}–{self._chapter_number(all_chapters[-1])}.")
                return

            bulk = data.get('bulkdl') or {}
            if bulk.get('blocked'):
                self.error.emit("Com-X временно ограничил скачивание для аккаунта. "
                                + str(bulk.get('blocked_note') or "Попробуйте позже."))
                return
            batch_size = max(1, min(int(bulk.get('batch') or 10), 10))
            news_id = str(data.get('news_id') or re.search(r'/(\d+)-', self.url).group(1))

            manga_path = Path(self.dest_root) / self.manga_title
            manga_path.mkdir(parents=True, exist_ok=True)

            def folder_of(ch):
                return manga_path / f"Ch_{int(ch['posi']):03d}"

            total = len(chapters)
            # Уже скачанные главы пропускаем: повторный запуск продолжает с места остановки и не тратит квоту.
            done = sum(1 for ch in chapters if self._has_images(folder_of(ch)))
            todo = [ch for ch in chapters if not self._has_images(folder_of(ch))]
            fresh = failed = 0
            stop_reason = ""

            for start in range(0, len(todo), batch_size):
                if self._cancel_requested:
                    self.status.emit("Скачивание отменено")
                    return
                batch = todo[start:start + batch_size]
                self.status.emit(f"Запрашиваю ссылки на главы {done + 1}–{done + len(batch)} из {total}...")
                try:
                    manifest = self._request_manifest(driver, news_id, [ch['id'] for ch in batch])
                except RuntimeError as e:
                    if 'авторизован' in str(e):
                        try:
                            self._cookies_file.unlink()
                        except OSError:
                            pass
                        self._rmdir_if_empty(manga_path)
                        self.error.emit("Com-X не принял вход в аккаунт. Нажмите «Войти в аккаунт» и "
                                        "войдите заново, затем повторите скачивание.")
                        return
                    stop_reason = str(e)
                    break

                delivered = {int(c['chapter_id']): c for c in manifest['chapters']}
                committed = []
                for ch in batch:
                    chapter_title = ch.get('title') or f"Глава {ch.get('posi', 0)}"
                    got = delivered.get(int(ch['id']))
                    if not got or not got.get('pages'):
                        stop_reason = "сервер не выдал ссылки — вероятно, исчерпан суточный лимит скачиваний"
                        continue
                    self.progress.emit(done + 1, total, chapter_title)
                    self.status.emit(f"Скачивание: {chapter_title}")
                    try:
                        self._save_chapter(driver, folder_of(ch), got['pages'])
                    except self._Cancelled:
                        self.status.emit("Скачивание отменено")
                        self._commit(driver, committed)
                        return
                    except Exception as e:
                        failed += 1
                        logging.error(f"Com-X: глава {ch.get('id')} не скачана: {e}")
                        self.status.emit(f"Ошибка главы «{chapter_title}»: {str(e)[:80]}")
                        continue
                    done += 1
                    fresh += 1
                    committed.append(ch['id'])
                self._commit(driver, committed)
                if stop_reason:
                    break
                time.sleep(0.5)

            if done == 0:
                self._rmdir_if_empty(manga_path)
                self.error.emit("Не удалось скачать ни одной главы: " + (stop_reason or "подробности в app.log") + ".")
                return

            complete = done == total
            if not complete:
                msg = f"Скачано глав: {done} из {total}."
                if stop_reason:
                    msg += f" Остановлено: {stop_reason}."
                elif failed:
                    msg += f" Не скачалось: {failed}."
                msg += " Запустите скачивание ещё раз — уже скачанные главы будут пропущены."
                self.warning.emit(msg)

            # В один CBZ пакуем только полную мангу: иначе повторный запуск перезаписал бы архив неполным.
            if complete and self.output_format == "CBZ (архив)":
                self.status.emit("Упаковка всех глав в CBZ...")
                self.pack_all_to_cbz(manga_path)

            self.finished.emit(self.manga_title, str(manga_path))

        except Exception as e:
            logging.exception("Com-X: ошибка загрузки")
            self.error.emit(str(e))
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
