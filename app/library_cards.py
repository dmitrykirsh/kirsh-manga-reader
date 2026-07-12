import zlib

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QProgressBar, QMenu, QGraphicsDropShadowEffect, QFrame,
    QGraphicsOpacityEffect)
from PyQt6.QtGui import QPixmap, QImage, QAction, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect

from app.models import get_cover_bytes
from app.image_utils import load_image_bounded, round_pixmap, scale_to_fill
from app import theme

STATUS_LABELS = [
    ("none", "▫ Без статуса"),
    ("reading", "📖 Читаю"),
    ("completed", "✅ Прочитано"),
    ("planned", "📌 В планах"),
    ("dropped", "🗑 Брошено"),
]
STATUS_EMOJI = {key: label.split(" ", 1)[0] for key, label in STATUS_LABELS if key != "none"}

RATING_LABELS = [
    ("none", "Без оценки"),
    ("1", "★☆☆☆☆"),
    ("2", "★★☆☆☆"),
    ("3", "★★★☆☆"),
    ("4", "★★★★☆"),
    ("5", "★★★★★"),
]


def _rating_stars(rating):
    if not rating: return ""
    return "★" * rating + "☆" * (5 - rating)


def _format_badge(status, rating):
    parts = []
    if status and status != "none":
        parts.append(STATUS_EMOJI.get(status, ""))
    stars = _rating_stars(rating)
    if stars:
        parts.append(stars)
    return " ".join(parts)


def _add_status_actions(menu, current_status, emit):
    for key, label in STATUS_LABELS:
        act = QAction(label, menu)
        act.setCheckable(True)
        act.setChecked((current_status or "none") == key)
        act.triggered.connect(lambda checked=False, k=key: emit(f"status:{k}"))
        menu.addAction(act)


def _add_rating_actions(menu, current_rating, emit):
    current_rating_key = str(current_rating) if current_rating else "none"
    for key, label in RATING_LABELS:
        act = QAction(label, menu)
        act.setCheckable(True)
        act.setChecked(current_rating_key == key)
        act.triggered.connect(lambda checked=False, k=key: emit(f"rating:{k}"))
        menu.addAction(act)


def _add_status_rating_actions(menu, current_status, current_rating, emit):
    status_menu = menu.addMenu("🏷 Статус")
    _add_status_actions(status_menu, current_status, emit)
    rating_menu = menu.addMenu("⭐ Оценка")
    _add_rating_actions(rating_menu, current_rating, emit)


# Градиентные пары для рамки вокруг обложки — те же пары, что и в
# app.theme.PRESETS (плюс один смешанный вариант), чтобы сетка библиотеки
# была разноцветной, но при этом в той же приглушённой палитре, что и
# остальной интерфейс, а не отдельным неоновым набором сама по себе.
# Выбираются детерминированно по имени тайтла — одна и та же манга всегда
# получает один и тот же градиент между перезапусками.
COVER_GRADIENTS = [tuple(theme.PRESETS[name][k] for k in ("accent1", "accent2")) for name in theme.PRESET_ORDER] + [
    ("#64d2a0", "#0a84ff"),  # бирюзово-синий — доп. вариант для разнообразия
]


def _gradient_for(key):
    idx = zlib.crc32(key.encode("utf-8")) % len(COVER_GRADIENTS)
    return COVER_GRADIENTS[idx]


def _gradient_css(c1, c2, angle="x1:0, y1:0, x2:1, y2:1"):
    return f"qlineargradient({angle}, stop:0 {c1}, stop:1 {c2})"


def _attach_hover_glow(card, target):
    """Мягкая цветная подсветка обложки при наведении — только вокруг
    обложки, а не всей карточки целиком (название/оценка остаются на месте,
    без тени под ними)."""
    c1, c2 = _gradient_for(getattr(card, "_gradient_key", "manga"))
    effect = QGraphicsDropShadowEffect(target)
    effect.setBlurRadius(0)
    effect.setOffset(0, 0)
    effect.setColor(QColor(c1))
    target.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"blurRadius", card)
    anim.setDuration(180)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    card._hover_glow_effect = effect
    card._hover_glow_anim = anim

    original_enter = card.enterEvent
    original_leave = card.leaveEvent

    def enterEvent(event):
        anim.stop()
        anim.setStartValue(effect.blurRadius())
        anim.setEndValue(28)
        anim.start()
        original_enter(event)

    def leaveEvent(event):
        anim.stop()
        anim.setStartValue(effect.blurRadius())
        anim.setEndValue(0)
        anim.start()
        original_leave(event)

    card.enterEvent = enterEvent
    card.leaveEvent = leaveEvent


