"""QQuickImageProvider'ы: иконки (SVG → QImage), обложки и страницы читалки.

Все провайдеры работают синхронно в потоках загрузки изображений QML —
QML сам не блокируется, пока страница декодируется."""

import logging

from PyQt6.QtCore import Qt, QSize, QByteArray
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtQuick import QQuickImageProvider
from PyQt6.QtSvg import QSvgRenderer

from app.image_utils import load_image_bounded
from app.models import get_cover_bytes

# Контурные иконки 24×24 (Lucide). Толщина штриха и заливка задаются при отрисовке:
# outline — состояние по умолчанию, fill (лёгкая заливка) — «активно».
ICONS = {
    "library": '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>',
    "continue": '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
    "done": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "planned": '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    "settings": '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "close": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "back": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "up": '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "more": '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "star": '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "edit": '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>',
    "image": '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    "list": '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>',
    "rows": '<rect width="18" height="7" x="3" y="3" rx="1"/><rect width="18" height="7" x="3" y="14" rx="1"/>',
    "page": '<rect width="14" height="18" x="5" y="3" rx="2"/>',
    "maximize": '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "minus": '<path d="M5 12h14"/>',
    "warning": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "keyboard": '<path d="M10 8h.01"/><path d="M12 12h.01"/><path d="M14 8h.01"/><path d="M16 12h.01"/><path d="M18 8h.01"/><path d="M6 8h.01"/><path d="M7 16h10"/><path d="M8 12h.01"/><rect width="20" height="16" x="2" y="4" rx="2"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "key": '<path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/><path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/>',
    "palette": '<path d="M12 22a1 1 0 0 1 0-20 10 9 0 0 1 10 9 5 5 0 0 1-5 5h-2.25a1.75 1.75 0 0 0-1.4 2.8l.3.4a1.75 1.75 0 0 1-1.4 2.8z"/><circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/>',
    "zoom": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/>',
    "bookmark": '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>',
    # Фирменный знак приложения: раскрытая книга с закладкой — вместо буквы «K».
    "logo": '<path d="M10 2v8l3-3 3 3V2"/><path d="M4 19.5V4a2 2 0 0 1 2-2h13a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a2.5 2.5 0 0 1 0-5H20"/>',
}


class IconProvider(QQuickImageProvider):
    """image://icon/<name>/<rrggbb>/<size>/<stroke>/<fill 0|1>"""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._cache = {}

    def requestImage(self, id, requestedSize):
        parts = id.split("?")[0].split("/")
        try:
            name = parts[0]
            color = parts[1][-6:] if len(parts) > 1 else "ffffff"
            px = int(float(parts[2])) if len(parts) > 2 else 24
            stroke = parts[3] if len(parts) > 3 else "1.75"
            fill = parts[4] == "1" if len(parts) > 4 else False
        except Exception:
            name, color, px, stroke, fill = "info", "ffffff", 24, "1.75", False
        dpr = 2
        key = (name, color, px, stroke, fill)
        img = self._cache.get(key)
        if img is None:
            fill_attr = f'fill="#{color}" fill-opacity="0.22"' if fill else 'fill="none"'
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {fill_attr} '
                   f'stroke="#{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
                   f'{ICONS.get(name, "")}</svg>')
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            img = QImage(px * dpr, px * dpr, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(p)
            p.end()
            self._cache[key] = img
        return img, QSize(img.width(), img.height())


def encode_path(path):
    return path.encode("utf-8").hex()


def decode_path(token):
    return bytes.fromhex(token).decode("utf-8")


def cover_url(path, is_folder, version=0):
    return f"image://cover/{'f' if is_folder else 'm'}/{encode_path(path)}?v={version}"


class CoverProvider(QQuickImageProvider):
    """image://cover/<f|m>/<hex path>?v=N — обложка папки (f) или файла манги (m)."""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, id, requestedSize):
        empty = QImage()
        try:
            kind, token = id.split("?")[0].split("/", 1)
            path = decode_path(token)
            data = get_cover_bytes(path, is_folder=(kind == "f"))
        except Exception as e:
            logging.error(f"Обложка: не удалось разобрать {id}: {e}")
            return empty, QSize()
        if not data:
            return empty, QSize()
        img = load_image_bounded(data)
        if img.isNull():
            return empty, QSize()
        if requestedSize.width() > 0 and img.width() > requestedSize.width():
            img = img.scaledToWidth(requestedSize.width(), Qt.TransformationMode.SmoothTransformation)
        return img, QSize(img.width(), img.height())


class PageProvider(QQuickImageProvider):
    """image://page/<gen>/<index> — страница текущей открытой манги."""

    def __init__(self, reader):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._reader = reader

    def requestImage(self, id, requestedSize):
        try:
            gen, idx = id.split("?")[0].split("/")
            manga = self._reader.manga_for_gen(int(gen))
            if manga is None:
                return QImage(), QSize()
            data = manga.get_page_data(int(idx))
        except Exception as e:
            logging.error(f"Страница: не удалось разобрать {id}: {e}")
            return QImage(), QSize()
        if not data:
            return QImage(), QSize()
        img = load_image_bounded(data)
        if img.isNull():
            return QImage(), QSize()
        if requestedSize.width() > 0 and img.width() > requestedSize.width():
            img = img.scaledToWidth(requestedSize.width(), Qt.TransformationMode.SmoothTransformation)
        return img, QSize(img.width(), img.height())
