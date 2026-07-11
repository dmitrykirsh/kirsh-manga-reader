import os
import re
import zipfile
import hashlib
import logging
import threading
from pathlib import Path

from natsort import natsorted

from app.constants import VALID_EXTENSIONS, ARCHIVE_EXTENSIONS, RAR_SUPPORT
from app.cache import BoundedCache, COVER_CACHE

if RAR_SUPPORT:
    import rarfile

from app.constants import COVERS_DIR


def get_custom_cover_path(item_path):
    if not item_path: return None
    h = hashlib.md5(os.path.abspath(item_path).encode('utf-8')).hexdigest()
    return os.path.join(COVERS_DIR, f"{h}.png")

def get_cover_bytes(item_path, is_folder=True):
    cp = get_custom_cover_path(item_path)
    if cp and os.path.exists(cp):
        try:
            with open(cp, 'rb') as f:
                return f.read()
        except Exception as e:
            logging.error(f"Не удалось прочитать обложку {cp}: {e}")

    if is_folder:
        return find_first_cover_in_folder(item_path)

    if item_path in COVER_CACHE:
        return COVER_CACHE[item_path]
    try:
        manga = MangaItem(item_path)
        data = manga.get_page_data(0)
        manga.close_archive()
        return data
    except Exception as e:
        logging.error(f"Не удалось получить обложку из {item_path}: {e}")
        return None

def find_first_cover_in_folder(folder_path):
    cp = get_custom_cover_path(folder_path)
    if cp and os.path.exists(cp):
        try:
            with open(cp, 'rb') as f: return f.read()
        except Exception as e:
            logging.error(f"Не удалось прочитать кастомную обложку {cp}: {e}")

    if folder_path in COVER_CACHE:
        return COVER_CACHE[folder_path]

    try:
        items = natsorted(os.listdir(folder_path))
    except Exception:
        return None

    for item in items:
        path = os.path.join(folder_path, item)
        if os.path.isfile(path) and item.lower().endswith(ARCHIVE_EXTENSIONS):
            f_cp = get_custom_cover_path(path)
            if f_cp and os.path.exists(f_cp):
                try:
                    with open(f_cp, 'rb') as f: return f.read()
                except Exception as e:
                    logging.error(f"Не удалось прочитать обложку {f_cp}: {e}")
            manga = MangaItem(path)
            if manga.pages:
                data = manga.get_page_data(0)
                manga.close_archive()
                if data:
                    COVER_CACHE[folder_path] = data
                    return data
        elif os.path.isdir(path):
            if item.startswith('.'): continue
            try: sub = os.listdir(path)
            except Exception as e:
                logging.error(f"Не удалось прочитать папку {path}: {e}")
                sub = []

            if any(f.lower().endswith(VALID_EXTENSIONS) for f in sub):
                s_cp = get_custom_cover_path(path)
                if s_cp and os.path.exists(s_cp):
                    try:
                        with open(s_cp, 'rb') as f: return f.read()
                    except Exception as e:
                        logging.error(f"Не удалось прочитать обложку {s_cp}: {e}")
                manga = MangaItem(path)
                if manga.pages:
                    data = manga.get_page_data(0)
                    if data:
                        COVER_CACHE[folder_path] = data
                        return data
            else:
                data = find_first_cover_in_folder(path)
                if data:
                    COVER_CACHE[folder_path] = data
                    return data
    return None

