import logging
import re
import html

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QInputDialog, QMenu, QFrame,
    QGraphicsDropShadowEffect, QLayout, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QColor, QAction
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QRect, QSize, QPoint
import requests

from app import info_data
from app import theme
from app.models import get_chapter_list, get_first_page_of_chapter, get_cover_bytes
from app.image_utils import round_pixmap, scale_to_fill
from app.library_cards import STATUS_LABELS, RATING_LABELS, _add_status_actions, _add_rating_actions

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_VOLUME_NUM_RE = re.compile(r"\d+")

STATUS_TEXT = dict(STATUS_LABELS)
RATING_TEXT = dict(RATING_LABELS)


class FlowLayout(QLayout):
    """Раскладка, переносящая дочерние виджеты на новую строку по мере
    нехватки ширины — для плашек жанров, которых может быть и 3, и 12,
    заранее неизвестно сколько влезет в одну строку."""

    def __init__(self, parent=None, margin=0, h_spacing=8, v_spacing=8):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + bottom


def _description_to_html(text):
    if not text:
        return ""
    parts = []
    last_end = 0
    for m in _MD_LINK_RE.finditer(text):
        parts.append(html.escape(text[last_end:m.start()]))
        parts.append(f'<a href="{html.escape(m.group(2))}">{html.escape(m.group(1))}</a>')
        last_end = m.end()
    parts.append(html.escape(text[last_end:]))
    return "".join(parts).replace("\n", "<br>")


def _format_volume_label(name):
    m = _VOLUME_NUM_RE.search(name)
    if m and re.search(r"vol|том", name, re.IGNORECASE):
        return f"Том {int(m.group())}"
    return name


STATUS_RU = {
    "ongoing": "Продолжается",
    "completed": "Завершено",
    "hiatus": "Приостановлено",
    "cancelled": "Отменено",
}

CONTENT_RATING_RU = {
    "safe": None,
    "suggestive": None,
    "erotica": "🔞 18+",
    "pornographic": "🔞 18+",
}


class InfoFetchWorker(QThread):
    finished_ok = pyqtSignal(dict)
    finished_error = pyqtSignal(str)

    def __init__(self, fetch_fn):
        super().__init__()
        self.fetch_fn = fetch_fn

    def run(self):
        try:
            result = self.fetch_fn()
            if result is None:
                self.finished_error.emit("Ничего не найдено")
            else:
                self.finished_ok.emit(result)
        except Exception as e:
            logging.error(f"Ошибка загрузки информации о манге: {e}")
            self.finished_error.emit(str(e))


