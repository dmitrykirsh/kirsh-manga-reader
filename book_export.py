"""Сборка скачанной манги (папки с картинками) в EPUB или PDF.

Загрузчики складывают главы в папки: vol<N>/<глава> (MangaLib, MangaHub, ReadManga)
или Ch_<NNN> (Com-X). Любая папка, где есть картинки, считается главой; порядок —
естественная сортировка путей. Работает в фоновом потоке, без сторонних библиотек:
EPUB — обычный zip с XHTML, PDF — через QPdfWriter.
"""
import os
import re
import uuid
import html
import zipfile
import datetime

from natsort import natsorted
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QRectF, QSizeF
from PyQt6.QtGui import QImage, QImageReader, QPageLayout, QPageSize, QPainter, QPdfWriter

IMG_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
# Форматы, которые EPUB-читалки обязаны понимать; остальное перекодируем в JPEG.
EPUB_NATIVE = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif'}
PDF_MAX_PT = 14000  # предел размера страницы PDF — 14400 pt (200 дюймов)


class ExportCancelled(Exception):
    pass


def chapter_label(rel):
    parts = [p for p in re.split(r'[\\/]', rel) if p and p != '.']
    if not parts:
        return "Глава 1"
    m = re.fullmatch(r'Ch_0*(\d+)', parts[-1])
    if m:
        return f"Глава {m.group(1)}"
    if len(parts) >= 2:
        v = re.fullmatch(r'vol(.+)', parts[-2])
        if v:
            return f"Том {v.group(1)}, глава {parts[-1]}"
    return " / ".join(parts)


def collect_chapters(folder):
    """[(название главы, [пути к страницам])] в порядке чтения."""
    found = []
    for root, _dirs, files in os.walk(folder):
        pages = natsorted(f for f in files if f.lower().endswith(IMG_EXTS))
        if pages:
            found.append((os.path.relpath(root, folder), [os.path.join(root, f) for f in pages]))
    return [(chapter_label(rel), pages) for rel, pages in natsorted(found, key=lambda c: c[0])]


def export_book(folder, out_path, title, fmt, progress=None, should_stop=None):
    """fmt: "EPUB" или "PDF". progress(done, total) — по страницам. Возвращает out_path."""
    chapters = collect_chapters(folder)
    if not chapters:
        raise RuntimeError("в папке нет картинок")
    tmp = out_path + ".part"
    try:
        if fmt == "PDF":
            _export_pdf(chapters, tmp, title, progress, should_stop)
        else:
            _export_epub(chapters, tmp, title, progress, should_stop)
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return out_path


def _tick(progress, should_stop, done, total):
    if should_stop and should_stop():
        raise ExportCancelled()
    if progress:
        progress(done, total)


# ------------------------------------------------------------------ PDF

def _export_pdf(chapters, out_path, title, progress, should_stop):
    pages = [p for _, ps in chapters for p in ps]
    writer = QPdfWriter(out_path)
    writer.setCreator("Kirsh Manga Reader")
    writer.setTitle(title)
    writer.setResolution(72)  # 1 пиксель картинки = 1 пункт страницы
    painter = None
    try:
        for i, path in enumerate(pages, 1):
            _tick(progress, should_stop, i - 1, len(pages))
            img = QImage(path)
            if img.isNull():
                continue
            w, h = float(img.width()), float(img.height())
            k = min(1.0, PDF_MAX_PT / max(w, h))  # длинные вебтун-страницы ужимаем до предела PDF
            w, h = w * k, h * k
            # QPageSize хранит размер в книжной ориентации — широкие страницы задаём через Landscape.
            if w > h:
                layout = QPageLayout(QPageSize(QSizeF(h, w), QPageSize.Unit.Point, "", QPageSize.SizeMatchPolicy.ExactMatch),
                                     QPageLayout.Orientation.Landscape, QMarginsF(0, 0, 0, 0))
            else:
                layout = QPageLayout(QPageSize(QSizeF(w, h), QPageSize.Unit.Point, "", QPageSize.SizeMatchPolicy.ExactMatch),
                                     QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))
            writer.setPageLayout(layout)
            if painter is None:
                painter = QPainter(writer)
            else:
                writer.newPage()
            painter.drawImage(QRectF(0, 0, w, h), img)
        if painter is None:
            raise RuntimeError("не удалось прочитать ни одной картинки")
        _tick(progress, should_stop, len(pages), len(pages))
    finally:
        if painter is not None:
            painter.end()


# ------------------------------------------------------------------ EPUB

