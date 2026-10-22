import os
import re
import zipfile
import hashlib
import logging
import threading
import posixpath
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

from natsort import natsorted

from app.constants import VALID_EXTENSIONS, ARCHIVE_EXTENSIONS, RAR_SUPPORT
from app.cache import BoundedCache, COVER_CACHE

if RAR_SUPPORT:
    import rarfile

from app.constants import COVERS_DIR


# Размер отрисовки страницы PDF. У страниц, собранных book_export, размер в
# пунктах равен размеру исходной картинки в пикселях, так что масштаб 1.0 даёт
# исходное разрешение; мелкие (A4 и т.п.) страницы чужих PDF дотягиваем до
# PDF_MIN_WIDTH, чтобы они не были мыльными.
PDF_MIN_WIDTH = 1400
PDF_MAX_WIDTH = 2400
PDF_MAX_PIXELS = 12_000_000


def _xml_attr(el, name):
    """Значение атрибута без учёта пространства имён (src, xlink:href и т.п.)."""
    for k, v in el.attrib.items():
        if k == name or k.endswith('}' + name):
            return v
    return None


def _xml_tag(el):
    return el.tag.rsplit('}', 1)[-1]


def _zip_join(base_dir, href):
    href = unquote(href.split('#', 1)[0])
    return posixpath.normpath(posixpath.join(base_dir, href)) if href else ''


def read_epub_pages(z):
    """Картинки EPUB (имена внутри zip) в порядке spine из content.opf.

    Рассчитано на fixed-layout мангу, как её собирает book_export.py: с каждой
    XHTML-страницы spine берутся её <img>/<svg:image>; картинка, стоящая прямо
    в spine, тоже считается страницей. У текстовых книг картинок-страниц нет —
    для них список пустой, и библиотека такой файл просто пропускает."""
    names = set(z.namelist())
    container = ET.fromstring(z.read('META-INF/container.xml'))
    opf_path = next((_xml_attr(el, 'full-path') for el in container.iter()
                     if _xml_tag(el) == 'rootfile' and _xml_attr(el, 'full-path')), None)
    if not opf_path:
        return []
    opf_dir = posixpath.dirname(opf_path)
    opf = ET.fromstring(z.read(opf_path))
    manifest, spine = {}, []
    for el in opf.iter():
        tag = _xml_tag(el)
        if tag == 'item' and el.get('id') and el.get('href'):
            manifest[el.get('id')] = (_zip_join(opf_dir, el.get('href')), el.get('media-type', ''))
        elif tag == 'itemref' and el.get('idref'):
            spine.append(el.get('idref'))

    pages, seen = [], set()

    def add(name):
        if name in names and name.lower().endswith(VALID_EXTENSIONS) and name not in seen:
            seen.add(name)
            pages.append(name)

    for idref in spine:
        href, mime = manifest.get(idref, (None, ''))
        if not href or href not in names:
            continue
        if mime.startswith('image/'):
            add(href)
            continue
        try:
            doc = ET.fromstring(z.read(href))
        except ET.ParseError as e:
            logging.error(f"EPUB: не удалось разобрать {href}: {e}")
            continue
        base = posixpath.dirname(href)
        for el in doc.iter():
            tag = _xml_tag(el)
            src = _xml_attr(el, 'src') if tag == 'img' else _xml_attr(el, 'href') if tag == 'image' else None
            if src:
                add(_zip_join(base, src))
    return pages


def _pdf_page_name(i):
    return f"{i + 1:05d}.pdfpage"


