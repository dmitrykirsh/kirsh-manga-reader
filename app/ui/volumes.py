"""Определение структуры серии на диске (тома, главы) — чистые функции без UI.

Перенесено из старого MainWindow: логика та же, но не зависит от виджетов и
принимает config явно."""

import os
import re
import logging

from natsort import natsorted

from app.constants import VALID_EXTENSIONS, ARCHIVE_EXTENSIONS
from app.models import MangaItem, get_chapter_groups

VOL_FOLDER_RE = re.compile(r"^(vol|том)\b", re.IGNORECASE)
_VOLUME_NUM_RE = re.compile(r"\d+")


def format_volume_label(name):
    m = _VOLUME_NUM_RE.search(name)
    if m and re.search(r"vol|том", name, re.IGNORECASE):
        return f"Том {int(m.group())}"
    return name


def is_archive(name):
    return name.lower().endswith(ARCHIVE_EXTENSIONS)


def is_series_folder(folder_path):
    """Папка — серия, если внутри архивы напрямую либо хотя бы один подкаталог (том)
    сам содержит архивы (Hellsing/Том 01/Глава 001.cbr, Made in Abyss/Vol. 01/x.cbz)."""
    try:
        sub_files = os.listdir(folder_path)
    except Exception:
        return False
    for f in sub_files:
        full = os.path.join(folder_path, f)
        if os.path.isfile(full) and is_archive(f):
            return True
        if os.path.isdir(full) and not f.startswith('.'):
            try:
                inner = os.listdir(full)
            except Exception:
                continue
            if any(is_archive(n) and os.path.isfile(os.path.join(full, n)) for n in inner):
                return True
    return False


def classify_volume_folder(folder_path):
    """Список (имя_главы, путь), если папка тома сама состоит из нескольких глав;
    None — если это уже читаемый том (страницы или ровно один архив)."""
    try:
        names = natsorted(os.listdir(folder_path))
    except Exception:
        return None
    archives = [n for n in names if os.path.isfile(os.path.join(folder_path, n)) and is_archive(n)]
    subdirs = [n for n in names if os.path.isdir(os.path.join(folder_path, n)) and not n.startswith('.')]
    has_images = any(n.lower().endswith(VALID_EXTENSIONS) for n in names)

    if has_images and not archives and not subdirs:
        return None
    if len(archives) == 1 and not subdirs:
        return None
    if len(archives) > 1:
        return [(os.path.splitext(n)[0], os.path.join(folder_path, n)) for n in archives]
    if subdirs and not archives:
        return [(n, os.path.join(folder_path, n)) for n in subdirs]
    return None


def resolve_single_archive(folder_path):
    try:
        names = os.listdir(folder_path)
    except Exception:
        return None
    archives = [n for n in names if os.path.isfile(os.path.join(folder_path, n)) and is_archive(n)]
    return os.path.join(folder_path, archives[0]) if len(archives) == 1 else None


def build_volume_entry(name, path):
    """Обычный том. Если он сам разбит на главы внутри (Highschool of the Dead:
    vol1.cbz содержит Ch_NNN) — entry["internal"]=True."""
    entry = {"name": name, "path": path, "chapters": None, "internal": False}
    try:
        manga = MangaItem(path)
        if manga.pages:
            internal = get_chapter_groups(manga)
            if internal:
                entry["chapters"] = [(ch, None) for ch in internal]
                entry["internal"] = True
    except Exception as e:
        logging.error(f"Не удалось проверить внутренние главы {path}: {e}")
    return entry


def compute_local_volumes(folder_path):
    """Список томов папки-серии: dict {"name","path","chapters","internal"}.
    chapters None → path читается целиком; internal=False → главы — отдельные файлы;
    internal=True → главы внутри одного файла (различаются стартовой страницей).
    Если есть и архив, и одноимённая папка — основным считается архив."""
    try:
        names = natsorted(os.listdir(folder_path))
    except Exception:
        return []
    archive_stems = {
        os.path.splitext(n)[0] for n in names
        if os.path.isfile(os.path.join(folder_path, n)) and is_archive(n)
    }
    volumes, seen = [], set()
    for name in names:
        path = os.path.join(folder_path, name)
        if os.path.isfile(path) and is_archive(name):
            stem = os.path.splitext(name)[0]
            if stem in seen:
                continue
            seen.add(stem)
            volumes.append(build_volume_entry(stem, path))
        elif os.path.isdir(path) and not name.startswith('.'):
            if name in archive_stems or name in seen:
                continue
            seen.add(name)
            chapters = classify_volume_folder(path)
            if chapters is not None:
                volumes.append({"name": name, "path": None, "chapters": chapters, "internal": False})
            else:
                single = resolve_single_archive(path)
                volumes.append(build_volume_entry(name, single or path))
    return volumes


def series_has_progress(progress, local_volumes, fallback_path):
    paths = [fallback_path]
    for entry in local_volumes:
        if entry.get("chapters"):
            paths.extend(p for _, p in entry["chapters"] if p)
        if entry.get("path"):
            paths.append(entry["path"])
    for p in paths:
        prog = progress.get(p, {})
        if isinstance(prog, dict) and prog.get("page", 0):
            return True
    return False


def find_last_progress(progress, local_volumes):
    """Путь и данные прогресса последнего (по порядку томов) элемента, у которого он есть."""
    best = None
    for entry in local_volumes:
        cands = []
        if entry.get("chapters") and not entry.get("internal"):
            cands.extend(p for _, p in entry["chapters"] if p)
        elif entry.get("path"):
            cands.append(entry["path"])
        for p in cands:
            prog = progress.get(p)
            if isinstance(prog, dict) and prog.get("page", 0):
                best = (p, prog)
    return best


def next_sibling(current_path, root_dir):
    """Следующий по порядку файл/папка-глава рядом с текущим (только внутри папки-серии,
    а не в корне библиотеки, где соседи — это чужие тайтлы)."""
    parent_dir = os.path.dirname(current_path)
    if root_dir and os.path.normpath(parent_dir) == os.path.normpath(root_dir):
        return None
    try:
        siblings = natsorted([
            os.path.join(parent_dir, f) for f in os.listdir(parent_dir)
            if (os.path.isfile(os.path.join(parent_dir, f)) and is_archive(f))
            or (os.path.isdir(os.path.join(parent_dir, f)) and not f.startswith('.'))
        ])
        idx = siblings.index(current_path)
        return siblings[idx + 1] if idx < len(siblings) - 1 else None
    except Exception:
        return None