def _image_bytes(path):
    """(байты, расширение, mime, ширина, высота) — с перекодированием в JPEG, если формат не родной для EPUB."""
    ext = os.path.splitext(path)[1].lower()
    if ext in EPUB_NATIVE:
        size = QImageReader(path).size()
        with open(path, 'rb') as f:
            return f.read(), ext, EPUB_NATIVE[ext], size.width(), size.height()
    img = QImage(path)
    if img.isNull():
        return None
    buf = QByteArray()
    dev = QBuffer(buf)
    dev.open(QIODevice.OpenModeFlag.WriteOnly)
    img.convertToFormat(QImage.Format.Format_RGB888).save(dev, "JPEG", 90)
    dev.close()
    return bytes(buf), '.jpg', 'image/jpeg', img.width(), img.height()


_PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ru" lang="ru">
<head>
<meta charset="UTF-8"/>
<title>{title}</title>
<meta name="viewport" content="width={w}, height={h}"/>
<style>html, body {{ margin: 0; padding: 0; }} img {{ display: block; width: 100%; height: 100%; object-fit: contain; }}</style>
</head>
<body><img src="../images/{img}" alt=""/></body>
</html>
"""


def _export_epub(chapters, out_path, title, progress, should_stop):
    total = sum(len(ps) for _, ps in chapters)
    book_id = f"urn:uuid:{uuid.uuid4()}"
    esc_title = html.escape(title)
    manifest, spine, toc = [], [], []
    n = 0
    with zipfile.ZipFile(out_path, 'w') as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
                   '</container>\n', compress_type=zipfile.ZIP_DEFLATED)
        for ch_title, pages in chapters:
            first_in_chapter = True
            for path in pages:
                _tick(progress, should_stop, n, total)
                data = _image_bytes(path)
                if data is None:
                    continue
                raw, ext, mime, w, h = data
                n += 1
                img_name, page_name = f"p{n:05d}{ext}", f"p{n:05d}.xhtml"
                z.writestr(f"OEBPS/images/{img_name}", raw, compress_type=zipfile.ZIP_STORED)
                z.writestr(f"OEBPS/pages/{page_name}",
                           _PAGE.format(title=esc_title, w=w, h=h, img=img_name), compress_type=zipfile.ZIP_DEFLATED)
                props = ' properties="cover-image"' if n == 1 else ''
                manifest.append(f'<item id="img{n}" href="images/{img_name}" media-type="{mime}"{props}/>')
                manifest.append(f'<item id="pg{n}" href="pages/{page_name}" media-type="application/xhtml+xml"/>')
                spine.append(f'<itemref idref="pg{n}"/>')
                if first_in_chapter:
                    toc.append((html.escape(ch_title), f"pages/{page_name}"))
                    first_in_chapter = False
        if n == 0:
            raise RuntimeError("не удалось прочитать ни одной картинки")

        nav_items = "\n".join(f'<li><a href="{href}">{t}</a></li>' for t, href in toc)
        z.writestr("OEBPS/nav.xhtml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
                   '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ru" lang="ru">\n'
                   f'<head><meta charset="UTF-8"/><title>{esc_title}</title></head>\n'
                   f'<body><nav epub:type="toc" id="toc"><h1>{esc_title}</h1><ol>\n{nav_items}\n</ol></nav></body>\n</html>\n',
                   compress_type=zipfile.ZIP_DEFLATED)
        nav_points = "\n".join(
            f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{t}</text></navLabel><content src="{href}"/></navPoint>'
            for i, (t, href) in enumerate(toc, 1))
        z.writestr("OEBPS/toc.ncx",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
                   f'<head><meta name="dtb:uid" content="{book_id}"/></head>\n'
                   f'<docTitle><text>{esc_title}</text></docTitle>\n<navMap>\n{nav_points}\n</navMap>\n</ncx>\n',
                   compress_type=zipfile.ZIP_DEFLATED)
        modified = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        z.writestr("OEBPS/content.opf",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ru"'
                   ' prefix="rendition: http://www.idpf.org/vocab/rendition/#">\n'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
                   f'<dc:identifier id="bookid">{book_id}</dc:identifier>\n'
                   f'<dc:title>{esc_title}</dc:title>\n<dc:language>ru</dc:language>\n'
                   f'<meta property="dcterms:modified">{modified}</meta>\n'
                   '<meta property="rendition:layout">pre-paginated</meta>\n'
                   '<meta property="rendition:spread">none</meta>\n'
                   '<meta name="cover" content="img1"/>\n'
                   '</metadata>\n<manifest>\n'
                   '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
                   '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
                   + "\n".join(manifest) +
                   '\n</manifest>\n<spine toc="ncx">\n' + "\n".join(spine) + '\n</spine>\n</package>\n',
                   compress_type=zipfile.ZIP_DEFLATED)
    _tick(progress, should_stop, total, total)
