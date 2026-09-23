"""Корневой объект QML-приложения: конфиг, навигация, библиотека, действия над файлами."""

import os
import json
import shutil
import logging
import subprocess
import datetime
import urllib.request
import webbrowser

import requests
from natsort import natsorted
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty, QTimer
from PyQt6.QtWidgets import QFileDialog

import mangadex_client
from app import info_data, theme
from app.cache import BoundedCache, COVER_CACHE
from app.constants import (CONFIG_PATH, VALID_EXTENSIONS, ARCHIVE_EXTENSIONS, APP_VERSION,
                           GITHUB_REPO, is_newer_version)
from app.models import MangaItem, get_custom_cover_path
from app.ui import library, volumes
from app.ui.downloads import DownloadController
from app.ui.info import InfoController
from app.ui.library import LibraryModel
from app.ui.reader import ReaderController
from app.ui.tasks import run_async

TAB_TITLES = ["Библиотека", "Продолжить чтение", "Завершено", "В планах"]
TAB_MODES = [None, "reading", "done", "planned"]


class Backend(QObject):
    themeChanged = pyqtSignal()
    pageChanged = pyqtSignal()
    tabChanged = pyqtSignal()
    dirChanged = pyqtSignal()
    libraryChanged = pyqtSignal()
    cardWidthChanged = pyqtSignal()
    rootChanged = pyqtSignal()
    updateChanged = pyqtSignal()
    toastRequested = pyqtSignal(str, str)
    keyboardNavChanged = pyqtSignal()
    switchingChanged = pyqtSignal()
    mangadexEnabledChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = {
            "root_dir": "", "progress": {}, "theme": theme.DEFAULT_PRESET,
            "archive_cache": {}, "card_width": 220, "show_navigation_hint": True,
            "metadata": {}, "webtoon_mode": {}, "mangadex_enabled": True,
        }
        self._load_config()
        self.config["theme"] = theme.normalize_name(self.config.get("theme"))
        MangaItem.GLOBAL_CACHE = BoundedCache(300, self.config.get("archive_cache", {}))

        self._page = "library"
        self._tab = 0
        self._dir = self.config.get("root_dir", "")
        self._loading = False
        self._scan_gen = 0
        self._search = ""
        self._cover_ver = {}
        self._volumes_cache = {}
        self._origin = "library"
        self._empty_kind = ""
        self._update = {"available": False, "version": "", "url": ""}
        self._keyboard_nav = False
        self._switching = False

        self._model = LibraryModel(self)
        self._reader = ReaderController(self)
        self._info = InfoController(self)
        self._downloads = DownloadController(self)
        self._downloads.finishedOk.connect(self._on_download_finished)
        self._downloads.failed.connect(lambda m: self.toast("error", f"Не удалось скачать: {m}"))
        self._downloads.warned.connect(lambda m: self.toast("warn", m))
        self._reader.requestInfo.connect(self._reader_to_info)
        self._reader.requestClose.connect(self.closeReader)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self.save_config)

    # ---------------------------------------------------------------- конфиг
    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self.config.update(json.load(f))
            except Exception as e:
                logging.error(f"Не удалось прочитать конфиг: {e}")

    def save_config(self):
        self.config["archive_cache"] = MangaItem.GLOBAL_CACHE
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Не удалось сохранить конфиг: {e}")

    def report_progress(self, path, page, total):
        self.config["progress"][path] = {"page": page, "total": total}
        self._save_timer.start()

    def get_webtoon_pref(self, path):
        return self.config.get("webtoon_mode", {}).get(path, False)

    def set_webtoon_pref(self, path, enabled):
        prefs = self.config.setdefault("webtoon_mode", {})
        if enabled:
            prefs[path] = True
        else:
            prefs.pop(path, None)
        self.save_config()

    def set_item_status(self, path, status):
        meta = self.config.setdefault("metadata", {})
        if status == "none":
            if path in meta:
                meta[path].pop("status", None)
                if not meta[path]:
                    meta.pop(path)
        else:
            meta.setdefault(path, {})["status"] = status
        self.save_config()

    def set_item_rating(self, path, rating):
        meta = self.config.setdefault("metadata", {})
        if rating in (None, "none", 0):
            if path in meta:
                meta[path].pop("rating", None)
                if not meta[path]:
                    meta.pop(path)
        else:
            meta.setdefault(path, {})["rating"] = int(rating)
        self.save_config()

    def cover_version(self, path):
        return self._cover_ver.get(path, 0)

    def toast(self, kind, text):
        self.toastRequested.emit(kind, text)

    # ------------------------------------------------------------ свойства QML
    @pyqtProperty(QObject, constant=True)
    def library(self):
        return self._model

    @pyqtProperty(QObject, constant=True)
    def info(self):
        return self._info

    @pyqtProperty(QObject, constant=True)
    def reader(self):
        return self._reader

    @pyqtProperty(QObject, constant=True)
    def downloads(self):
        return self._downloads

    @pyqtProperty(str, constant=True)
    def appVersion(self):
        return APP_VERSION

    @pyqtProperty(bool, constant=True)
    def motionEnabled(self):
        return theme.motion_enabled()

    @pyqtProperty(str, notify=themeChanged)
    def themeName(self):
        return self.config["theme"]

    @pyqtProperty("QVariantMap", notify=themeChanged)
    def palette(self):
        return theme.get_preset(self.config["theme"])

    @pyqtProperty("QVariantList", constant=True)
    def themes(self):
        out = []
        for n in theme.PRESET_ORDER:
            p = theme.get_preset(n)
            out.append({"name": n, "accent": p["accent"], "accentHi": p["accent_hi"], "bg": p["bg"],
                        "panel": p["panel"], "elevated": p["elevated"], "card": p["card"]})
        return out

    @pyqtProperty(bool, notify=keyboardNavChanged)
    def keyboardNav(self):
        return self._keyboard_nav

    def set_keyboard_nav(self, value):
        if value != self._keyboard_nav:
            self._keyboard_nav = value
            self.keyboardNavChanged.emit()

    @pyqtProperty(bool, notify=switchingChanged)
    def themeSwitching(self):
        return self._switching

    @pyqtProperty(bool, notify=mangadexEnabledChanged)
    def mangadexEnabled(self):
        return bool(self.config.get("mangadex_enabled", True))

    @pyqtSlot(bool)
    def setMangadexEnabled(self, value):
        value = bool(value)
        if value == self.config.get("mangadex_enabled", True):
            return
        self.config["mangadex_enabled"] = value
        self.save_config()
        self.mangadexEnabledChanged.emit()

    @pyqtProperty(str, notify=pageChanged)
    def page(self):
        return self._page

    @pyqtProperty(int, notify=tabChanged)
    def tab(self):
        return self._tab

    @pyqtProperty(str, notify=dirChanged)
    def title(self):
        if self._tab == 0 and self._dir and self._dir != self.config.get("root_dir"):
            return os.path.basename(self._dir.rstrip("\\/")) or TAB_TITLES[0]
        return TAB_TITLES[self._tab]

    @pyqtProperty(bool, notify=dirChanged)
    def canGoUp(self):
        return self._tab == 0 and bool(self._dir) and self._dir != self.config.get("root_dir")

    @pyqtProperty(bool, notify=libraryChanged)
    def loading(self):
        return self._loading

    @pyqtProperty(str, notify=libraryChanged)
    def emptyKind(self):
        return self._empty_kind

    @pyqtProperty(int, notify=cardWidthChanged)
    def cardWidth(self):
        return int(self.config.get("card_width", 220))

    @pyqtProperty(str, notify=rootChanged)
    def rootDir(self):
        return self.config.get("root_dir", "")

    @pyqtProperty("QVariantMap", notify=updateChanged)
    def update(self):
        return self._update

    # ------------------------------------------------------------ тема/размер
    @pyqtSlot(str)
    def setTheme(self, name):
        name = theme.normalize_name(name)
        if name == self.config["theme"]:
            return
        # Смена темы — без анимаций цвета, иначе все поверхности «плывут» разом.
        self._switching = True
        self.switchingChanged.emit()
        self.config["theme"] = name
        self.save_config()
        self.themeChanged.emit()
        QTimer.singleShot(120, self._end_switching)

    def _end_switching(self):
        self._switching = False
        self.switchingChanged.emit()

    @pyqtSlot(int)
    def setCardWidth(self, value):
        self.config["card_width"] = int(value)
        self._save_timer.start()
        self.cardWidthChanged.emit()

    # -------------------------------------------------------------- навигация
    def _set_page(self, page):
        if page != self._page:
            self._page = page
            self.pageChanged.emit()

    @pyqtSlot(int)
    def setTab(self, index):
        if index == self._tab and self._page == "library":
            return
        self._tab = index
        self._set_page("library")
        self.tabChanged.emit()
        self.dirChanged.emit()
        self.refresh_library()

    @pyqtSlot()
    def goUp(self):
        if self.canGoUp:
            self._dir = os.path.dirname(self._dir)
            self.dirChanged.emit()
            self.refresh_library()

    @pyqtSlot()
    def showLibrary(self):
        if self._reader.get("active"):
            self._reader.close_reader()
        self._set_page("library")
        self.refresh_library()

    @pyqtSlot(str)
    def setSearch(self, text):
        self._search = text or ""
        self._model.set_filter(self._search)
        self._update_empty()

    def refresh_library_soft(self):
        """Обновить карточки после смены статуса/оценки, не трогая страницу."""
        self.refresh_library()

    @pyqtSlot()
    def refresh_library(self):
        self._scan_gen += 1
        gen = self._scan_gen
        root = self.config.get("root_dir")
        self._loading = True
        self.libraryChanged.emit()
        if not root or not os.path.exists(root):
            self._model.set_entries([])
            self._finish_scan()
            return
        if self._tab == 0 and (not self._dir or not os.path.exists(self._dir)):
            self._dir = root
            self.dirChanged.emit()
        snapshot = {"root_dir": root, "progress": dict(self.config.get("progress", {})),
                    "metadata": dict(self.config.get("metadata", {}))}
        ver = dict(self._cover_ver)
        mode = TAB_MODES[self._tab]
        target = self._dir

        def work():
            return library.scan_directory(snapshot, ver, target) if mode is None \
                else library.scan_flat(snapshot, ver, mode)

        def done(result, error):
            if gen != self._scan_gen:
                return
            if error is not None:
                self.toast("error", f"Не удалось прочитать библиотеку: {error}")
                result = []
            self._model.set_entries(result)
            self._finish_scan()

        run_async(work, done)

    def _finish_scan(self):
        self._loading = False
        self._update_empty()

    def _update_empty(self):
        root = self.config.get("root_dir")
        if not root or not os.path.exists(root):
            kind = "noRoot"
        elif self._model.total_count() == 0:
            kind = "emptyFolder" if self._tab == 0 else "emptyTab"
        elif self._model.shown_count() == 0:
            kind = "noResults"
        else:
            kind = ""
        self._empty_kind = kind
        self.libraryChanged.emit()

    # ---------------------------------------------------------- открытие манги
    @pyqtSlot(int)
    def openEntry(self, row):
        e = self._model.entry(row)
        if not e:
            return
        act, path = e["open"], e["path"]
        if act == "info":
            manga = MangaItem(path)
            if manga.pages:
                self.open_manga_info(manga)
        elif act == "series":
            self.open_series_info(path)
        elif act == "enter":
            self._dir = path
            self.dirChanged.emit()
            self.refresh_library()
        elif act == "continue":
            self._open_folder_continue(path)
        elif act == "completed":
            self._open_folder_completed(path)
        elif act == "planned":
            if volumes.is_series_folder(path):
                self.open_series_info(path)
            else:
                self._tab = 0
                self._dir = path
                self.tabChanged.emit()
                self.dirChanged.emit()
                self.refresh_library()
        elif act == "end":
            manga = MangaItem(path)
            if manga.pages:
                self.open_manga(manga, start_page=len(manga.pages) - 1)

    def _open_folder_continue(self, folder):
        norm = os.path.abspath(folder) + os.sep
        target = None
        for p, data in self.config["progress"].items():
            if os.path.abspath(p).startswith(norm) and isinstance(data, dict) \
                    and 0 < data.get("page", 0) < (data.get("total", 0) - 1):
                target = p
                break
        if not target:
            for root, _, files in os.walk(folder):
                arch = [os.path.join(root, f) for f in files if f.lower().endswith(ARCHIVE_EXTENSIONS)]
                if arch:
                    target = natsorted(arch)[0]
                    break
        if target:
            manga = MangaItem(target)
            if manga.pages:
                self.open_manga(manga)

    def _open_folder_completed(self, folder):
        files = []
        for root, _, names in os.walk(folder):
            files.extend(os.path.join(root, f) for f in names if f.lower().endswith(ARCHIVE_EXTENSIONS))
        if files:
            manga = MangaItem(natsorted(files)[-1])
            if manga.pages:
                self.open_manga(manga, start_page=len(manga.pages) - 1)

    def _list_volumes(self, folder):
        if folder not in self._volumes_cache:
            self._volumes_cache[folder] = volumes.compute_local_volumes(folder)
        return self._volumes_cache[folder]

    def _series_dir_for(self, manga_path):
        """Папка серии (тома/главы) для файла манги — или None, если файл лежит
        прямо в корне библиотеки и сам по себе не часть серии."""
        parent_dir = os.path.dirname(manga_path)
        root = os.path.normpath(self.config.get("root_dir", ""))
        parent_name = os.path.basename(parent_dir)
        grand = os.path.dirname(parent_dir)
        if os.path.normpath(parent_dir) == root:
            return None
        if volumes.VOL_FOLDER_RE.match(parent_name) and os.path.normpath(grand) != os.path.normpath(parent_dir):
            return grand
        return parent_dir

    def open_manga_info(self, manga):
        series_dir = self._series_dir_for(manga.path)
        self._set_origin_page()
        if series_dir:
            self._info.show_for(manga, os.path.basename(series_dir), series_dir, self._list_volumes(series_dir))
        else:
            self._info.show_for(manga, manga.display_name, manga.path, [])
        self._set_page("info")

    def open_series_info(self, folder):
        vols = self._list_volumes(folder)
        first = None
        for entry in vols:
            if entry["chapters"] and not entry.get("internal"):
                cands = [c[1] for c in entry["chapters"]]
            else:
                cands = [entry["path"]]
            for p in cands:
                if p:
                    m = MangaItem(p)
                    if m.pages:
                        first = m
                        break
            if first:
                break
        if not first:
            self._dir = folder
            self.dirChanged.emit()
            self._tab = 0
            self.tabChanged.emit()
            self.refresh_library()
            return
        self._set_origin_page()
        self._info.show_for(first, os.path.basename(folder), folder, vols)
        self._set_page("info")

    def _set_origin_page(self):
        if self._page in ("library", "info"):
            self._origin = self._page

    def open_manga(self, manga, start_page=None, force_webtoon=None):
        if start_page is None:
            prog = self.config["progress"].get(manga.path, {})
            start_page = prog.get("page", 0) if isinstance(prog, dict) else 0
        if self._page in ("library", "info"):
            self._origin = self._page
        series_dir = self._series_dir_for(manga.path)
        series_volumes = self._list_volumes(series_dir) if series_dir else []
        self._reader.open_manga(manga, start_page, force_webtoon, series_volumes)
        self._set_page("reader")

    @pyqtSlot()
    def closeReader(self):
        """Назад из читалки — туда, откуда пришли (страница манги или библиотека)."""
        self._reader.close_reader()
        self.save_config()
        if self._origin == "info" and self._info.current_manga is not None:
            self._info.refresh_progress()
            self._set_page("info")
        else:
            self._set_page("library")
            self.refresh_library()

    def _reader_to_info(self):
        manga = self._reader.manga
        if manga:
            self._reader.close_reader()
            self.save_config()
            self.open_manga_info(manga)

    # ---------------------------------------------------- действия над файлами
    @pyqtSlot(str, str)
    def itemAction(self, action, path):
        if action == "reset":
            self._reset_progress(path)
        elif action == "mark_read":
            self._mark_read(path)
        elif action == "open_folder":
            self._open_in_explorer(path)
            return
        elif action == "remove_cover":
            self._remove_cover(path)
        elif action.startswith("status:"):
            self.set_item_status(path, action.split(":", 1)[1])
        elif action.startswith("rating:"):
            v = action.split(":", 1)[1]
            self.set_item_rating(path, None if v == "none" else int(v))
        self._after_change()

    def _after_change(self):
        if self._page == "info":
            self._info.refresh_progress()
        self.refresh_library()

    def _reset_progress(self, path):
        if os.path.isdir(path):
            norm = os.path.abspath(path) + os.sep
            for p in [p for p in self.config["progress"] if os.path.abspath(p).startswith(norm)]:
                self.config["progress"].pop(p, None)
        self.config["progress"].pop(path, None)
        self.save_config()

    def _mark_read(self, path):
        progress = self.config["progress"]
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in files)
                has_arch = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in files)
                valid_dirs = [d for d in dirs if not d.startswith('.')]
                if has_images and not has_arch and not valid_dirs:
                    targets = [root]
                else:
                    targets = [os.path.join(root, f) for f in files if f.lower().endswith(ARCHIVE_EXTENSIONS)]
                for p in targets:
                    m = MangaItem(p)
                    if m.pages:
                        progress[p] = {"page": len(m.pages) - 1, "total": len(m.pages)}
        else:
            m = MangaItem(path)
            if m.pages:
                progress[path] = {"page": len(m.pages) - 1, "total": len(m.pages)}
        self.save_config()

    def _open_in_explorer(self, path):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            self.toast("error", f"Путь не найден: {path}")
            return
        if os.path.isdir(path):
            os.startfile(path)
        else:
            subprocess.Popen(f'explorer /select, "{path}"')

    @pyqtSlot(str, str)
    def renameItem(self, path, new_base):
        old_name = os.path.basename(path)
        ext = os.path.splitext(old_name)[1] if os.path.isfile(path) else ""
        base = new_base.strip()
        for ch in r'<>:"/\|?*':
            base = base.replace(ch, '_')
        if not base:
            return
        new_name = base + ext
        if new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(path), new_name)
        if os.path.exists(new_path):
            self.toast("error", f"Имя «{new_name}» уже занято. Выберите другое.")
            return
        try:
            os.rename(path, new_path)
        except Exception as e:
            self.toast("error", f"Не удалось переименовать: {e}")
            return
        self._volumes_cache.clear()
        for store in (self.config["progress"], self.config.get("metadata", {}), COVER_CACHE, MangaItem.GLOBAL_CACHE):
            if path in store:
                store[new_path] = store.pop(path)
        info_data.rename_cached_info(path, new_path)
        self.save_config()
        self.toast("success", f"Переименовано: {new_name}")
        if self._page == "info":
            self._set_page("library")
        self.refresh_library()

    @pyqtSlot(str)
    def deleteItem(self, path):
        try:
            self._reset_progress(path)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            self._volumes_cache.clear()
            self.config.get("metadata", {}).pop(path, None)
            COVER_CACHE.pop(path, None)
            MangaItem.GLOBAL_CACHE.pop(path, None)
            cp = get_custom_cover_path(path)
            if cp and os.path.exists(cp):
                os.remove(cp)
            self.save_config()
        except Exception as e:
            self.toast("error", f"Не удалось удалить: {e}")
            return
        self.toast("success", "Удалено с устройства.")
        if self._page == "info":
            self._set_page("library")
        self.refresh_library()

    # ------------------------------------------------------------ обложки
    def _cover_changed(self, path):
        COVER_CACHE.pop(path, None)
        self._cover_ver[path] = self._cover_ver.get(path, 0) + 1
        self.refresh_library()

    @pyqtSlot(str)
    def coverFromFile(self, path):
        f, _ = QFileDialog.getOpenFileName(None, "Выберите изображение", "", "Изображения (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not f:
            return
        try:
            shutil.copy(f, get_custom_cover_path(path))
            self._cover_changed(path)
            self.toast("success", "Обложка обновлена.")
        except Exception as e:
            self.toast("error", f"Не удалось скопировать файл: {e}")

    @pyqtSlot(str, str)
    def coverFromUrl(self, path, url):
        url = url.strip()
        if not url:
            return
        target = get_custom_cover_path(path)

        def work():
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            with open(target, 'wb') as f:
                f.write(data)

        def done(_, error):
            if error:
                self.toast("error", f"Не удалось скачать обложку: {error}")
            else:
                self._cover_changed(path)
                self.toast("success", "Обложка обновлена.")

        run_async(work, done)

    @pyqtSlot(str)
    def coverFromMangadex(self, path):
        target = get_custom_cover_path(path)

        def work():
            cached = info_data.load_cached_info(path)
            url = cached.get("cover_url") if cached else None
            if not url:
                query = os.path.splitext(os.path.basename(path))[0]
                results = info_data.search_mangadex_best(query, limit=1)
                if results:
                    url = mangadex_client.get_cover_url(results[0]["id"], results[0].get("relationships"))
            if not url:
                return False
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            with open(target, 'wb') as f:
                f.write(resp.content)
            return True

        def done(ok, error):
            if error:
                self.toast("error", f"Не удалось загрузить обложку: {error}")
            elif not ok:
                self.toast("warn", "На MangaDex не нашлась обложка для этой манги.")
            else:
                self._cover_changed(path)
                self.toast("success", "Обложка с MangaDex установлена.")

        self.toast("info", "Ищу обложку на MangaDex…")
        run_async(work, done)

    def _remove_cover(self, path):
        cp = get_custom_cover_path(path)
        if cp and os.path.exists(cp):
            try:
                os.remove(cp)
                self._cover_changed(path)
                self.toast("success", "Своя обложка удалена.")
            except Exception as e:
                self.toast("error", f"Не удалось удалить обложку: {e}")
        else:
            self.toast("info", "У этого элемента нет своей обложки.")

    # ------------------------------------------------------------- настройки
    @pyqtSlot()
    def pickRoot(self):
        folder = QFileDialog.getExistingDirectory(None, "Выберите корневую папку с мангой", self.config.get("root_dir", ""))
        if not folder:
            return
        self.config["root_dir"] = folder
        self._dir = folder
        self._volumes_cache.clear()
        self.save_config()
        self.rootChanged.emit()
        self.dirChanged.emit()
        self.refresh_library()

    @pyqtSlot()
    def rescan(self):
        COVER_CACHE.clear()
        MangaItem.GLOBAL_CACHE = BoundedCache(max_size=300)
        self._volumes_cache.clear()
        self.refresh_library()
        self.toast("success", "Библиотека пересканирована.")

    @pyqtSlot()
    def exportProgress(self):
        root = self.config.get("root_dir")
        if not root:
            self.toast("warn", "Сначала выберите папку с мангой.")
            return
        path, _ = QFileDialog.getSaveFileName(None, "Экспорт прогресса чтения", "kirsh_manga_progress.json", "JSON (*.json)")
        if not path:
            return
        exported = {}
        for p, data in self.config["progress"].items():
            try:
                rel = os.path.relpath(p, root)
            except ValueError:
                continue
            if not rel.startswith(".."):
                exported[rel] = data
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({"app": "KirshMangaReader", "format_version": 1, "progress": exported}, f, ensure_ascii=False, indent=2)
            self.toast("success", f"Прогресс экспортирован: {len(exported)} записей.")
        except Exception as e:
            self.toast("error", f"Не удалось сохранить файл: {e}")

    @pyqtSlot(bool)
    def importProgress(self, replace):
        root = self.config.get("root_dir")
        if not root:
            self.toast("warn", "Сначала выберите папку с мангой.")
            return
        path, _ = QFileDialog.getOpenFileName(None, "Импорт прогресса чтения", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            self.toast("error", f"Не удалось прочитать файл: {e}")
            return
        imported = payload.get("progress") if isinstance(payload, dict) else None
        if not isinstance(imported, dict):
            self.toast("error", "Файл не похож на экспорт прогресса Kirsh Manga Reader.")
            return
        added = missing = 0
        for rel, data in imported.items():
            p = os.path.normpath(os.path.join(root, rel))
            if not os.path.exists(p):
                missing += 1
                continue
            if p in self.config["progress"] and not replace:
                continue
            self.config["progress"][p] = data
            added += 1
        self.save_config()
        self.refresh_library()
        msg = f"Импортировано записей: {added}."
        if missing:
            msg += f" Не найдено на диске: {missing}."
        self.toast("success" if added else "warn", msg)

    # ------------------------------------------------------------ обновления
    @pyqtSlot(bool)
    def checkUpdates(self, manual):
        if not manual and self.config.get("last_update_check") == datetime.date.today().isoformat():
            return

        def work():
            resp = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=6,
                                headers={"Accept": "application/vnd.github+json"})
            if resp.status_code == 200:
                data = resp.json()
                tag = (data.get("tag_name") or "").lstrip("vV")
                if tag and is_newer_version(tag, APP_VERSION):
                    return {"available": True, "version": tag,
                            "url": data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest"}
                return {"available": False}
            if resp.status_code == 404:
                return {"available": False}
            raise RuntimeError(f"HTTP {resp.status_code}")

        def done(result, error):
            self.config["last_update_check"] = datetime.date.today().isoformat()
            self.save_config()
            if error:
                if manual:
                    self.toast("error", f"Не удалось проверить обновления ({error}). "
                                        "Возможно, исчерпан лимит запросов GitHub — повторите позже.")
                return
            self._update = {"available": result["available"], "version": result.get("version", ""), "url": result.get("url", "")}
            self.updateChanged.emit()
            if result["available"]:
                self.toast("info", f"Доступна версия {result['version']}. Откройте настройки, чтобы перейти к релизу.")
            elif manual:
                self.toast("success", f"У вас последняя версия ({APP_VERSION}).")

        run_async(work, done)

    @pyqtSlot()
    def openUpdate(self):
        if self._update.get("url"):
            webbrowser.open(self._update["url"])

    @pyqtSlot(str)
    def openUrl(self, url):
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)

    # ------------------------------------------------------------- загрузки
    def _on_download_finished(self, title, folder):
        self.toast("success", f"Манга «{title}» скачана: {folder}")
        self.refresh_library()

    @pyqtSlot()
    def start(self):
        """Первичная загрузка библиотеки и проверка обновлений."""
        self.refresh_library()
        QTimer.singleShot(2500, lambda: self.checkUpdates(False))
