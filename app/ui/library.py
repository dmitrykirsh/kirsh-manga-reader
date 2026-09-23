"""Данные библиотеки: сборка карточек (в фоне) и модель для QML-сетки."""

import os
import logging

from natsort import natsorted
from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, QByteArray

from app.constants import VALID_EXTENSIONS, ARCHIVE_EXTENSIONS
from app.models import MangaItem
from app.ui import volumes
from app.ui.providers import cover_url

STATUS_LABELS = {
    "none": "Без статуса", "reading": "Читаю", "completed": "Прочитано",
    "planned": "В планах", "dropped": "Брошено",
}


def folder_progress(progress, folder_path):
    total = read = 0
    try:
        for root, dirs, files in os.walk(folder_path):
            has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in files)
            has_archives = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in files)
            valid_dirs = [d for d in dirs if not d.startswith('.')]
            targets = []
            if has_images and not has_archives and not valid_dirs:
                targets.append(root)
            else:
                targets.extend(os.path.join(root, f) for f in files if f.lower().endswith(ARCHIVE_EXTENSIONS))
            for p in targets:
                pages = len(MangaItem(p).pages)
                total += pages
                data = progress.get(p)
                if isinstance(data, dict):
                    read += min(data.get("page", 0) + 1, pages)
    except Exception as e:
        logging.error(f"Ошибка подсчёта прогресса папки {folder_path}: {e}")
    return read, total


def _meta(config, path):
    m = config.get("metadata", {}).get(path, {})
    return m.get("status", "none"), m.get("rating")


def _entry(config, cover_ver, kind, path, name, page, total, action):
    status, rating = _meta(config, path)
    return {
        "kind": kind, "path": path, "name": name, "page": page, "total": total,
        "progress": (min(1.0, (page + 1) / total) if total and page > 0 else 0.0) if kind == "manga"
        else (min(1.0, page / total) if total else 0.0),
        "status": status, "statusLabel": STATUS_LABELS.get(status, ""), "rating": rating or 0,
        "cover": cover_url(path, kind == "folder", cover_ver.get(path, 0)),
        "open": action,
    }


def _manga_entry(config, cover_ver, path, action):
    manga = MangaItem(path)
    if not manga.pages:
        return None
    prog = config.get("progress", {}).get(path, {})
    page = prog.get("page", 0) if isinstance(prog, dict) else 0
    return _entry(config, cover_ver, "manga", path, manga.display_name, page, len(manga.pages), action)


def _folder_entry(config, cover_ver, path, action):
    read, total = folder_progress(config.get("progress", {}), path)
    return _entry(config, cover_ver, "folder", path, os.path.basename(path), read, total, action)


def scan_directory(config, cover_ver, target_dir):
    """Вкладка «Библиотека»: содержимое одной папки."""
    entries = []
    try:
        raw = os.listdir(target_dir)
    except Exception as e:
        logging.error(f"Ошибка чтения папки {target_dir}: {e}")
        return entries
    for item in natsorted(raw):
        path = os.path.join(target_dir, item)
        if os.path.isfile(path) and item.lower().endswith(ARCHIVE_EXTENSIONS):
            e = _manga_entry(config, cover_ver, path, "info")
            if e:
                entries.append(e)
        elif os.path.isdir(path) and not item.startswith('.'):
            try:
                sub = os.listdir(path)
            except Exception:
                sub = []
            has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in sub)
            has_archives = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in sub)
            has_subdirs = any(os.path.isdir(os.path.join(path, d)) for d in sub)
            if has_images and not has_archives and not has_subdirs:
                e = _manga_entry(config, cover_ver, path, "info")
            else:
                series = has_archives or volumes.is_series_folder(path)
                e = _folder_entry(config, cover_ver, path, "series" if series else "enter")
            if e:
                entries.append(e)
    return entries


def scan_flat(config, cover_ver, mode):
    """Вкладки «Продолжить чтение», «Завершено», «В планах» — верхний уровень корня."""
    root = config.get("root_dir")
    progress = config.get("progress", {})
    if not root or not os.path.exists(root):
        return []
    entries = []

    def add_path(item_path, folder_action, manga_action):
        if os.path.isfile(item_path) and item_path.lower().endswith(ARCHIVE_EXTENSIONS):
            e = _manga_entry(config, cover_ver, item_path, manga_action)
        elif os.path.isdir(item_path):
            e = _folder_entry(config, cover_ver, item_path, folder_action)
        else:
            return
        if e:
            entries.append(e)

    try:
        raw = [i for i in os.listdir(root) if not i.startswith('.')]
    except Exception:
        raw = []

    if mode == "reading":
        tops = set()
        for path, data in progress.items():
            if not os.path.exists(path) or not isinstance(data, dict):
                continue
            if 0 < data.get("page", 0) < (data.get("total", 0) - 1):
                rel = os.path.relpath(path, root)
                if not rel.startswith(".."):
                    tops.add(os.path.join(root, rel.split(os.sep)[0]))
        for p in natsorted(tops):
            add_path(p, "continue", "info")
    elif mode == "planned":
        planned = [os.path.join(root, i) for i in raw
                   if config.get("metadata", {}).get(os.path.join(root, i), {}).get("status") == "planned"]
        for p in natsorted(planned):
            add_path(p, "planned", "info")
    else:
        done = set()
        for item in raw:
            p = os.path.join(root, item)
            if os.path.isfile(p) and p.lower().endswith(ARCHIVE_EXTENSIONS):
                d = progress.get(p)
                if isinstance(d, dict) and d.get("total", 0) > 0 and d.get("page", 0) >= d["total"] - 1:
                    done.add(p)
            elif os.path.isdir(p):
                read, total = folder_progress(progress, p)
                if total > 0 and read >= total - 5:
                    done.add(p)
        for p in natsorted(done):
            add_path(p, "completed", "end")
    return entries


class LibraryModel(QAbstractListModel):
    ROLES = ["kind", "path", "name", "page", "total", "progress", "status", "statusLabel", "rating", "cover", "open"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all = []
        self._shown = []
        self._filter = ""
        self._role_ids = {Qt.ItemDataRole.UserRole + 1 + i: n for i, n in enumerate(self.ROLES)}

    def roleNames(self):
        return {rid: QByteArray(n.encode()) for rid, n in self._role_ids.items()}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._shown)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._shown):
            return None
        name = self._role_ids.get(role)
        return self._shown[index.row()].get(name) if name else None

    def entry(self, row):
        return self._shown[row] if 0 <= row < len(self._shown) else None

    def set_entries(self, entries):
        self._all = entries
        self._apply()

    def set_filter(self, text):
        self._filter = (text or "").lower().strip()
        self._apply()

    def total_count(self):
        return len(self._all)

    def shown_count(self):
        return len(self._shown)

    def _apply(self):
        self.beginResetModel()
        f = self._filter
        self._shown = [e for e in self._all if not f or f in e["name"].lower()]
        self.endResetModel()
