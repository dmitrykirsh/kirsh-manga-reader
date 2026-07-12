from PyQt6.QtCore import QBuffer, QByteArray, QSize, Qt, QRectF
from PyQt6.QtGui import QImageReader, QPixmap, QPainter, QPainterPath

# Некоторые манхва-страницы — это не отдельная картинка на страницу, а один
# гигантский вертикальный скан на главу целиком (десятки тысяч пикселей в
# высоту при обычной ширине ~1000px). QImage.loadFromData() декодирует такую
# картинку в её нативном разрешении — по 200-250 МБ на одну такую страницу,
# и с учётом кэша чтения и фоновой предзагрузки соседних страниц это забивает
# всю оперативную память и уводит систему в своп (зависает весь ПК, а не
# только программа).
#
# Ограничиваем по ПЛОЩАДИ (ширина×высота), а не по одной стороне — сканы
# такого рода почти квадратные по соотношению высоты к ширине наоборот,
# сильно вытянутые, и урезание по наибольшей стороне непропорционально режет
# именно ширину (единственную ось, где реально нужна детализация при чтении),
# оставляя нечитаемо узкую картинку. Равномерное уменьшение по площади
# сохраняет пропорции и детализацию по обеим осям.
MAX_DECODE_PIXELS = 12_000_000  # ~12 МП — с запасом выше обычной сканированной страницы


def load_image_bounded(data):
    """Декодирует байты картинки в QImage, ограничивая площадь
    MAX_DECODE_PIXELS. Картинки крупнее уменьшаются пропорционально прямо во
    время декодирования через QImageReader.setScaledSize() — без создания
    промежуточной полноразмерной битмапы в памяти."""
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QBuffer.OpenModeFlag.ReadOnly)
    reader = QImageReader(buf)
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        pixels = size.width() * size.height()
        if pixels > MAX_DECODE_PIXELS:
            scale = (MAX_DECODE_PIXELS / pixels) ** 0.5
            reader.setScaledSize(QSize(
                max(1, round(size.width() * scale)),
                max(1, round(size.height() * scale)),
            ))
    image = reader.read()
    buf.close()
    return image


def scale_to_fill(pixmap, width, height):
    """Масштабирует pixmap так, чтобы он РОВНО заполнил width×height, обрезая
    лишнее по центру. QPixmap.scaled(..., KeepAspectRatioByExpanding) даёт
    гарантию "не меньше" заданного размера, а не "ровно" — получившаяся
    картинка может быть шире/выше цели по одной из осей в зависимости от
    исходных пропорций. Это лишнее либо вылезает за границы контейнера, либо
    (что незаметнее и хуже) сдвигает скруглённые углы round_pixmap() за
    пределы видимой области — снаружи это выглядит как "не скруглено",
    хотя маска на самом деле применена правильно, просто не к тому краю."""
    if pixmap.isNull() or width <= 0 or height <= 0:
        return pixmap
    scaled = pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    if scaled.width() == width and scaled.height() == height:
        return scaled
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    return scaled.copy(x, y, width, height)


def round_pixmap(pixmap, radius):
    """Возвращает копию pixmap со скруглёнными углами, обрезанными прямо в
    пикселях. QSS border-radius на QLabel скругляет только фон/рамку самого
    виджета, но НЕ содержимое, нарисованное через setPixmap() — картинка
    поверх всё равно рисуется прямоугольником. Единственный надёжный способ
    в Qt — обрезать сам pixmap через QPainterPath маску."""
    if pixmap.isNull():
        return pixmap
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, pixmap.width(), pixmap.height()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result
