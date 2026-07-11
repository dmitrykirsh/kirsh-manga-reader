from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QProgressBar, QMenu)
from PyQt6.QtGui import QPixmap, QImage, QAction
from PyQt6.QtCore import Qt, pyqtSignal

from app.models import get_cover_bytes

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background-color: #2a2a2a; border-radius: 8px;")

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

        layout.addWidget(self.cover_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.badge_label)
        layout.addWidget(self.title_label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.update_size(card_width)

    def update_size(self, card_width):
        self.setFixedWidth(card_width)
        w_cover = card_width - 20
        h_cover = int(w_cover * 1.4)
        self.cover_label.setFixedSize(w_cover, h_cover)

        if self.cover_data:
            img = QImage()
            img.loadFromData(self.cover_data)
            pix = QPixmap.fromImage(img).scaled(w_cover, h_cover, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setPixmap(pix)
        else:
            self.cover_label.setText("📖")
            self.cover_label.setStyleSheet("background-color: #2a2a2a; border-radius: 8px; font-size: 32px;")

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background-color: #2d261d; border-radius: 8px;")

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

        layout.addWidget(self.cover_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.badge_label)
        layout.addWidget(self.title_label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.update_size(card_width)

    def update_size(self, card_width):
        self.setFixedWidth(card_width)
        w_cover = card_width - 20
        h_cover = int(w_cover * 1.4)
        self.cover_label.setFixedSize(w_cover, h_cover)

        if self.cover_data:
            img = QImage()
            img.loadFromData(self.cover_data)
            pix = QPixmap.fromImage(img).scaled(w_cover, h_cover, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setPixmap(pix)
            self.cover_label.setText("")
        else:
            self.cover_label.setText("📁")
            self.cover_label.setStyleSheet("background-color: #2d261d; border-radius: 8px; font-size: 48px;")

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
