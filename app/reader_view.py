import os
import re
import logging
from collections import OrderedDict
from pathlib import Path

from natsort import natsorted
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QDialog, QMessageBox, QGraphicsView, QGraphicsScene,
    QSlider, QInputDialog, QListWidget)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QImageReader
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QObject, QTimer, QBuffer, QByteArray

from app.constants import ARCHIVE_EXTENSIONS, VALID_EXTENSIONS
from app.models import get_chapter_list as _shared_get_chapter_list, get_first_page_of_chapter as _shared_get_first_page_of_chapter

# Сколько страниц предзагружать вперёд/назад от текущей и сколько
# декодированных страниц держать в кэше (текущая + окно предзагрузки + запас).
PREFETCH_AHEAD = 2
PREFETCH_BEHIND = 1
PAGE_CACHE_SIZE = 6

# Вертикальный (webtoon) режим: сколько высот вьюпорта вперёд/назад от
# видимой области держать реально decoded, и на каком расстоянии выгружать
# обратно в плейсхолдер, чтобы не копить в памяти сотни полноразмерных страниц.
WEBTOON_LOAD_MARGIN_VIEWPORTS = 1.5
WEBTOON_EVICT_MARGIN_VIEWPORTS = 4.0


class PagePrefetchWorker(QObject):
    """Живёт в отдельном QThread. Декодирует страницы в QImage в фоне,
    чтобы декодирование не подвешивало UI при перелистывании."""
    page_ready = pyqtSignal(str, int, QImage)
    sizes_probed = pyqtSignal(str, list)

    def prefetch(self, manga, page_idx):
        data = manga.get_page_data(page_idx)
        if not data:
            return
        image = QImage()
        image.loadFromData(data)
        if not image.isNull():
            self.page_ready.emit(manga.path, page_idx, image)

    def probe_sizes(self, manga, total_pages):
        """Быстро определяет реальные размеры всех страниц (без полного
        декодирования) — нужно, чтобы заранее раскидать плейсхолдеры
        по вертикальной ленте на правильную высоту."""
        results = []
        for idx in range(total_pages):
            width, height = 800, 1200
            data = manga.get_page_data(idx)
            if data:
                buf = QBuffer()
                buf.setData(QByteArray(data))
                buf.open(QBuffer.OpenModeFlag.ReadOnly)
                reader = QImageReader(buf)
                size = reader.size()
                buf.close()
                if size.isValid() and size.width() > 0 and size.height() > 0:
                    width, height = size.width(), size.height()
            results.append((idx, width, height))
        self.sizes_probed.emit(manga.path, results)