class MangaItem:
    GLOBAL_CACHE = BoundedCache(max_size=300)

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.display_name = os.path.splitext(self.name)[0] if path.lower().endswith(ARCHIVE_EXTENSIONS) else self.name
        self.is_archive = path.lower().endswith(ARCHIVE_EXTENSIONS)
        self.pages = []
        self.real_archive_type = None
        self._archive_handle = None
        # Страницы читаются как из основного потока (при листании), так и из
        # фонового потока предзагрузки (см. ReaderView) — zipfile/rarfile не
        # рассчитаны на конкурентный доступ к одному хендлу, поэтому весь
        # доступ к архиву сериализуется через этот лок. RLock, а не Lock,
        # потому что get_page_data сам вызывает open_archive() из того же потока.
        self._lock = threading.RLock()
        self.load_pages_list()

    def load_pages_list(self):
        if self.path in MangaItem.GLOBAL_CACHE:
            self.pages = MangaItem.GLOBAL_CACHE[self.path]
            if self.path.lower().endswith(('.zip', '.cbz')): self.real_archive_type = 'zip'
            else: self.real_archive_type = 'rar'
            return

        if not self.is_archive:
            try:
                self.pages = [f for f in os.listdir(self.path) if f.lower().endswith(VALID_EXTENSIONS)]
            except Exception: self.pages = []
            self.pages = natsorted(self.pages)
            return

        if self.path.lower().endswith(('.zip', '.cbz')):
            try:
                with zipfile.ZipFile(self.path, 'r') as z:
                    self.pages = [f for f in z.namelist() if f.lower().endswith(VALID_EXTENSIONS)]
                    self.real_archive_type = 'zip'
            except Exception as e_zip_initial:
                logging.error(f"Ошибка открытия ZIP/CBZ как ZIP: {e_zip_initial}")
                if RAR_SUPPORT:
                    try:
                        with rarfile.RarFile(self.path, 'r') as r:
                            self.pages = [f for f in r.namelist() if f.lower().endswith(VALID_EXTENSIONS)]
                            self.real_archive_type = 'rar'
                    except Exception as e_rar_fallback:
                        logging.error(f"Ошибка открытия ZIP/CBZ как RAR (fallback): {e_rar_fallback}")
        elif RAR_SUPPORT and self.path.lower().endswith(('.rar', '.cbr')):
            try:
                with rarfile.RarFile(self.path, 'r') as r:
                    self.pages = [f for f in r.namelist() if f.lower().endswith(VALID_EXTENSIONS)]
                    self.real_archive_type = 'rar'
            except Exception as e:
                logging.error(f"Ошибка открытия RAR/CBR: {e}")

        self.pages = natsorted(self.pages)
        if self.pages:
            MangaItem.GLOBAL_CACHE[self.path] = self.pages

    def open_archive(self):
        if not self.is_archive or self._archive_handle: return
        with self._lock:
            if self._archive_handle: return
            try:
                if self.real_archive_type == 'zip':
                    self._archive_handle = zipfile.ZipFile(self.path, 'r')
                elif self.real_archive_type == 'rar' and RAR_SUPPORT:
                    self._archive_handle = rarfile.RarFile(self.path, 'r')
            except Exception: self._archive_handle = None

    def close_archive(self):
        with self._lock:
            if self._archive_handle:
                try: self._archive_handle.close()
                except Exception as e:
                    logging.error(f"Ошибка в MangaItem: {e}")
                self._archive_handle = None

    def get_page_data(self, index):
        if not self.pages or index < 0 or index >= len(self.pages): return None
        if self.path in COVER_CACHE and index == 0:
            return COVER_CACHE[self.path]
        page_name = self.pages[index]
        with self._lock:
            try:
                if self.is_archive:
                    if not self._archive_handle: self.open_archive()
                    if self._archive_handle:
                        data = self._archive_handle.read(page_name)
                        if index == 0: COVER_CACHE[self.path] = data
                        return data
                else:
                    with open(os.path.join(self.path, page_name), 'rb') as f:
                        data = f.read()
                        if index == 0: COVER_CACHE[self.path] = data
                        return data
            except Exception: return None
        return None