class InfoPage(QWidget):
    back_clicked = pyqtSignal()
    read_clicked = pyqtSignal(object)
    status_rating_changed = pyqtSignal(str, str)
    volume_selected = pyqtSignal(str)
    chapter_selected = pyqtSignal(str, str)
    read_file_requested = pyqtSignal(str)
    menu_action_triggered = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.current_manga = None
        self._worker = None
        self._current_status = "none"
        self._current_rating = None
        self._cache_key = None
        self._local_volumes = []
        self._fetch_source = "mangadex"
        self._local_chapters = []
        self._cover_pixmap_cache = {}
        self._fetch_token = 0
        self._cover_token = 0

        self._preset = theme.get_preset(theme.PRESET_ORDER[0])
        self._current_genres = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_panel = QWidget()
        top_panel.setObjectName("TopPanel")
        top_panel.setStyleSheet("QWidget#TopPanel { border-bottom: 1px solid rgba(255,255,255,0.08); }")
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(15, 8, 15, 8)

        self.btn_back = QPushButton("← В библиотеку")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        top_layout.addWidget(self.btn_back)

        self.btn_refresh = QPushButton("🔄 Обновить")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.force_refresh)
        top_layout.addWidget(self.btn_refresh)

        self.btn_change_link = QPushButton("🔗 Изменить ссылку")
        self.btn_change_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_link.clicked.connect(self.change_mal_link)
        top_layout.addWidget(self.btn_change_link)

        top_layout.addStretch()

        self.btn_menu = QPushButton("⋮")
        self.btn_menu.setObjectName("IconMenuButton")
        self.btn_menu.setFixedSize(36, 34)
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.setToolTip("Действия с мангой")
        self.btn_menu.clicked.connect(self._show_item_menu)
        top_layout.addWidget(self.btn_menu)

        main_layout.addWidget(top_panel)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(28, 28, 28, 28)
        body_layout.setSpacing(32)

        # --- Обложка: крупнее, с мягкой тенью, чтобы "выступала" над фоном ---
        # Тень — единственный QGraphicsEffect на этой странице. Раньше сюда же
        # добавлялся QGraphicsOpacityEffect на fade-in всей страницы, обёрнутый
        # вокруг этого блока — Qt не умеет корректно рисовать вложенные друг в
        # друга эффекты (тень на дочернем виджете внутри виджета с opacity-
        # эффектом), из-за чего обложка переставала отрисовываться вообще.
        cover_col = QVBoxLayout()
        cover_col.setSpacing(0)
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(300, 430)
        self.cover_label.setObjectName("CoverLabel")
        self.cover_label.setStyleSheet(
            "QLabel#CoverLabel { background: rgba(255,255,255,0.06); border-radius: 14px; }"
        )
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setScaledContents(False)
        cover_shadow = QGraphicsDropShadowEffect(self.cover_label)
        cover_shadow.setBlurRadius(36)
        cover_shadow.setOffset(0, 10)
        cover_shadow.setColor(QColor(0, 0, 0, 160))
        self.cover_label.setGraphicsEffect(cover_shadow)
        cover_col.addWidget(self.cover_label)
        # Без stretch снизу QHBoxLayout центрирует cover_col по высоте всей
        # строки (а строка высокая — задаётся правой колонкой с описанием и
        # списками) — обложка "плавала" в середине вместо того, чтобы стоять
        # у верхнего края рядом с заголовком.
        cover_col.addStretch()
        body_layout.addLayout(cover_col, 0)
        body_layout.setAlignment(cover_col, Qt.AlignmentFlag.AlignTop)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        # "Hero" — заголовок и статус/оценка сидят на мягкой градиентной
        # подложке пресета, а не на голом фоне страницы — раньше вся правая
        # колонка была плоской, без единого цветового акцента наверху.
        self.hero_frame = QFrame()
        self.hero_frame.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(self.hero_frame)
        hero_layout.setContentsMargins(20, 18, 20, 18)
        hero_layout.setSpacing(10)
        right_col.addWidget(self.hero_frame)

        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        # background:transparent — иначе лейбл наследует сплошной фон страницы
        # из глобального QWidget {background-color:...} и рисует тёмный
        # прямоугольник поверх градиентной подложки hero-блока.
        self.title_label.setStyleSheet(
            f"background: transparent; color: {theme.TEXT_PRIMARY}; "
            f"font-size: {theme.FONT_DISPLAY + 4}px; font-weight: 800; letter-spacing: 0.3px;"
        )
        hero_layout.addWidget(self.title_label)

        self.original_title_label = QLabel("")
        self.original_title_label.setWordWrap(True)
        self.original_title_label.setStyleSheet(
            f"background: transparent; color: {theme.TEXT_MUTED}; "
            f"font-style: italic; font-size: {theme.FONT_TITLE}px;"
        )
        hero_layout.addWidget(self.original_title_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.btn_status = QPushButton()
        self.btn_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_status.clicked.connect(self._show_status_menu)
        status_row.addWidget(self.btn_status)

        self.btn_rating = QPushButton()
        self.btn_rating.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rating.clicked.connect(self._show_rating_menu)
        status_row.addWidget(self.btn_rating)

        status_row.addStretch()
        hero_layout.addLayout(status_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background-color: #4a2f1a; color: #ffcc80; padding: 10px 14px; "
            "border-radius: 8px; border: 1px solid #ff9800; font-size: 13px;"
        )
        self.status_label.hide()
        right_col.addWidget(self.status_label)

        # Жанры — отдельные цветные плашки, а не текст через запятую.
        # Количество жанров заранее не известно, поэтому обёртка сама
        # переносит их на следующую строку по мере нехватки места (FlowLayout).
        self.genres_frame = QWidget()
        self._genres_flow = FlowLayout(self.genres_frame, margin=0, h_spacing=8, v_spacing=8)
        right_col.addWidget(self.genres_frame)
        self.genres_frame.hide()

        # Плашка метаданных — раньше была ЕДВА темнее фона страницы (почти не
        # видна) с таблицей текста внутри. Теперь однозначно тёмная карточка,
        # а каждое поле (автор/статус/год...) — отдельная плашка на градиенте,
        # той же природы, что и плашки жанров, но ярче и с двухцветной заливкой.
        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("MetaCard")
        self.meta_frame.setFrameShape(QFrame.Shape.NoFrame)
        meta_frame_layout = QVBoxLayout(self.meta_frame)
        meta_frame_layout.setContentsMargins(18, 16, 18, 16)
        self.meta_chips_frame = QWidget()
        self._meta_flow = FlowLayout(self.meta_chips_frame, margin=0, h_spacing=8, v_spacing=8)
        meta_frame_layout.addWidget(self.meta_chips_frame)
        right_col.addWidget(self.meta_frame)

        self.btn_read = QPushButton("▶   Читать")
        self.btn_read.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_read.clicked.connect(lambda: self.current_manga and self.read_clicked.emit(self.current_manga))
        right_col.addWidget(self.btn_read, 0, Qt.AlignmentFlag.AlignLeft)
        self._has_progress = False

        # "Блоки" — локальные тома, главы в файле, описание и главы на
        # MangaDex/MAL — все одной и той же тёмной карточной системы, что и
        # плашка метаданных, а не голые списки прямо на фоне страницы.
        self.volumes_frame, volumes_inner = self._make_card("Локальные тома")
        self.volumes_list = QTreeWidget()
        self.volumes_list.setHeaderHidden(True)
        self.volumes_list.setMaximumHeight(220)
        self.volumes_list.itemClicked.connect(self._on_volume_clicked)
        volumes_inner.addWidget(self.volumes_list)
        right_col.addWidget(self.volumes_frame)
        self.volumes_frame.hide()

        self.local_chapters_frame, local_chapters_inner = self._make_card("Главы в файле")
        self.local_chapters_list = QListWidget()
        self.local_chapters_list.setMaximumHeight(150)
        self.local_chapters_list.itemDoubleClicked.connect(self._on_local_chapter_double_clicked)
        local_chapters_inner.addWidget(self.local_chapters_list)
        right_col.addWidget(self.local_chapters_frame)
        self.local_chapters_frame.hide()

        self.description_frame, description_inner = self._make_card("Описание")
        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        self.description_label.setTextFormat(Qt.TextFormat.RichText)
        self.description_label.setOpenExternalLinks(True)
        self.description_label.setStyleSheet(f"background: transparent; font-size: {theme.FONT_BODY_SMALL}px; line-height: 160%; color: {theme.TEXT_PRIMARY};")
        description_inner.addWidget(self.description_label)
        right_col.addWidget(self.description_frame)

        self.mangadex_frame, mangadex_inner = self._make_card("Главы на MangaDex/MAL")
        self.chapters_list = QListWidget()
        self.chapters_list.setMaximumHeight(220)
        mangadex_inner.addWidget(self.chapters_list)
        right_col.addWidget(self.mangadex_frame)

        right_col.addStretch()
        body_layout.addLayout(right_col, 1)

        scroll.setWidget(body)
        main_layout.addWidget(scroll, 1)

        self.set_preset(theme.get_preset(theme.PRESET_ORDER[0]))

    def set_preset(self, p):
        """Применяет цветовой пресет темы (вызывается из MainWindow.apply_theme).
        Раньше акцент был одним плоским цветом, жёстко зашитым в оранжевый
        независимо от настройки, а рамка метаданных — без градиентов и
        скруглений ("как из Windows 2000"). Теперь всё берётся из
        app.theme.PRESETS и красится градиентом пресета."""
        self._preset = p
        gradient = theme.accent_gradient_from(p)
        accent1, accent2 = p["accent1"], p["accent2"]
        a1 = QColor(accent1)
        a2 = QColor(accent2)

        self.hero_frame.setStyleSheet(
            "QFrame#HeroCard { "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 rgba({a1.red()},{a1.green()},{a1.blue()},46), "
            f"stop:1 rgba({a2.red()},{a2.green()},{a2.blue()},20)); "
            f"border: 1px solid rgba({a1.red()},{a1.green()},{a1.blue()},70); "
            f"border-radius: {theme.RADIUS_LG}px; }}"
        )

        # Плашка метаданных и остальные карточки-блоки (тома/главы/описание) —
        # той же природы, что и hero-блок с заголовком, но однозначно тёмные
        # (сплошной почти чёрный, а не полупрозрачная накладка поверх и без
        # того тёмного фона страницы — раньше это давало едва заметную рамку
        # без контраста фона).
        dark_card_css = (
            "background-color: #121114; "
            f"border: 1px solid rgba(255,255,255,0.07); border-radius: {theme.RADIUS_MD}px;"
        )
        self.meta_frame.setStyleSheet(f"QFrame#MetaCard {{ {dark_card_css} }}")
        for frame in (self.volumes_frame, self.local_chapters_frame, self.description_frame, self.mangadex_frame):
            frame.setStyleSheet(f"QFrame#BlockCard {{ {dark_card_css} }}")
        tag_style = (
            f"QPushButton {{ padding: 7px 18px; border-radius: 16px; "
            f"border: 1.5px solid {accent1}; color: {accent2}; "
            f"background: rgba(255,255,255,0.03); font-size: {theme.FONT_CAPTION}px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {gradient}; color: white; border-color: transparent; }}"
        )
        self.btn_status.setStyleSheet(tag_style)
        self.btn_rating.setStyleSheet(tag_style)
        self.btn_read.setStyleSheet(
            f"QPushButton {{ background: {gradient}; color: white; font-weight: 700; font-size: {theme.FONT_BODY}px; "
            f"padding: 12px 32px; border-radius: {theme.RADIUS_SM}px; border: none; }}"
            f"QPushButton:hover {{ background: {accent1}; }}"
        )
        for label in self.findChildren(QLabel):
            if label.property("_section_header"):
                label.setStyleSheet(
                    f"color: {accent2}; font-weight: bold; font-size: {theme.FONT_CAPTION}px; "
                    f"margin-top: 12px; padding: 3px 0px 3px 12px; "
                    f"border-left: 3px solid {accent1};"
                )

        if self._current_genres:
            self._set_genres(self._current_genres)

    def _make_card(self, header_text):
        """Тёмная карточка-блок с заголовком — общая обёртка для локальных
        томов/глав, описания и списка глав на MangaDex/MAL, чтобы страница
        читалась как набор чётких секций, а не как один длинный список."""
        frame = QFrame()
        frame.setObjectName("BlockCard")
        frame.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)
        header = QLabel(header_text)
        header.setProperty("_section_header", True)
        layout.addWidget(header)
        return frame, layout

    def show_for(self, manga_item, search_title=None, status="none", rating=None,
                 cache_key=None, local_volumes=None, has_progress=False):
        self.current_manga = manga_item
        self._search_title = search_title or manga_item.display_name
        self._cache_key = cache_key or manga_item.path
        self.set_status_rating(status, rating)
        self._has_progress = has_progress
        self.btn_read.setText("↻   Продолжить" if has_progress else "▶   Читать")
        self._populate_volumes(local_volumes or [])
        self._populate_local_chapters()
        self._render_loading()
        cached = info_data.load_cached_info(self._cache_key)
        if cached:
            self._render(cached)
        else:
            self._fetch_from_mangadex()

    def _populate_volumes(self, local_volumes):
        self._local_volumes = local_volumes
        self.volumes_list.clear()
        if not local_volumes:
            self.volumes_frame.hide()
            return
        self.volumes_frame.show()
        current_path = self.current_manga.path if self.current_manga else None

        for entry in local_volumes:
            label = _format_volume_label(entry["name"])
            is_internal = entry.get("internal", False)

            if entry["chapters"] and not is_internal:
                # Внешние главы-файлы (Hellsing/Berserk/Tokyo Ghoul-re): раскрывающийся том,
                # дети — отдельные файлы глав. Клик по главе открывает читалку сразу
                # (kind="read"), а не страницу информации — это конечная единица чтения.
                parent_item = QTreeWidgetItem([label])
                parent_item.setData(0, Qt.ItemDataRole.UserRole, None)
                expand_this = False
                for ch_name, ch_path in entry["chapters"]:
                    is_current = ch_path == current_path
                    child = QTreeWidgetItem([f"▶ {ch_name}" if is_current else ch_name])
                    child.setData(0, Qt.ItemDataRole.UserRole, ("read", ch_path))
                    parent_item.addChild(child)
                    if is_current:
                        expand_this = True
                if expand_this:
                    parent_item.setExpanded(True)
                self.volumes_list.addTopLevelItem(parent_item)
            elif entry["chapters"] and is_internal:
                # Внутренние главы одного файла (Highschool of the Dead: vol1.cbz содержит
                # несколько Ch_NNN) — дети переходят на нужную страницу ТОГО ЖЕ файла.
                is_current_volume = entry["path"] == current_path
                parent_item = QTreeWidgetItem([f"▶ {label}" if is_current_volume else label])
                parent_item.setData(0, Qt.ItemDataRole.UserRole, ("volume", entry["path"]))
                for ch_name, _unused in entry["chapters"]:
                    child = QTreeWidgetItem([ch_name])
                    child.setData(0, Qt.ItemDataRole.UserRole, ("chapter", (entry["path"], ch_name)))
                    parent_item.addChild(child)
                if is_current_volume:
                    parent_item.setExpanded(True)
                self.volumes_list.addTopLevelItem(parent_item)
            else:
                is_current = entry["path"] == current_path
                item = QTreeWidgetItem([f"▶ {label}" if is_current else label])
                item.setData(0, Qt.ItemDataRole.UserRole, ("volume", entry["path"]))
                self.volumes_list.addTopLevelItem(item)

    def _on_volume_clicked(self, item, _column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            item.setExpanded(not item.isExpanded())
            return
        kind, payload = data
        current_path = self.current_manga.path if self.current_manga else None
        if kind == "volume":
            if payload != current_path:
                self.volume_selected.emit(payload)
        elif kind == "chapter":
            volume_path, chapter_name = payload
            self.chapter_selected.emit(volume_path, chapter_name)
        elif kind == "read":
            self.read_file_requested.emit(payload)

    def _populate_local_chapters(self):
        self.local_chapters_list.clear()
        self._local_chapters = []
        if self._local_volumes or not self.current_manga:
            self.local_chapters_frame.hide()
            return
        try:
            chapters = get_chapter_list(self.current_manga)
        except Exception as e:
            logging.error(f"Ошибка получения списка глав {self.current_manga.path}: {e}")
            chapters = []
        if len(chapters) <= 1:
            self.local_chapters_frame.hide()
            return
        self._local_chapters = chapters
        self.local_chapters_frame.show()
        for ch in chapters:
            self.local_chapters_list.addItem(ch)

    def _on_local_chapter_double_clicked(self, item):
        if self.current_manga:
            self.chapter_selected.emit(self.current_manga.path, item.text())

    def set_status_rating(self, status, rating):
        self._current_status = status or "none"
        self._current_rating = int(rating) if rating else None
        self.btn_status.setText(f"🏷 {STATUS_TEXT.get(self._current_status, 'Без статуса')}")
        rating_key = str(self._current_rating) if self._current_rating else "none"
        self.btn_rating.setText(f"⭐ {RATING_TEXT.get(rating_key, 'Без оценки')}")

    def set_continue_state(self, has_progress):
        """Переключает текст кнопки чтения без полной перезагрузки страницы —
        вызывается после "Удалить прогресс"/"Отметить как прочитанное" из
        контекстного меню, пока пользователь остаётся на этой же странице."""
        self._has_progress = has_progress
        self.btn_read.setText("↻   Продолжить" if has_progress else "▶   Читать")

    def _set_genres(self, genres):
        """Пересобирает плашки жанров — раньше это была одна строка текста
        через запятую в таблице метаданных, теперь каждый жанр — отдельная
        цветная плашка (FlowLayout сам переносит их на новую строку)."""
        self._current_genres = genres
        while self._genres_flow.count():
            item = self._genres_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not genres:
            self.genres_frame.hide()
            return

        p = self._preset
        base = QColor(p["accent1"])
        # Qt QSS rgba() ждёт альфа-канал 0-255, а не 0.0-1.0 как в обычном CSS.
        alpha = 40
        for genre in genres:
            chip = QLabel(html.escape(genre))
            chip.setStyleSheet(
                f"background: rgba({base.red()},{base.green()},{base.blue()},{alpha}); "
                f"color: {p['accent2']}; padding: 5px 14px; border-radius: 12px; "
                f"font-size: {theme.FONT_CAPTION}px; font-weight: 600;"
            )
            self._genres_flow.addWidget(chip)
        self.genres_frame.show()

    def _set_meta_chips(self, rows):
        """Пересобирает плашки метаданных (автор/статус/год/...) — раньше
        это была HTML-таблица внутри едва отличимой от фона плашки. Каждое
        поле теперь отдельная плашка на градиенте — ярче и контрастнее
        плашек жанров, чтобы метаданные не сливались с описательным текстом."""
        while self._meta_flow.count():
            item = self._meta_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rows:
            return

        p = self._preset
        a1, a2 = QColor(p["accent1"]), QColor(p["accent2"])
        gradient = (
            f"qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 rgba({a1.red()},{a1.green()},{a1.blue()},110), "
            f"stop:1 rgba({a2.red()},{a2.green()},{a2.blue()},90))"
        )
        for label, value in rows:
            chip = QLabel(f"{html.escape(label.upper())}: {value}")
            chip.setTextFormat(Qt.TextFormat.PlainText)
            chip.setStyleSheet(
                f"background: {gradient}; color: white; padding: 6px 14px; "
                f"border-radius: 12px; font-size: {theme.FONT_BODY_SMALL}px; font-weight: 600;"
            )
            self._meta_flow.addWidget(chip)

    def _show_status_menu(self):
        if not self._cache_key:
            return
        menu = QMenu(self)
        _add_status_actions(menu, self._current_status, lambda a: self.status_rating_changed.emit(a, self._cache_key))
        menu.exec(self.btn_status.mapToGlobal(self.btn_status.rect().bottomLeft()))

    def _show_rating_menu(self):
        if not self._cache_key:
            return
        menu = QMenu(self)
        _add_rating_actions(menu, self._current_rating, lambda a: self.status_rating_changed.emit(a, self._cache_key))
        menu.exec(self.btn_rating.mapToGlobal(self.btn_rating.rect().bottomLeft()))

    def _show_item_menu(self):
        """Контекстное меню действий с мангой — то же самое, что в карточке
        библиотеки, но без статуса/оценки (для них тут отдельные кнопки)."""
        if not self._cache_key:
            return
        menu = QMenu(self)
        act_reset = QAction("🔄 Удалить прогресс", self)
        act_read = QAction("✅ Отметить как прочитанное", self)
        act_open_folder = QAction("📂 Открыть в проводнике", self)
        act_rename = QAction("✏️ Переименовать", self)
        act_del = QAction("❌ Удалить с устройства", self)

        act_reset.triggered.connect(lambda: self.menu_action_triggered.emit("reset", self._cache_key))
        act_read.triggered.connect(lambda: self.menu_action_triggered.emit("mark_read", self._cache_key))
        act_open_folder.triggered.connect(lambda: self.menu_action_triggered.emit("open_folder", self._cache_key))
        act_rename.triggered.connect(lambda: self.menu_action_triggered.emit("rename", self._cache_key))
        act_del.triggered.connect(lambda: self.menu_action_triggered.emit("delete", self._cache_key))

        menu.addAction(act_reset)
        menu.addAction(act_read)
        menu.addSeparator()
        menu.addAction(act_open_folder)
        menu.addAction(act_rename)
        menu.addSeparator()
        menu.addAction(act_del)
        menu.exec(self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomRight()))

    def force_refresh(self):
        if not self.current_manga:
            return
        info_data.clear_cached_info(self._cache_key)
        self._render_loading()
        self._fetch_from_mangadex()

    def change_mal_link(self):
        if not self.current_manga:
            return
        url, ok = QInputDialog.getText(self, "Изменить ссылку", "Вставьте ссылку на MyAnimeList:")
        if not ok or not url.strip():
            return
        self._render_loading()
        self._run_fetch(lambda: info_data.from_mal_smart(url.strip(), self._search_title), source="mal")

    def _fetch_from_mangadex(self):
        query = self._search_title

        def fetch():
            results = info_data.search_mangadex_best(query, limit=1)
            if not results:
                return None
            return info_data.from_mangadex(results[0]["id"])

        self._run_fetch(fetch, source="mangadex")

    def _run_fetch(self, fetch_fn, source="mangadex"):
        self._fetch_source = source
        self._fetch_token += 1
        token = self._fetch_token
        cache_key = self._cache_key
        self._worker = InfoFetchWorker(fetch_fn)
        self._worker.finished_ok.connect(lambda info, t=token, k=cache_key: self._on_fetch_ok(info, t, k))
        self._worker.finished_error.connect(lambda msg, t=token: self._on_fetch_error(msg, t))
        self._worker.start()

    def _on_fetch_ok(self, info, token, cache_key):
        if token != self._fetch_token:
            # Пришёл ответ на уже неактуальный запрос (пользователь успел переключить
            # том/мангу, пока этот запрос летел) — не перезаписываем текущий экран.
            return
        if cache_key:
            info_data.save_cached_info(cache_key, info)
        self._render(info)

    def _on_fetch_error(self, message, token):
        if token != self._fetch_token:
            return
        if self._fetch_source == "mal":
            self._show_status_banner(
                f"⚠ Не удалось загрузить данные с MyAnimeList ({message}). "
                f"Похоже, MyAnimeList/Jikan сейчас недоступен — попробуйте позже."
            )
        else:
            self._show_status_banner(
                f"⚠ Не удалось найти мангу автоматически ({message}). "
                f"Попробуйте «Изменить ссылку» и указать MyAnimeList вручную."
            )
        self._set_meta_chips([])
        self.original_title_label.setText("")
        self.description_label.setText("")
        self.chapters_list.clear()
        self._set_genres([])

    def _show_status_banner(self, text):
        self.status_label.setText(text)
        self.status_label.show()

    def _hide_status_banner(self):
        self.status_label.setText("")
        self.status_label.hide()

    def _render_loading(self):
        self.title_label.setText(self.current_manga.display_name if self.current_manga else "")
        self.original_title_label.setText("")
        self._set_meta_chips([])
        self.description_label.setText("")
        self._hide_status_banner()
        self.chapters_list.clear()
        self._set_genres([])
        self._set_local_cover_fallback()

    def _set_local_cover_fallback(self):
        """Обложка из библиотеки (своя кастомная либо первая страница архива)
        — используется как заглушка на время загрузки с MangaDex/MAL и
        остаётся, если мангу там не нашли (иначе обложка не отображалась бы
        вообще, хотя локальная есть)."""
        self.cover_label.setPixmap(QPixmap())
        if not self.current_manga:
            return
        data = get_cover_bytes(self.current_manga.path, is_folder=not self.current_manga.is_archive)
        if not data:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if not pixmap.isNull():
            self._set_cover_pixmap(pixmap)

    def _render(self, info):
        title = info.get("title_ru") or info.get("title") or (self.current_manga.display_name if self.current_manga else "")
        self.title_label.setText(title)

        original = info.get("title") or ""
        self.original_title_label.setText(original if original and original != title else "")

        self._set_genres(info.get("genres") or [])

        rows = []
        if info.get("author"):
            rows.append(("Автор", html.escape(info["author"])))
        if info.get("artist") and info.get("artist") != info.get("author"):
            rows.append(("Художник", html.escape(info["artist"])))
        status = info.get("status")
        if status:
            rows.append(("Статус", STATUS_RU.get(status, status)))
        if info.get("year"):
            rows.append(("Год", str(info["year"])))
        if info.get("rating"):
            rows.append(("Оценка MAL", str(info["rating"])))
        content_badge = CONTENT_RATING_RU.get(info.get("content_rating"))
        if content_badge:
            rows.append(("Рейтинг", content_badge))
        if info.get("last_chapter"):
            rows.append(("Последняя глава", str(info["last_chapter"])))
        if info.get("chapters"):
            source_label = "MangaDex" if info.get("source") == "mangadex" else "MAL"
            rows.append((f"Глав на {source_label}", str(len(info["chapters"]))))

        self._set_meta_chips(rows)

        self.description_label.setText(_description_to_html(info.get("description")))
        self._hide_status_banner()

        self.chapters_list.clear()
        for ch in info.get("chapters", [])[:500]:
            label = f"Глава {ch['chapter']}" if ch.get("chapter") else "Глава ?"
            if ch.get("title"):
                label += f" — {ch['title']}"
            self.chapters_list.addItem(label)

        cover_url = info.get("cover_url")
        if cover_url:
            cached_pixmap = self._cover_pixmap_cache.get(cover_url)
            if cached_pixmap is not None:
                # Обложка уже загружалась в этой сессии (например, при переключении томов
                # внутри одной серии) — применяем сразу, без повторного сетевого запроса
                # и без "мигания" пустой обложки на время загрузки.
                self._set_cover_pixmap(cached_pixmap)
            else:
                self._load_cover(cover_url)

    def _load_cover(self, url):
        self._cover_token += 1
        token = self._cover_token

        def fetch():
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return {"_cover_bytes": resp.content, "_cover_url": url}

        worker = InfoFetchWorker(fetch)
        worker.finished_ok.connect(lambda result, t=token: self._on_cover_loaded(result, t))
        worker.finished_error.connect(lambda _msg: None)
        self._cover_worker = worker
        worker.start()

    def _on_cover_loaded(self, result, token):
        pixmap = QPixmap()
        pixmap.loadFromData(result["_cover_bytes"])
        if not pixmap.isNull():
            self._cover_pixmap_cache[result["_cover_url"]] = pixmap
            if token == self._cover_token:
                self._set_cover_pixmap(pixmap)

    def _set_cover_pixmap(self, pixmap):
        scaled = scale_to_fill(pixmap, self.cover_label.width(), self.cover_label.height())
        self.cover_label.setPixmap(round_pixmap(scaled, theme.RADIUS_MD))


def _section_header(text):
    label = QLabel(text)
    label.setProperty("_section_header", True)
    label.setStyleSheet("color: #ff9800; font-weight: bold; font-size: 13px; margin-top: 10px; padding-left: 10px; border-left: 3px solid #ff9800;")
    return label