def _pdf_render_size(point_size):
    w, h = point_size.width(), point_size.height()
    if w <= 0 or h <= 0:
        return 0, 0
    k = min(max(w, PDF_MIN_WIDTH), PDF_MAX_WIDTH) / w
    if w * h * k * k > PDF_MAX_PIXELS:
        k = (PDF_MAX_PIXELS / (w * h)) ** 0.5
    return max(1, round(w * k)), max(1, round(h * k))


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
        # 'zip' | 'rar' | 'epub' | 'pdf'. EPUB читается как zip, но порядок
        # страниц берётся из spine, а не естественной сортировкой имён.
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
            low = self.path.lower()
            if low.endswith('.epub'): self.real_archive_type = 'epub'
            elif low.endswith('.pdf'): self.real_archive_type = 'pdf'
            elif low.endswith(('.zip', '.cbz')): self.real_archive_type = 'zip'
            else: self.real_archive_type = 'rar'
            return

        if not self.is_archive:
            try:
                self.pages = [f for f in os.listdir(self.path) if f.lower().endswith(VALID_EXTENSIONS)]
            except Exception: self.pages = []
            self.pages = natsorted(self.pages)
            return

        if self.path.lower().endswith('.epub'):
            try:
                with zipfile.ZipFile(self.path, 'r') as z:
                    self.pages = read_epub_pages(z)
                self.real_archive_type = 'epub'
                if not self.pages:
                    logging.info(f"EPUB без страниц-картинок (текстовая книга?) пропущен: {self.path}")
            except Exception as e:
                logging.error(f"Ошибка открытия EPUB {self.path}: {e}")
            # Порядок задаёт spine — natsort здесь его бы сломал.
            if self.pages:
                MangaItem.GLOBAL_CACHE[self.path] = self.pages
            return
        if self.path.lower().endswith('.pdf'):
            doc = self._load_pdf()
            if doc is not None:
                self.pages = [_pdf_page_name(i) for i in range(doc.pageCount())]
                doc.close()
                self.real_archive_type = 'pdf'
            if self.pages:
                MangaItem.GLOBAL_CACHE[self.path] = self.pages
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

    def _load_pdf(self):
        from PyQt6.QtPdf import QPdfDocument
        doc = QPdfDocument(None)
        err = doc.load(self.path)
        if err != QPdfDocument.Error.None_ or doc.pageCount() <= 0:
            logging.error(f"Ошибка открытия PDF {self.path}: {err}")
            doc.close()
            return None
        return doc

    def get_page_size(self, index):
        """(ширина, высота) страницы без её декодирования — пока только для PDF, где
        получить байты страницы значит отрисовать её целиком. None — неизвестно."""
        if self.real_archive_type != 'pdf' or not (0 <= index < len(self.pages)):
            return None
        with self._lock:
            if not self._archive_handle: self.open_archive()
            if not self._archive_handle: return None
            w, h = _pdf_render_size(self._archive_handle.pagePointSize(index))
            return (w, h) if w and h else None

    def _render_pdf_page(self, index):
        """Отрисовка страницы PDF в JPEG-байты (дальше они идут тем же путём, что и картинки из архивов)."""
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize
        from PyQt6.QtGui import QImage, QPainter
        w, h = _pdf_render_size(self._archive_handle.pagePointSize(index))
        if not w or not h:
            return None
        img = self._archive_handle.render(index, QSize(w, h))
        if img.isNull():
            return None
        # Фон страницы PDF бывает прозрачным — подкладываем белый, как любая PDF-читалка.
        if img.hasAlphaChannel():
            flat = QImage(img.size(), QImage.Format.Format_RGB32)
            flat.fill(0xFFFFFFFF)
            p = QPainter(flat)
            p.drawImage(0, 0, img)
            p.end()
            img = flat
        buf = QByteArray()
        dev = QBuffer(buf)
        dev.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(dev, "JPEG", 92)
        dev.close()
        return bytes(buf)

    def open_archive(self):
        if not self.is_archive or self._archive_handle: return
        with self._lock:
            if self._archive_handle: return
            try:
                if self.real_archive_type == 'pdf':
                    self._archive_handle = self._load_pdf()
                elif self.real_archive_type in ('zip', 'epub'):
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
                        if self.real_archive_type == 'pdf':
                            data = self._render_pdf_page(index)
                        else:
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