def get_chapter_list(manga):
    """Возвращает список глав, найденных внутри одного файла/папки манги (по вложенным папкам)."""
    chapters = []

    if manga.is_archive:
        try:
            all_names = manga.pages
            candidate_folders = set()
            for name in all_names:
                if '/' in name:
                    folder_path = '/'.join(name.split('/')[:-1])
                    last_folder = folder_path.split('/')[-1]
                    candidate_folders.add(last_folder)

            if candidate_folders:
                if len(candidate_folders) == 1:
                    folder = list(candidate_folders)[0]
                    prefix = f"{folder}/"
                    images = [Path(name).stem for name in all_names if name.startswith(prefix)]
                    chapters = sorted(images)
                else:
                    def extract_num(name):
                        nums = re.findall(r'\d+', name)
                        return int(nums[0]) if nums else 0
                    chapters = sorted(candidate_folders, key=extract_num)
            else:
                chapters = sorted(Path(name).stem for name in all_names)
        except Exception as e:
            logging.error(f"Ошибка чтения архива {manga.path}: {e}")
    else:
        try:
            manga_path = Path(manga.path)
            subdirs = [d for d in manga_path.iterdir() if d.is_dir() and not d.name.startswith('.')]

            if subdirs:
                if len(subdirs) == 1:
                    folder = subdirs[0]
                    images = [f.stem for f in folder.iterdir() if f.suffix.lower() in VALID_EXTENSIONS]
                    chapters = sorted(images)
                else:
                    chapters = [d.name for d in sorted(subdirs)]
            else:
                images = [f.stem for f in manga_path.iterdir() if f.suffix.lower() in VALID_EXTENSIONS]
                chapters = sorted(images)
        except Exception as e:
            logging.error(f"Ошибка чтения папки {manga.path}: {e}")

    return chapters


def get_chapter_groups(manga):
    """Похоже на get_chapter_list, но возвращает None, если у манги нет настоящего деления
    на главы — то есть страницы лежат плоским списком без вложенных папок-групп.
    get_chapter_list в этом случае считает каждую страницу отдельной "главой" (это годится
    для оглавления читалки — быстрый переход к любой странице), но здесь такое поведение
    не подходит: используется, чтобы решить, стоит ли вообще показывать разворачиваемый
    список глав у тома (иначе, например, папка с обложками без подпапок ошибочно
    показывалась бы как том с десятками "глав" — по одной на каждую картинку)."""
    if manga.is_archive:
        try:
            candidate_folders = set()
            for name in manga.pages:
                if '/' in name:
                    folder_path = '/'.join(name.split('/')[:-1])
                    candidate_folders.add(folder_path.split('/')[-1])
            if len(candidate_folders) > 1:
                def extract_num(name):
                    nums = re.findall(r'\d+', name)
                    return int(nums[0]) if nums else 0
                return sorted(candidate_folders, key=extract_num)
        except Exception as e:
            logging.error(f"Ошибка чтения архива {manga.path}: {e}")
        return None
    else:
        try:
            manga_path = Path(manga.path)
            subdirs = [d for d in manga_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
            if len(subdirs) > 1:
                return [d.name for d in sorted(subdirs)]
        except Exception as e:
            logging.error(f"Ошибка чтения папки {manga.path}: {e}")
        return None


def get_first_page_of_chapter(manga, chapter_name):
    """Возвращает индекс первой страницы главы по её имени (из get_chapter_list)."""
    if manga.is_archive:
        try:
            all_files = manga.pages
            for idx, page in enumerate(all_files):
                if Path(page).stem == chapter_name:
                    return idx
            for idx, page in enumerate(all_files):
                if '/' in page:
                    parts = page.split('/')
                    last_folder = parts[-2] if len(parts) >= 2 else None
                    if last_folder == chapter_name:
                        return idx
        except Exception as e:
            logging.error(f"Ошибка поиска главы '{chapter_name}' в архиве {manga.path}: {e}")
    else:
        try:
            manga_path = Path(manga.path)
            all_images = []
            for root, dirs, files in os.walk(manga_path):
                for f in files:
                    if f.lower().endswith(VALID_EXTENSIONS):
                        all_images.append(os.path.join(root, f))
            all_images.sort()

            for idx, img in enumerate(all_images):
                if Path(img).stem == chapter_name:
                    return idx
        except Exception as e:
            logging.error(f"Ошибка поиска главы '{chapter_name}' в папке {manga.path}: {e}")
    return -1