class ReaderView(QGraphicsView):
    return_to_library = pyqtSignal()
    progress_changed = pyqtSignal(str, int, int)
    last_page_reached = pyqtSignal(bool)
    _request_prefetch = pyqtSignal(object, int)
    _request_probe_sizes = pyqtSignal(object, int)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.current_manga = None
        self.current_page_idx = 0
        self.pixmap_item = None
        self.is_zoomed = False

        self._page_cache = OrderedDict()
        self._pending_prefetch = set()

        # Состояние вертикального (webtoon) режима.
        self.webtoon_mode = False
        self._wt_ready = False
        self._wt_items = {}
        self._wt_loaded = set()
        self._wt_raw_sizes = {}
        self._wt_heights = {}
        self._wt_y_offsets = {}
        self._wt_total_height = 0
        self._wt_target_width = 0
        self._wt_placeholder_cache = {}
        self._wt_scroll_timer = QTimer(self)
        self._wt_scroll_timer.setSingleShot(True)
        self._wt_scroll_timer.timeout.connect(self._wt_update_visible)

        self._prefetch_thread = QThread(self)
        self._prefetch_worker = PagePrefetchWorker()
        self._prefetch_worker.moveToThread(self._prefetch_thread)
        self._request_prefetch.connect(self._prefetch_worker.prefetch)
        self._request_probe_sizes.connect(self._prefetch_worker.probe_sizes)
        self._prefetch_worker.page_ready.connect(self._on_page_prefetched)
        self._prefetch_worker.sizes_probed.connect(self._on_sizes_probed)
        self._prefetch_thread.start()

        self.verticalScrollBar().valueChanged.connect(self._on_wt_scrolled)

        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_prefetch_thread)

    def _stop_prefetch_thread(self):
        self._prefetch_thread.quit()
        self._prefetch_thread.wait(2000)

    def load_manga(self, manga_item, start_page=0):
        self.current_manga = manga_item
        self.current_manga.open_archive()
        self.current_page_idx = start_page
        self.is_zoomed = False
        self._page_cache.clear()
        self._pending_prefetch.clear()

        want_webtoon = bool(self.main_window and self.main_window.get_webtoon_pref(manga_item.path))
        self.webtoon_mode = False
        if want_webtoon:
            self.set_webtoon_mode(True)
        else:
            self.show_page()

    def _cache_page(self, page_idx, image):
        self._page_cache[page_idx] = image
        self._page_cache.move_to_end(page_idx)
        while len(self._page_cache) > PAGE_CACHE_SIZE:
            self._page_cache.popitem(last=False)

    def _on_page_prefetched(self, manga_path, page_idx, image):
        self._pending_prefetch.discard(page_idx)
        if not self.current_manga or self.current_manga.path != manga_path:
            return
        if self.webtoon_mode:
            item = self._wt_items.get(page_idx)
            if item and not image.isNull():
                pixmap = QPixmap.fromImage(image).scaledToWidth(
                    self._wt_target_width, Qt.TransformationMode.SmoothTransformation)
                item.setPixmap(pixmap)
                self._wt_loaded.add(page_idx)
            return
        self._cache_page(page_idx, image)

    def _schedule_prefetch(self):
        if not self.current_manga: return
        total = len(self.current_manga.pages)
        wanted = (
            [self.current_page_idx + i for i in range(1, PREFETCH_AHEAD + 1)] +
            [self.current_page_idx - i for i in range(1, PREFETCH_BEHIND + 1)]
        )
        for idx in wanted:
            if 0 <= idx < total and idx not in self._page_cache and idx not in self._pending_prefetch:
                self._pending_prefetch.add(idx)
                self._request_prefetch.emit(self.current_manga, idx)

    def show_page(self):
        if not self.current_manga: return
        if self.webtoon_mode:
            if self._wt_ready:
                self._wt_scroll_to_page(self.current_page_idx)
            return
        idx = self.current_page_idx

        image = self._page_cache.get(idx)
        if image is None:
            data = self.current_manga.get_page_data(idx)
            if not data: return
            image = QImage()
            image.loadFromData(data)
            if image.isNull(): return
            self._cache_page(idx, image)
        else:
            self._page_cache.move_to_end(idx)

        pixmap = QPixmap.fromImage(image)

        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.pixmap().rect().toRectF())

        self.fit_to_height()
        self.progress_changed.emit(self.current_manga.path, self.current_page_idx, len(self.current_manga.pages))

        is_last = (self.current_page_idx == len(self.current_manga.pages) - 1)
        self.last_page_reached.emit(is_last)

        self._schedule_prefetch()

    def fit_to_height(self):
        if self.pixmap_item and self.pixmap_item.pixmap().height() > 0:
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            scale_factor = self.viewport().height() / self.pixmap_item.pixmap().height()
            self.resetTransform()
            self.scale(scale_factor, scale_factor)
            self.centerOn(self.pixmap_item)

    def toggle_zoom(self, pos):
        if not self.pixmap_item: return
        self.is_zoomed = not self.is_zoomed
        if self.is_zoomed:
            self.resetTransform()
            self.scale(1.8, 1.8)
            self.centerOn(pos)
        else:
            self.fit_to_height()

    def next_page(self):
        if self.current_manga and self.current_page_idx < len(self.current_manga.pages) - 1:
            self.current_page_idx += 1
            self.is_zoomed = False
            self.show_page()

    def prev_page(self):
        if self.current_manga and self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.is_zoomed = False
            self.show_page()

    # -------------------------------------------------
    # Вертикальный (webtoon) режим
    # -------------------------------------------------

    def set_webtoon_mode(self, enabled):
        if enabled == self.webtoon_mode or not self.current_manga:
            return
        self.webtoon_mode = enabled
        if enabled:
            self._enter_webtoon_mode()
        else:
            self._exit_webtoon_mode()

    def _enter_webtoon_mode(self):
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.resetTransform()
        self.is_zoomed = False
        self._wt_ready = False
        self._wt_items.clear()
        self._wt_loaded.clear()
        self._wt_raw_sizes.clear()
        self._wt_heights.clear()
        self._wt_y_offsets.clear()
        self._pending_prefetch.clear()
        self.pixmap_item = None
        self.scene.clear()

        width = max(self.viewport().width(), 200)
        loading_item = self.scene.addText("Загрузка вертикального режима…")
        loading_item.setDefaultTextColor(Qt.GlobalColor.white)
        self.scene.setSceneRect(0, 0, width, 60)

        self._request_probe_sizes.emit(self.current_manga, len(self.current_manga.pages))

    def _exit_webtoon_mode(self):
        idx = self.current_page_idx
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._wt_ready = False
        self._wt_items.clear()
        self._wt_loaded.clear()
        self._wt_raw_sizes.clear()
        self._wt_heights.clear()
        self._wt_y_offsets.clear()
        self._pending_prefetch.clear()
        self.scene.clear()
        self.pixmap_item = None
        self.current_page_idx = idx
        self.show_page()

    def _get_placeholder(self, width, height):
        key = (width, max(height, 1))
        pixmap = self._wt_placeholder_cache.get(key)
        if pixmap is None:
            pixmap = QPixmap(key[0], key[1])
            pixmap.fill(Qt.GlobalColor.darkGray)
            self._wt_placeholder_cache[key] = pixmap
        return pixmap

    def _on_sizes_probed(self, manga_path, results):
        if not self.webtoon_mode or not self.current_manga or self.current_manga.path != manga_path:
            return
        for idx, width, height in results:
            self._wt_raw_sizes[idx] = (width, height)
        self._wt_rebuild_layout()
        self._wt_ready = True
        self._wt_scroll_to_page(self.current_page_idx)
        self._wt_update_visible()

    def _wt_rebuild_layout(self):
        """Пересчитывает высоты/позиции страниц под текущую ширину вьюпорта
        по уже известным исходным размерам — без повторного чтения архива."""
        target_width = max(self.viewport().width(), 200)
        self._wt_target_width = target_width
        self._wt_items.clear()
        self._wt_loaded.clear()
        self.scene.clear()
        self.pixmap_item = None

        y = 0.0
        for idx in range(len(self.current_manga.pages)):
            width, height = self._wt_raw_sizes.get(idx, (target_width, int(target_width * 1.4)))
            scaled_h = height * (target_width / width) if width > 0 else height
            self._wt_heights[idx] = scaled_h
            self._wt_y_offsets[idx] = y
            item = self.scene.addPixmap(self._get_placeholder(target_width, int(scaled_h)))
            item.setPos(0, y)
            self._wt_items[idx] = item
            y += scaled_h

        self._wt_total_height = y
        self.scene.setSceneRect(0, 0, target_width, max(y, 1))

    def _wt_scroll_to_page(self, idx):
        if idx not in self._wt_y_offsets:
            return
        top = self._wt_y_offsets[idx]
        height = self._wt_heights.get(idx, 0)
        visible_h = self._wt_visible_scene_rect().height() or self.viewport().height()
        target_y = top + min(height, visible_h) / 2
        self.centerOn(self._wt_target_width / 2, target_y)

    def _wt_visible_scene_rect(self):
        """Видимая область в координатах сцены — учитывает текущий зум
        (Ctrl+колесико в вертикальном режиме), в отличие от голых значений
        скроллбара."""
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def _on_wt_scrolled(self, _value):
        if self.webtoon_mode and self._wt_ready:
            self._wt_scroll_timer.start(80)

    def _wt_page_at(self, y):
        if not self._wt_y_offsets:
            return None
        if y <= 0:
            return 0
        if y >= self._wt_total_height:
            return max(self._wt_y_offsets)
        for idx, offset in self._wt_y_offsets.items():
            if offset <= y < offset + self._wt_heights.get(idx, 0):
                return idx
        return self.current_page_idx

    def _wt_evict_page(self, idx):
        self._wt_loaded.discard(idx)
        item = self._wt_items.get(idx)
        if item:
            width = self._wt_target_width
            height = int(self._wt_heights.get(idx, 0))
            item.setPixmap(self._get_placeholder(width, height))

    def _wt_update_visible(self):
        if not self.webtoon_mode or not self._wt_ready or not self.current_manga:
            return
        visible = self._wt_visible_scene_rect()
        top, bottom = visible.top(), visible.bottom()
        viewport_h = max(bottom - top, 1)

        load_margin = viewport_h * WEBTOON_LOAD_MARGIN_VIEWPORTS
        evict_margin = viewport_h * WEBTOON_EVICT_MARGIN_VIEWPORTS
        load_top, load_bottom = top - load_margin, bottom + load_margin
        evict_top, evict_bottom = top - evict_margin, bottom + evict_margin

        for idx, y in self._wt_y_offsets.items():
            h = self._wt_heights.get(idx, 0)
            page_top, page_bottom = y, y + h
            in_load_range = page_bottom >= load_top and page_top <= load_bottom
            in_evict_range = page_bottom >= evict_top and page_top <= evict_bottom

            if in_load_range and idx not in self._wt_loaded and idx not in self._pending_prefetch:
                self._pending_prefetch.add(idx)
                self._request_prefetch.emit(self.current_manga, idx)
            elif not in_evict_range and idx in self._wt_loaded:
                self._wt_evict_page(idx)

        current_idx = self._wt_page_at(top + viewport_h * 0.3)
        if current_idx is not None:
            self.current_page_idx = current_idx
            self.progress_changed.emit(self.current_manga.path, current_idx, len(self.current_manga.pages))
            is_last = bottom >= (self._wt_total_height - 5)
            self.last_page_reached.emit(is_last)

    def wheelEvent(self, event):
        if self.webtoon_mode:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                factor = 1.1 if event.angleDelta().y() > 0 else 0.9
                anchor = self.transformationAnchor()
                self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                self.scale(factor, factor)
                self.setTransformationAnchor(anchor)
                event.accept()
                self._wt_scroll_timer.start(80)
                return
            super().wheelEvent(event)
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self.scale(factor, factor)
            self.is_zoomed = True
            event.accept()
            return

        if not self.is_zoomed:
            if event.angleDelta().y() > 0: self.prev_page()
            else: self.next_page()
        else: super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.return_to_library.emit()
            return
        if self.webtoon_mode:
            step = int(self.viewport().height() * 0.8)
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Right):
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() + step)
            elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Left):
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - step)
            else:
                super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Right: self.next_page()
        elif event.key() == Qt.Key.Key_Left: self.prev_page()
        else: super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.XButton1:
            self.return_to_library.emit()
            event.accept()
            return
        if self.webtoon_mode:
            super().mousePressEvent(event)
            return
        elif event.button() == Qt.MouseButton.RightButton:
            self.fit_to_height()
            self.is_zoomed = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.webtoon_mode:
            return
        scene_pos = self.mapToScene(event.pos())
        self.toggle_zoom(scene_pos)

    def resizeEvent(self, event):
        if self.webtoon_mode:
            if self._wt_ready and self.current_manga and abs(self.viewport().width() - self._wt_target_width) > 5:
                current_idx = self.current_page_idx
                self._wt_rebuild_layout()
                self._wt_scroll_to_page(current_idx)
                self._wt_update_visible()
            super().resizeEvent(event)
            return
        if not self.is_zoomed: self.fit_to_height()
        super().resizeEvent(event)