class LibraryCard(QWidget):
    clicked = pyqtSignal(object)
    menu_action_triggered = pyqtSignal(str, str)

    def __init__(self, manga_item, current_page=0, card_width=220, status="none", rating=None):
        super().__init__()
        self.manga_item = manga_item
        self.current_page = current_page
        self.status = status
        self.rating = rating
        self.cover_data = get_cover_bytes(self.manga_item.path, is_folder=False)
        self._gradient_key = self.manga_item.display_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        c1, c2 = _gradient_for(self._gradient_key)
        self.cover_frame = QFrame()
        self.cover_frame.setObjectName("CoverFrame")
        self.cover_frame.setStyleSheet(
            f"QFrame#CoverFrame {{ background: {_gradient_css(c1, c2)}; border-radius: 16px; }}"
        )
        cover_frame_layout = QVBoxLayout(self.cover_frame)
        cover_frame_layout.setContentsMargins(3, 3, 3, 3)

        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background-color: #1c1c1c; border-radius: 13px;")
        cover_frame_layout.addWidget(self.cover_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)

        total_pages = len(self.manga_item.pages)
        self.progress_bar.setMaximum(total_pages if total_pages > 0 else 100)
        self.progress_bar.setValue(current_page + 1 if current_page > 0 or total_pages == 1 else current_page)
        if current_page == 0 and total_pages > 0: self.progress_bar.setValue(0)

        self.badge_label = QLabel(_format_badge(status, rating))
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_label.setStyleSheet("font-size: 12px; color: #ffb300;")

        self.title_label = QLabel(self.manga_item.display_name)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        self.title_label.setToolTip(self.manga_item.display_name)

        layout.addWidget(self.cover_frame)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.badge_label)
        layout.addWidget(self.title_label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        _attach_hover_glow(self, self.cover_frame)
        self.update_size(card_width)

    def update_size(self, card_width):
        self.setFixedWidth(card_width)
        w_cover = card_width - 20
        h_cover = int(w_cover * 1.4)
        self.cover_label.setFixedSize(w_cover - 6, h_cover - 6)

        if self.cover_data:
            img = load_image_bounded(self.cover_data)
            pix = scale_to_fill(QPixmap.fromImage(img), w_cover - 6, h_cover - 6)
            # Прозрачный фон — иначе в скруглённых (прозрачных) углах самой
            # картинки просвечивал сплошной тёмный квадрат фона лейбла:
            # незаметно на обложках с тёмными углами, но чётко видно как
            # "не скруглено" на ярких (тот самый разнобой между обложками).
            # Так сквозь угол видно градиентную рамку позади — тоже красивее.
            self.cover_label.setStyleSheet("background: transparent; border-radius: 13px;")
            self.cover_label.setPixmap(round_pixmap(pix, theme.RADIUS_MD))
        else:
            self.cover_label.setText("📖")
            self.cover_label.setStyleSheet("background-color: #1c1c1c; border-radius: 13px; font-size: 32px;")

        self.progress_bar.setFixedSize(w_cover, 6)

        self.badge_label.setFixedWidth(w_cover)

        self.title_label.setFixedWidth(w_cover)
        self.title_label.setFixedHeight(20)
        self.title_label.setWordWrap(False)
        font_metrics = self.title_label.fontMetrics()
        elided_text = font_metrics.elidedText(self.manga_item.display_name, Qt.TextElideMode.ElideRight, w_cover)
        self.title_label.setText(elided_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.manga_item)

    def show_context_menu(self, pos):
        menu = QMenu(self)

        act_reset = QAction("🔄 Удалить прогресс", self)
        act_read = QAction("✅ Отметить как прочитанное", self)
        act_cover = QAction("🖼 Изменить обложку", self)
        act_rem_cover = QAction("🗑 Удалить свою обложку", self)
        act_open_folder = QAction("📂 Открыть в проводнике", self)
        act_rename = QAction("✏️ Переименовать", self)
        act_del = QAction("❌ Удалить с устройства", self)

        act_reset.triggered.connect(lambda: self.menu_action_triggered.emit("reset", self.manga_item.path))
        act_read.triggered.connect(lambda: self.menu_action_triggered.emit("mark_read", self.manga_item.path))
        act_cover.triggered.connect(lambda: self.menu_action_triggered.emit("change_cover", self.manga_item.path))
        act_rem_cover.triggered.connect(lambda: self.menu_action_triggered.emit("remove_cover", self.manga_item.path))
        act_open_folder.triggered.connect(lambda: self.menu_action_triggered.emit("open_folder", self.manga_item.path))
        act_rename.triggered.connect(lambda: self.menu_action_triggered.emit("rename", self.manga_item.path))
        act_del.triggered.connect(lambda: self.menu_action_triggered.emit("delete", self.manga_item.path))

        menu.addAction(act_reset)
        menu.addAction(act_read)
        menu.addSeparator()
        _add_status_rating_actions(
            menu, self.status, self.rating,
            lambda action: self.menu_action_triggered.emit(action, self.manga_item.path)
        )
        menu.addSeparator()
        menu.addAction(act_cover)
        menu.addAction(act_rem_cover)
        menu.addSeparator()
        menu.addAction(act_open_folder)
        menu.addAction(act_rename)
        menu.addSeparator()
        menu.addAction(act_del)
        menu.exec(self.mapToGlobal(pos))

class LibraryFolderCard(QWidget):
    clicked = pyqtSignal(str)
    menu_action_triggered = pyqtSignal(str, str)

    def __init__(self, folder_path, display_name, progress_val, progress_max, card_width=220, status="none", rating=None):
        super().__init__()
        self.folder_path = folder_path
        self.display_name = display_name
        self.progress_val = progress_val
        self.progress_max = progress_max
        self.status = status
        self.rating = rating
        self.cover_data = get_cover_bytes(folder_path, is_folder=True)
        self._gradient_key = display_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        c1, c2 = _gradient_for(self._gradient_key)
        self.cover_frame = QFrame()
        self.cover_frame.setObjectName("CoverFrame")
        self.cover_frame.setStyleSheet(
            f"QFrame#CoverFrame {{ background: {_gradient_css(c1, c2)}; border-radius: 16px; }}"
        )
        cover_frame_layout = QVBoxLayout(self.cover_frame)
        cover_frame_layout.setContentsMargins(3, 3, 3, 3)

        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background-color: #211c15; border-radius: 13px;")
        cover_frame_layout.addWidget(self.cover_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximum(progress_max if progress_max > 0 else 100)
        self.progress_bar.setValue(progress_val)

        self.badge_label = QLabel(_format_badge(status, rating))
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_label.setStyleSheet("font-size: 12px; color: #ffb300;")

        self.title_label = QLabel(display_name)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #ff9800;")
        self.title_label.setToolTip(display_name)

        layout.addWidget(self.cover_frame)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.badge_label)
        layout.addWidget(self.title_label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        _attach_hover_glow(self, self.cover_frame)
        self.update_size(card_width)

    def update_size(self, card_width):
        self.setFixedWidth(card_width)
        w_cover = card_width - 20
        h_cover = int(w_cover * 1.4)
        self.cover_label.setFixedSize(w_cover - 6, h_cover - 6)

        if self.cover_data:
            img = load_image_bounded(self.cover_data)
            pix = scale_to_fill(QPixmap.fromImage(img), w_cover - 6, h_cover - 6)
            self.cover_label.setStyleSheet("background: transparent; border-radius: 13px;")
            self.cover_label.setPixmap(round_pixmap(pix, theme.RADIUS_MD))
            self.cover_label.setText("")
        else:
            self.cover_label.setText("📁")
            self.cover_label.setStyleSheet("background-color: #211c15; border-radius: 13px; font-size: 48px;")

        self.progress_bar.setFixedSize(w_cover, 6)

        self.badge_label.setFixedWidth(w_cover)

        self.title_label.setFixedWidth(w_cover)
        self.title_label.setFixedHeight(20)
        self.title_label.setWordWrap(False)
        font_metrics = self.title_label.fontMetrics()
        elided_text = font_metrics.elidedText(self.display_name, Qt.TextElideMode.ElideRight, w_cover)
        self.title_label.setText(elided_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.folder_path)

    def show_context_menu(self, pos):
        menu = QMenu(self)

        act_reset = QAction("🔄 Удалить прогресс папки", self)
        act_read = QAction("✅ Отметить как прочитанное", self)
        act_cover = QAction("🖼 Изменить обложку", self)
        act_rem_cover = QAction("🗑 Удалить свою обложку", self)
        act_open_folder = QAction("📂 Открыть в проводнике", self)
        act_rename = QAction("✏️ Переименовать папку", self)
        act_del = QAction("❌ Удалить папку с устройства", self)

        act_reset.triggered.connect(lambda: self.menu_action_triggered.emit("reset", self.folder_path))
        act_read.triggered.connect(lambda: self.menu_action_triggered.emit("mark_read", self.folder_path))
        act_cover.triggered.connect(lambda: self.menu_action_triggered.emit("change_cover", self.folder_path))
        act_rem_cover.triggered.connect(lambda: self.menu_action_triggered.emit("remove_cover", self.folder_path))
        act_open_folder.triggered.connect(lambda: self.menu_action_triggered.emit("open_folder", self.folder_path))
        act_rename.triggered.connect(lambda: self.menu_action_triggered.emit("rename", self.folder_path))
        act_del.triggered.connect(lambda: self.menu_action_triggered.emit("delete", self.folder_path))

        menu.addAction(act_reset)
        menu.addAction(act_read)
        menu.addSeparator()
        _add_status_rating_actions(
            menu, self.status, self.rating,
            lambda action: self.menu_action_triggered.emit(action, self.folder_path)
        )
        menu.addSeparator()
        menu.addAction(act_cover)
        menu.addAction(act_rem_cover)
        menu.addSeparator()
        menu.addAction(act_open_folder)
        menu.addAction(act_rename)
        menu.addSeparator()
        menu.addAction(act_del)
        menu.exec(self.mapToGlobal(pos))