class ReaderPage(QWidget):
    back_clicked = pyqtSignal()
    next_chapter_requested = pyqtSignal()
    to_info_clicked = pyqtSignal()

    def __init__(self, reader_view):
        super().__init__()
        self.reader_view = reader_view

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.top_panel = QWidget()
        self.top_panel.setObjectName("TopPanel")
        panel_layout = QHBoxLayout(self.top_panel)
        panel_layout.setContentsMargins(15, 5, 15, 5)

        self.btn_back = QPushButton("← В библиотеку")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_clicked.emit)

        self.title_label = QLabel("")
        self.title_label.setObjectName("ReaderTitle")

        panel_layout.addWidget(self.btn_back)

        self.btn_to_info = QPushButton("📖 К манге")
        self.btn_to_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_to_info.clicked.connect(self.to_info_clicked.emit)
        panel_layout.addWidget(self.btn_to_info)

        self.btn_toc = QPushButton("📑 Оглавление")
        self.btn_toc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toc.clicked.connect(self.show_toc)
        panel_layout.addWidget(self.btn_toc)

        self.btn_webtoon = QPushButton("📜 Вертикальный режим")
        self.btn_webtoon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_webtoon.setCheckable(True)
        self.btn_webtoon.setStyleSheet("QPushButton:checked { background-color: #ff9800; color: black; font-weight: bold; }")
        self.btn_webtoon.clicked.connect(self.toggle_webtoon_mode)
        panel_layout.addWidget(self.btn_webtoon)

        panel_layout.addWidget(self.title_label)
        panel_layout.addStretch()

        main_layout.addWidget(self.top_panel)

        self.viewer_container = QWidget()
        container_layout = QGridLayout(self.viewer_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.reader_view, 0, 0)

        self.hint_frame = QWidget()
        self.hint_frame.setObjectName("HintFrame")
        self.hint_frame.setStyleSheet("""
            QWidget#HintFrame {
                background-color: rgba(25, 25, 25, 0.95);
                border: 2px solid #ff9800;
                border-radius: 8px;
            }
            QLabel { color: white; font-size: 12px; }
        """)
        hint_layout = QVBoxLayout(self.hint_frame)
        hint_layout.setContentsMargins(12, 12, 12, 12)
        hint_layout.setSpacing(8)

        hint_header = QHBoxLayout()
        lbl_hint_title = QLabel("<b>Навигация ридера:</b>")
        lbl_hint_title.setStyleSheet("color: #ff9800; font-size: 13px; font-weight: bold;")
        btn_close_x = QPushButton("×")
        btn_close_x.setFixedSize(18, 18)
        btn_close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close_x.setStyleSheet("background: transparent; border: none; color: white; font-size: 16px; font-weight: bold; padding: 0;")
        btn_close_x.clicked.connect(self.hint_frame.hide)

        hint_header.addWidget(lbl_hint_title)
        hint_header.addStretch()
        hint_header.addWidget(btn_close_x)
        hint_layout.addLayout(hint_header)

        lbl_hint = QLabel(
            "• Стрелки влево/вправо или Колесико — Листать страницы<br>"
            "• <b>Ctrl + Колесико</b> — Изменение масштаба страницы (и в вертикальном режиме)<br>"
            "• <b>ПКМ (Правый клик)</b> — Мгновенный сброс масштаба<br>"
            "• Двойной клик ЛКМ — Приблизить в точку<br>"
            "• «📜 Вертикальный режим» вверху — непрерывная лента вместо страниц<br>"
            "• <b>F11</b> — Полноэкранный режим<br>"
            "• Esc — Вернуться в главное меню"
        )
        btn_close_hint = QPushButton("Понятно, больше не показывать")
        btn_close_hint.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close_hint.setStyleSheet("background-color: #ff9800; color: black; font-weight: bold; border: none; padding: 6px; border-radius: 4px;")
        btn_close_hint.clicked.connect(self.close_hint_permanently)

        hint_layout.addWidget(lbl_hint)
        hint_layout.addWidget(btn_close_hint)
        container_layout.addWidget(self.hint_frame, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.hint_frame.hide()

        self.next_chap_widget = QWidget()
        nc_layout = QHBoxLayout(self.next_chap_widget)
        nc_layout.setContentsMargins(0, 0, 25, 25)
        self.btn_next_chap = QPushButton("Следующая глава →")
        self.btn_next_chap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next_chap.setStyleSheet("""
            QPushButton {
                background-color: #28a745; color: white; padding: 12px 24px;
                font-weight: bold; font-size: 14px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        self.btn_next_chap.clicked.connect(self.next_chapter_requested.emit)
        nc_layout.addStretch()
        nc_layout.addWidget(self.btn_next_chap)

        container_layout.addWidget(self.next_chap_widget, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.next_chap_widget.hide()

        main_layout.addWidget(self.viewer_container)

        self.bottom_panel = QWidget()
        self.bottom_panel.setObjectName("BottomPanel")
        bottom_layout = QHBoxLayout(self.bottom_panel)
        bottom_layout.setContentsMargins(20, 5, 20, 5)

        self.btn_page_jump = QPushButton("1 из 1")
        self.btn_page_jump.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_jump.clicked.connect(self.show_jump_dialog)

        self.page_slider = QSlider(Qt.Orientation.Horizontal)
        self.page_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.page_slider.sliderMoved.connect(self.handle_slider_move)

        bottom_layout.addWidget(self.btn_page_jump)
        bottom_layout.addWidget(self.page_slider)
        main_layout.addWidget(self.bottom_panel)

        self.reader_view.last_page_reached.connect(self.toggle_next_chapter_button)

    def close_hint_permanently(self):
        self.hint_frame.hide()
        self.reader_view.main_window.config["show_navigation_hint"] = False
        self.reader_view.main_window.save_config()

    def handle_slider_move(self, value):
        self.reader_view.current_page_idx = value - 1
        self.reader_view.show_page()

    def show_jump_dialog(self):
        if not self.reader_view.current_manga: return
        total = len(self.reader_view.current_manga.pages)
        if total <= 0: return
        current = self.reader_view.current_page_idx + 1
        val, ok = QInputDialog.getInt(self, "Перейти к странице", f"Введите страницу (1-{total}):", current, 1, total)
        if ok:
            self.reader_view.current_page_idx = val - 1
            self.reader_view.show_page()

    def set_title(self, text):
        self.title_label.setText(text)

    def toggle_webtoon_mode(self):
        enabled = self.btn_webtoon.isChecked()
        self.reader_view.set_webtoon_mode(enabled)
        manga = self.reader_view.current_manga
        if manga and self.reader_view.main_window:
            self.reader_view.main_window.set_webtoon_pref(manga.path, enabled)

    def sync_webtoon_button(self):
        """Подтягивает состояние кнопки под фактический режим ридера
        (вызывается после открытия манги — режим определяется сохранённым
        для неё предпочтением)."""
        self.btn_webtoon.blockSignals(True)
        self.btn_webtoon.setChecked(self.reader_view.webtoon_mode)
        self.btn_webtoon.blockSignals(False)

    def toggle_next_chapter_button(self, visible):
        if visible and self.has_next_chapter():
            self.next_chap_widget.show()
        else:
            self.next_chap_widget.hide()

    def show_toc(self):
        """Показывает диалог с оглавлением"""
        if not self.reader_view.current_manga:
            QMessageBox.information(self, "Оглавление", "Ничего не открыто")
            return

        manga = self.reader_view.current_manga
        chapters = self.get_chapter_list(manga)

        if not chapters:
            QMessageBox.information(self, "Оглавление", "Нет доступных глав")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Оглавление")
        dialog.setMinimumSize(400, 500)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Выберите главу:"))
        self.toc_list = QListWidget()
        for ch in chapters:
            self.toc_list.addItem(ch)
        layout.addWidget(self.toc_list)

        btn_go = QPushButton("📖 Перейти к главе")
        btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_go.clicked.connect(lambda: self.go_to_chapter(dialog, manga))
        layout.addWidget(btn_go)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(dialog.reject)
        layout.addWidget(btn_cancel)

        self.toc_list.itemDoubleClicked.connect(lambda: self.go_to_chapter(dialog, manga))

        dialog.exec()

    def get_chapter_list(self, manga):
        """Возвращает список глав (общая логика вынесена в app.models)"""
        return _shared_get_chapter_list(manga)

    def get_first_page_of_chapter(self, manga, chapter_name):
        """Возвращает индекс первой страницы главы (общая логика вынесена в app.models)"""
        return _shared_get_first_page_of_chapter(manga, chapter_name)

    def go_to_chapter(self, dialog, manga):
        """Переходит к выбранной главе"""
        current_item = self.toc_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Оглавление", "Выберите главу из списка")
            return

        chapter_name = current_item.text()

        page_num = self.get_first_page_of_chapter(manga, chapter_name)

        if page_num >= 0:
            self.reader_view.current_page_idx = page_num
            self.reader_view.show_page()
            dialog.accept()
        else:
            QMessageBox.warning(self, "Ошибка", f"Не удалось найти главу: {chapter_name}")

        return -1

    def has_next_chapter(self):
        if not self.reader_view.current_manga: return False
        current_path = self.reader_view.current_manga.path
        parent_dir = os.path.dirname(current_path)
        try:
            siblings = natsorted([os.path.join(parent_dir, f) for f in os.listdir(parent_dir)
                                  if (os.path.isfile(os.path.join(parent_dir, f)) and f.lower().endswith(ARCHIVE_EXTENSIONS))
                                  or (os.path.isdir(os.path.join(parent_dir, f)) and not f.startswith('.'))])
            idx = siblings.index(current_path)
            return idx < len(siblings) - 1
        except Exception: return False

    def _extract_number(self, name):
        """Извлекает число из названия главы для сортировки"""
        nums = re.findall(r'\d+', name)
        return int(nums[0]) if nums else 0
