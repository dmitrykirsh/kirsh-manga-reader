import os
import re
import json
import shutil
import urllib.request
import requests
import logging
from pathlib import Path

from natsort import natsorted
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QScrollArea, QGridLayout, QLabel,
    QStackedWidget, QProgressBar, QDialog, QMessageBox, QTabBar,
    QSlider, QInputDialog, QLineEdit)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer, QEvent

from app.constants import (DATA_DIR, CONFIG_PATH, VALID_EXTENSIONS,
    ARCHIVE_EXTENSIONS, APP_VERSION, GITHUB_REPO, is_newer_version)
from app.cache import BoundedCache, COVER_CACHE
from app.models import MangaItem, get_custom_cover_path, get_first_page_of_chapter, get_chapter_groups
from app.reader_view import ReaderView, ReaderPage
from app.library_cards import LibraryCard, LibraryFolderCard
from app.dialogs import SettingsDialog, DownloadDialog, run_auth_with_dialog
from app.info_page import InfoPage
from app import info_data
import mangadex_client
from mangalib_downloader import MangaLibDownloadThread
from comx_downloader import ComXDownloadThread
from group_downloader import GroupDownloadThread


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kirsh Manga Reader")

        icon_path = os.path.join(DATA_DIR, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1350, 850)
        self._volumes_cache = {}
        self.config = {
            "root_dir": "", "progress": {}, "theme": "Тёмная", "accent": "Розовый",
            "archive_cache": {}, "card_width": 220, "show_navigation_hint": True,
            "metadata": {}, "webtoon_mode": {}
        }
        self.load_config()

        MangaItem.GLOBAL_CACHE = BoundedCache(300, self.config.get("archive_cache", {}))
        self.current_dir = self.config["root_dir"]

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.main_library_page = QWidget()
        main_lib_layout = QVBoxLayout(self.main_library_page)
        main_lib_layout.setContentsMargins(15, 15, 15, 15)

        top_bar = QHBoxLayout()

        # Кнопка "На уровень вверх" (слева)
        self.btn_lib_back = QPushButton("← На уровень вверх")
        self.btn_lib_back.setStyleSheet("padding: 8px 16px; font-weight: bold; border-radius: 4px;")
        self.btn_lib_back.clicked.connect(self.navigate_up)
        self.btn_lib_back.hide()
        top_bar.addWidget(self.btn_lib_back)

        # РАСТЯГИВАЕМ ВСЁ ВЛЕВО, ЧТОБЫ СЛАЙДЕР, ПОИСК И КНОПКИ БЫЛИ СПРАВА
        top_bar.addStretch()

        # СЛАЙДЕР РАЗМЕРА
        top_bar.addWidget(QLabel("Размер:"))
        self.card_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.card_width_slider.setRange(150, 350)
        self.card_width_slider.setValue(self.config.get("card_width", 220))
        self.card_width_slider.setFixedWidth(150)
        self.card_width_slider.valueChanged.connect(self.on_card_width_changed)
        top_bar.addWidget(self.card_width_slider)
        top_bar.addSpacing(15)

        # ПОИСК (между слайдером размера и кнопкой загрузки).
        # Строка поиска и кнопка 🔍/✕ лежат прямо в top_bar, без обёртки.
        # Ширина self.search_input переключается через setFixedWidth(0/300)
        # (а не через min/max + Expanding-политику — так поведение
        # предсказуемо и не "уезжает" дальше, чем на реальную ширину поля).
        # Так как слайдер и весь этот блок стоят ПОСЛЕ единственного
        # addStretch(), при раскрытии поиска резинка сжимается ровно на
        # ширину раскрывшегося поля — и слайдер сдвигается влево ровно на
        # эту же величину (как и было задумано изначально).
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Поиск манги...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 6px 12px;
                border: 2px solid #444;
                border-radius: 6px;
                background-color: #2a2a2a;
                color: white;
            }
            QLineEdit:focus {
                border: 2px solid #ff9800;
            }
        """)
        self.search_input.textChanged.connect(self.on_search_changed)
        self.search_input.setVisible(False)
        self.search_input.setFixedHeight(36)
        self.search_input.setFixedWidth(0)
        self.search_input.installEventFilter(self)
        top_bar.addWidget(self.search_input)
        top_bar.addSpacing(4)

        self.btn_search = QPushButton("🔍")
        self.btn_search.setFixedSize(36, 36)
        self.btn_search.setStyleSheet("font-size: 18px; border-radius: 4px;")
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.setToolTip("Показать строку поиска")
        self.btn_search.setCheckable(True)
        self.btn_search.clicked.connect(self.toggle_search_input)
        top_bar.addWidget(self.btn_search)
        top_bar.addSpacing(8)

        # КНОПКИ СПРАВА
        self.btn_download = QPushButton("📥")
        self.btn_download.setFixedSize(36, 36)
        self.btn_download.setStyleSheet("font-size: 18px; border-radius: 4px;")
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.setToolTip("Скачать мангу по ссылке (MangaLib, HentaiLib, SlashLIB, Com-X.life, ReadManga/MintManga)")
        self.btn_download.clicked.connect(self.show_download_dialog)
        top_bar.addWidget(self.btn_download)

        top_bar.addSpacing(8)

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(36, 36)
        self.btn_settings.setStyleSheet("font-size: 18px; border-radius: 4px;")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("Настройки программы")
        self.btn_settings.clicked.connect(self.open_settings)
        top_bar.addWidget(self.btn_settings)

        top_bar.addSpacing(10)

        main_lib_layout.addLayout(top_bar)

        tab_bar_container = QWidget()
        tab_bar_layout = QHBoxLayout(tab_bar_container)
        tab_bar_layout.setContentsMargins(0, 0, 0, 10)

        self.custom_tab_bar = QTabBar()
        self.custom_tab_bar.addTab("Библиотека")
        self.custom_tab_bar.addTab("Продолжить чтение")
        self.custom_tab_bar.addTab("Завершено")
        self.custom_tab_bar.addTab("В планах")
        self.custom_tab_bar.currentChanged.connect(self.handle_tab_changed)

        tab_bar_layout.addStretch()
        tab_bar_layout.addWidget(self.custom_tab_bar)
        tab_bar_layout.addStretch()
        main_lib_layout.addWidget(tab_bar_container)

        self.tab_stack = QStackedWidget()

        self.scroll_all = QScrollArea()
        self.grid_all = QGridLayout()
        self.init_tab_scroll(self.scroll_all, self.grid_all)

        self.scroll_reading = QScrollArea()
        self.grid_reading = QGridLayout()
        self.init_tab_scroll(self.scroll_reading, self.grid_reading)

        self.scroll_done = QScrollArea()
        self.grid_done = QGridLayout()
        self.init_tab_scroll(self.scroll_done, self.grid_done)

        self.scroll_planned = QScrollArea()
        self.grid_planned = QGridLayout()
        self.init_tab_scroll(self.scroll_planned, self.grid_planned)

        self.tab_stack.addWidget(self.scroll_all)
        self.tab_stack.addWidget(self.scroll_reading)
        self.tab_stack.addWidget(self.scroll_done)
        self.tab_stack.addWidget(self.scroll_planned)

        # Полный список карточек текущей папки библиотеки (не зависит от того,
        # что сейчас реально лежит в self.grid_all — нужен для поиска).
        self.library_widgets = []
        self.search_empty_label = None

        main_lib_layout.addWidget(self.tab_stack, 1)

        self.empty_btn = QPushButton("Библиотека пуста.\nНажмите сюда, чтобы указать папку с мангой в настройках.")
        self.empty_btn.setObjectName("EmptyLibraryButton")
        self.empty_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.empty_btn.clicked.connect(self.open_settings)
        main_lib_layout.addWidget(self.empty_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.empty_btn.hide()

        self.reader_view = ReaderView(self)
        self.reader_page = ReaderPage(self.reader_view)

        self.reader_view.return_to_library.connect(self.show_library)
        self.reader_page.back_clicked.connect(self.show_library)
        self.reader_page.next_chapter_requested.connect(self.open_next_chapter)
        self.reader_page.to_info_clicked.connect(self.handle_reader_to_info)
        self.reader_view.progress_changed.connect(self.update_reader_ui_progress)

        self.info_page = InfoPage()
        self.info_page.back_clicked.connect(self.show_library)
        self.info_page.read_clicked.connect(self.open_manga)
        self.info_page.status_rating_changed.connect(self.handle_info_page_status_rating)
        self.info_page.volume_selected.connect(self.handle_info_volume_selected)
        self.info_page.chapter_selected.connect(self.handle_info_chapter_selected)

        self.stacked_widget.addWidget(self.main_library_page)
        self.stacked_widget.addWidget(self.reader_page)
        self.stacked_widget.addWidget(self.info_page)

        self.apply_theme()

        if self.current_dir and os.path.exists(self.current_dir):
            QTimer.singleShot(50, lambda: self.scan_library(self.current_dir))
        else:
            QTimer.singleShot(50, lambda: self.scan_library(""))

        QTimer.singleShot(2000, lambda: self.check_for_updates(manual=False))

    def _abort_download_for_auth_cancel(self):
        """Останавливает текущее скачивание, когда пользователь отменяет
        авторизацию, всплывшую сама по себе во время закачки."""
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.request_cancel()
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()

    def handle_comx_auth(self):
        """Обработка авторизации для Com-X, всплывшей во время скачивания
        (вызывается в главном потоке). Показывает то же окно ожидания
        входа, что и явная кнопка "Авторизоваться" в диалоге скачивания —
        с кнопками "Я вошёл" и "Отмена" сразу под рукой."""
        if not hasattr(self, 'loader') or not isinstance(self.loader, ComXDownloadThread):
            return
        dlg = run_auth_with_dialog(self, self.loader, "com-x.life")
        dlg.cancelled.connect(self._abort_download_for_auth_cancel)

    def handle_group_auth(self):
        """Обработка авторизации для ReadManga/MintManga, всплывшей во время
        скачивания (вызывается в главном потоке)."""
        if not hasattr(self, 'loader') or not isinstance(self.loader, GroupDownloadThread):
            return
        dlg = run_auth_with_dialog(self, self.loader, self.loader.domain)
        dlg.cancelled.connect(self._abort_download_for_auth_cancel)

    def init_tab_scroll(self, scroll_area, grid_layout):
        scroll_area.setWidgetResizable(True)
        container = QWidget()
        grid_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid_layout.setSpacing(20)
        container.setLayout(grid_layout)
        scroll_area.setWidget(container)

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    for k, v in loaded.items():
                        self.config[k] = v
            except Exception as e:
                logging.error(f"Ошибка: {e}")

    def save_config(self):
        self.config["archive_cache"] = MangaItem.GLOBAL_CACHE
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    def get_item_status(self, path):
        return self.config.get("metadata", {}).get(path, {}).get("status", "none")

    def get_item_rating(self, path):
        return self.config.get("metadata", {}).get(path, {}).get("rating")

    def set_item_status(self, path, status):
        meta = self.config.setdefault("metadata", {})
        if status == "none":
            if path in meta:
                meta[path].pop("status", None)
                if not meta[path]: meta.pop(path)
        else:
            meta.setdefault(path, {})["status"] = status
        self.save_config()

    def set_item_rating(self, path, rating):
        meta = self.config.setdefault("metadata", {})
        if rating in (None, "none"):
            if path in meta:
                meta[path].pop("rating", None)
                if not meta[path]: meta.pop(path)
        else:
            meta.setdefault(path, {})["rating"] = int(rating)
        self.save_config()

    def get_webtoon_pref(self, path):
        return self.config.get("webtoon_mode", {}).get(path, False)

    def set_webtoon_pref(self, path, enabled):
        prefs = self.config.setdefault("webtoon_mode", {})
        if enabled:
            prefs[path] = True
        else:
            prefs.pop(path, None)
        self.save_config()

    def on_card_width_changed(self, value):
        self.config["card_width"] = value
        for grid in [self.grid_reading, self.grid_done, self.grid_planned]:
            for i in range(grid.count()):
                widget = grid.itemAt(i).widget()
                if widget and hasattr(widget, 'update_size'):
                    widget.update_size(value)
        # self.library_widgets содержит ВСЕ карточки библиотеки, включая
        # скрытые фильтром поиска (их сейчас нет в self.grid_all).
        for widget in self.library_widgets:
            if hasattr(widget, 'update_size'):
                widget.update_size(value)
        self.save_config()
        self.refresh_grid_layout()

    def update_reader_ui_progress(self, path, page_idx, total_pages):
        self.config["progress"][path] = {"page": page_idx, "total": total_pages}
        self.save_config()

        self.reader_page.btn_page_jump.setText(f"{page_idx + 1} из {total_pages}")
        self.reader_page.page_slider.blockSignals(True)
        self.reader_page.page_slider.setRange(1, total_pages)
        self.reader_page.page_slider.setValue(page_idx + 1)
        self.reader_page.page_slider.blockSignals(False)

    def open_settings(self):
        dlg = SettingsDialog(self, self.config["root_dir"], self.config["theme"], self.config["accent"])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.rescan_requested:
                COVER_CACHE.clear()
                MangaItem.GLOBAL_CACHE = BoundedCache(max_size=300)
            self.config["root_dir"] = dlg.lbl_path.text()
            self.config["theme"] = dlg.combo_theme.currentText()
            self.config["accent"] = dlg.combo_accent.currentText()
            self.current_dir = dlg.lbl_path.text()
            self.save_config()
            self.apply_theme()
            self.scan_library(self.current_dir)

    def check_for_updates(self, manual=False):
        if getattr(self, "_update_check_thread", None) and self._update_check_thread.is_alive():
            return

        import datetime
        if not manual:
            last_check = self.config.get("last_update_check", "")
            if last_check == datetime.date.today().isoformat():
                return

        import threading
        self._update_check_manual = manual
        self._update_check_result = {"version": None, "url": None, "error": None}
        self._update_check_thread = threading.Thread(target=self._update_check_worker, daemon=True)
        self._update_check_thread.start()

        self._update_check_timer = QTimer(self)
        self._update_check_timer.timeout.connect(self._poll_update_check)
        self._update_check_timer.start(300)

    def _update_check_worker(self):
        """Выполняется в фоновом потоке — сюда НЕЛЬЗЯ добавлять QMessageBox и другие вызовы интерфейса"""
        result = {"version": None, "url": None, "error": None}
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=6, headers={"Accept": "application/vnd.github+json"}
            )
            if resp.status_code == 200:
                data = resp.json()
                tag = (data.get("tag_name") or "").lstrip("vV")
                if tag and is_newer_version(tag, APP_VERSION):
                    result["version"] = tag
                    result["url"] = data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest"
            # Не-200 (например 404 — релизов ещё нет, или лимит запросов GitHub API)
            # тихо считаем "обновлений нет", без ошибки для пользователя.
        except Exception as e:
            result["error"] = str(e)
            logging.warning(f"Не удалось проверить обновления: {e}")
        self._update_check_result = result

    def _poll_update_check(self):
        if self._update_check_thread.is_alive():
            return
        self._update_check_timer.stop()

        import datetime
        result = self._update_check_result
        self.config["last_update_check"] = datetime.date.today().isoformat()
        self.save_config()

        if result["version"]:
            reply = QMessageBox.question(
                self, "Доступно обновление",
                f"Доступна новая версия {result['version']} (у вас {APP_VERSION}).\n\nОткрыть страницу релиза?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                import webbrowser
                webbrowser.open(result["url"])
        elif self._update_check_manual:
            if result["error"]:
                QMessageBox.warning(self, "Проверка обновлений", "Не удалось проверить обновления. Проверьте подключение к интернету.")
            else:
                QMessageBox.information(self, "Проверка обновлений", f"У вас установлена последняя версия ({APP_VERSION}).")

    def export_progress(self):
        if not self.config.get("root_dir"):
            QMessageBox.warning(self, "Ошибка", "Сначала укажите корневую папку в настройках")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт прогресса чтения", "kirsh_manga_progress.json", "JSON (*.json)"
        )
        if not file_path:
            return

        root = self.config["root_dir"]
        exported = {}
        for path, data in self.config["progress"].items():
            try:
                rel = os.path.relpath(path, root)
            except ValueError:
                continue
            if rel.startswith(".."):
                continue
            exported[rel] = data

        payload = {"app": "KirshMangaReader", "format_version": 1, "progress": exported}
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Экспорт завершён", f"Экспортировано записей: {len(exported)}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл:\n{e}")

    def import_progress(self):
        if not self.config.get("root_dir"):
            QMessageBox.warning(self, "Ошибка", "Сначала укажите корневую папку в настройках")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Импорт прогресса чтения", "", "JSON (*.json)")
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать файл:\n{e}")
            return

        imported = payload.get("progress") if isinstance(payload, dict) else None
        if not isinstance(imported, dict):
            QMessageBox.critical(self, "Ошибка", "Файл не похож на экспорт прогресса Kirsh Manga Reader.")
            return

        root = self.config["root_dir"]
        resolved = {}
        missing = 0
        for rel, data in imported.items():
            abs_path = os.path.normpath(os.path.join(root, rel))
            if os.path.exists(abs_path):
                resolved[abs_path] = data
            else:
                missing += 1

        if not resolved:
            QMessageBox.warning(self, "Импорт прогресса", "Ни один путь из файла не найден в текущей библиотеке.")
            return

        overlap = sum(1 for p in resolved if p in self.config["progress"])
        mode = "merge"
        if overlap:
            reply = QMessageBox.question(
                self, "Импорт прогресса",
                f"Для {overlap} элементов уже есть сохранённый прогресс на этом устройстве.\n\n"
                "Заменить его данными из файла (Да) или оставить существующий и добавить только новое (Нет)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            mode = "replace" if reply == QMessageBox.StandardButton.Yes else "merge"

        added = 0
        for p, data in resolved.items():
            if p in self.config["progress"] and mode == "merge":
                continue
            self.config["progress"][p] = data
            added += 1

        self.save_config()
        self.scan_library(self.current_dir)

        msg = f"Импортировано записей: {added}."
        if missing:
            msg += f"\nНе найдено на диске и пропущено: {missing}."
        QMessageBox.information(self, "Импорт завершён", msg)

    def apply_theme(self):
        theme = self.config.get("theme", "Тёмная")
        accent_name = self.config.get("accent", "Розовый")

        THEMES = {
            "Тёмная": "#1e1e1e", "Глубокая чёрная": "#000000", "Тёмно-синяя": "#111a2e",
            "Тёмно-красная": "#2b1111", "Тёмно-зелёная": "#112415", "Тёмно-фиолетовая": "#1f112e",
            "Тёмно-серая": "#2d3238"
        }
        PANELS = {
            "Тёмная": "#2a2a2a", "Глубокая чёрная": "#111111", "Тёмно-синяя": "#1b263b",
            "Тёмно-красная": "#3d1818", "Тёмно-зелёная": "#1b331e", "Тёмно-фиолетовая": "#2e1b40",
            "Тёмно-серая": "#3a3f47"
        }
        ACCENTS = {
            "Розовый": "#ff69b4", "Оранжевый": "#ff9800", "Синий": "#0078D7",
            "Зелёный": "#28a745", "Красный": "#dc3545", "Фиолетовый": "#9c27b0"
        }

        bg = THEMES.get(theme, "#1e1e1e")
        panel = PANELS.get(theme, "#2a2a2a")
        accent = ACCENTS.get(accent_name, "#ff69b4")
        text = "#ffffff"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {bg}; color: {text}; }}
            QScrollArea, QScrollArea QWidget {{ background-color: {bg}; border: none; }}
            QPushButton {{ background-color: {panel}; color: {text}; border: 1px solid #444; padding: 6px; border-radius: 4px; }}
            QPushButton:hover {{ background-color: {accent}; color: white; }}
            QDialog {{ background-color: {bg}; }}
            QComboBox, QCheckBox {{ background-color: {panel}; color: {text}; padding: 4px; border: 1px solid #444; }}

            QProgressBar {{ background-color: #333; border: none; border-radius: 3px; }}
            QProgressBar::chunk {{ background-color: {accent}; border-radius: 3px; }}

        QSlider::groove:horizontal {{
            border: 1px solid #444;
            height: 8px;
            background: {panel};
            border-radius: 4px;
        }}
        QSlider::sub-page:horizontal {{
            background: {accent};
            border-radius: 4px;
        }}
        QSlider::add-page:horizontal {{
            background: transparent;
        }}
        QSlider::handle:horizontal {{
            background: {text};
            border: 1px solid #444;
            width: 16px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {accent};
        }}

            /* === НОВЫЕ СТИЛИ ДЛЯ СКРОЛЛБАРА === */
            QScrollBar:vertical {{
                border: none;
                background: {panel};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {accent};
                min-height: 30px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {text};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
                height: 0px;
            }}

            QScrollBar:horizontal {{
                border: none;
                background: {panel};
                height: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {accent};
                min-width: 30px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {text};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
                width: 0px;
            }}
            /* ================================== */

            QTabBar {{ background: transparent; }}
            QTabBar::tab {{
                background: {panel};
                color: {text};
                padding: 8px 24px;
                font-weight: bold;
                border: 2px solid {accent};
                border-radius: 12px;
                margin: 0 4px;
            }}
            QTabBar::tab:hover {{ background: {accent}; color: white; }}
            QTabBar::tab:selected {{ background: {accent}; color: white; border: 2px solid {accent}; }}

            QTabWidget::pane {{ border: 1px solid #444; background: {bg}; border-radius: 8px; margin-top: -1px; }}

            QPushButton#EmptyLibraryButton {{
                background-color: {panel};
                border: 2px dashed {accent};
                padding: 30px;
                font-size: 15px;
                font-weight: bold;
                border-radius: 12px;
                min-width: 400px;
            }}
            QPushButton#EmptyLibraryButton:hover {{
                background-color: {accent};
                color: white;
                border-style: solid;
            }}

            QMenu {{ background-color: {panel}; color: {text}; border: 1px solid #444; padding: 5px; border-radius: 6px; }}
            QMenu::item {{ padding: 6px 28px 6px 16px; border-radius: 4px; background-color: transparent; }}
            QMenu::item:selected {{ background-color: {accent}; color: white; }}
            QMenu::separator {{ height: 1px; background-color: #444; margin: 4px 6px; }}
        """)
        self.reader_view.setStyleSheet(f"background-color: {bg}; border: none;")
        self.reader_page.top_panel.setStyleSheet(f"background-color: {panel}; max-height: 50px;")
        self.reader_page.bottom_panel.setStyleSheet(f"background-color: {panel}; max-height: 50px;")
        self.reader_page.title_label.setStyleSheet(f"color: {text}; font-weight: bold; font-size: 14px; margin-left: 15px;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.stacked_widget.currentWidget() == self.main_library_page:
            self.refresh_grid_layout()

    def refresh_grid_layout(self):
        idx = self.custom_tab_bar.currentIndex()
        if idx == 0: self.rearrange_grid(self.grid_all)
        elif idx == 1: self.rearrange_grid(self.grid_reading)
        elif idx == 2: self.rearrange_grid(self.grid_done)
        elif idx == 3: self.rearrange_grid(self.grid_planned)

    def rearrange_grid(self, grid):
        if grid.count() == 0: return
        max_cols = self.get_max_columns()
        widgets = []
        for i in range(grid.count()):
            w = grid.itemAt(i).widget()
            if w: widgets.append(w)

        for w in widgets: grid.removeWidget(w)

        row, col = 0, 0
        for w in widgets:
            grid.addWidget(w, row, col)
            col += 1
            if col >= max_cols: col = 0; row += 1

    def eventFilter(self, obj, event):
        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape and self.search_input.isVisible():
                self.toggle_search_input(False)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.search_input.isVisible():
            self.toggle_search_input(False)
            event.accept()
            return
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen(): self.showNormal()
            else: self.showFullScreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.XButton1:
            if self.stacked_widget.currentWidget() == self.main_library_page:
                self.navigate_up()
                event.accept()
                return
        super().mousePressEvent(event)

    def navigate_up(self):
        if self.current_dir and self.current_dir != self.config["root_dir"]:
            self.scan_library(os.path.dirname(self.current_dir))

    def handle_tab_changed(self, index):
        if self.search_input.isVisible():
            self.custom_tab_bar.blockSignals(True)
            self.custom_tab_bar.setCurrentIndex(0)
            self.custom_tab_bar.blockSignals(False)
            self.tab_stack.setCurrentIndex(0)
            return

        if index == 0:
            self.tab_stack.setCurrentIndex(0)
            self.scan_library(self.current_dir)
        elif index == 1:
            self.tab_stack.setCurrentIndex(1)
            self.build_flat_tab("reading")
        elif index == 2:
            self.tab_stack.setCurrentIndex(2)
            self.build_flat_tab("done")
        elif index == 3:
            self.tab_stack.setCurrentIndex(3)
            self.build_flat_tab("planned")

    def toggle_search_input(self, visible=None):
        if visible is None:
            visible = not self.search_input.isVisible()

        self.btn_search.setChecked(visible)
        self.btn_search.setText("✕" if visible else "🔍")
        self.btn_search.setToolTip("Закрыть поиск" if visible else "Показать строку поиска")

        if visible:
            self.stacked_widget.setCurrentWidget(self.main_library_page)
            if self.custom_tab_bar.currentIndex() != 0:
                self.custom_tab_bar.blockSignals(True)
                self.custom_tab_bar.setCurrentIndex(0)
                self.custom_tab_bar.blockSignals(False)
                self.tab_stack.setCurrentIndex(0)
            self.search_input.setFixedWidth(300)
            self.search_input.setVisible(True)
            self.search_input.setFocus()
        else:
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
            self.search_input.setFixedWidth(0)
            self.search_input.setVisible(False)
            self.apply_library_filter("")

    def get_card_title(self, widget):
        """Возвращает полное (не обрезанное эллипсисом) название карточки для поиска."""
        manga_item = getattr(widget, 'manga_item', None)
        if manga_item is not None:
            return manga_item.display_name.lower()
        display_name = getattr(widget, 'display_name', None)
        if display_name is not None:
            return display_name.lower()
        return ""

    def apply_library_filter(self, text):
        """Фильтрует вкладку "Библиотека" по тексту.

        Всегда фильтрует полный список self.library_widgets, а не то, что
        сейчас лежит в self.grid_all — иначе после сужения результата
        стёртые из сетки карточки было бы уже не вернуть.
        """
        text = text.lower().strip()

        if self.search_empty_label is not None:
            self.grid_all.removeWidget(self.search_empty_label)
            self.search_empty_label.deleteLater()
            self.search_empty_label = None

        for widget in self.library_widgets:
            self.grid_all.removeWidget(widget)

        row, col = 0, 0
        max_cols = self.get_max_columns()
        matched_count = 0
        for widget in self.library_widgets:
            if text and text not in self.get_card_title(widget):
                widget.setVisible(False)
                continue
            widget.setVisible(True)
            self.grid_all.addWidget(widget, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
            matched_count += 1

        if text and matched_count == 0:
            self.search_empty_label = QLabel("Ничего не найдено для этого запроса")
            self.search_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.search_empty_label.setStyleSheet("color: #888; font-size: 16px; font-weight: bold;")
            self.grid_all.addWidget(self.search_empty_label, 0, 0)

    def calculate_folder_progress(self, folder_path):
        total_pages_in_folder = 0
        total_pages_read = 0
        try:
            for root, dirs, files in os.walk(folder_path):
                has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in files)
                has_archives = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in files)
                valid_dirs = [d for d in dirs if not d.startswith('.')]

                if has_images and not has_archives and not valid_dirs:
                    manga = MangaItem(root)
                    pages_count = len(manga.pages)
                    total_pages_in_folder += pages_count

                    prog_data = self.config["progress"].get(root, None)
                    if isinstance(prog_data, dict):
                        total_pages_read += min(prog_data.get("page", 0) + 1, pages_count)
                else:
                    for f in files:
                        if f.lower().endswith(ARCHIVE_EXTENSIONS):
                            p = os.path.join(root, f)
                            manga = MangaItem(p)
                            pages_count = len(manga.pages)
                            total_pages_in_folder += pages_count

                            prog_data = self.config["progress"].get(p, None)
                            if isinstance(prog_data, dict):
                                total_pages_read += min(prog_data.get("page", 0) + 1, pages_count)
        except Exception as e:
            logging.error(f"Ошибка: {e}")
        return total_pages_read, total_pages_in_folder

    def clear_grid(self, grid):
        if grid == self.grid_all:
            self.search_empty_label = None
        for i in reversed(range(grid.count())):
            w = grid.itemAt(i).widget()
            if w:
                w.deleteLater()

    def show_empty_state(self, grid, message="Тут пока пусто"):
        self.clear_grid(grid)
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 16px; font-weight: bold;")
        grid.addWidget(label, 0, 0)

    def get_max_columns(self):
        width = self.width()
        card_w = self.config.get("card_width", 220) + 20
        cols = (width - 60) // card_w
        return max(1, cols)

    def scan_library(self, target_dir):
        if self.custom_tab_bar.currentIndex() != 0: return
        self.current_dir = target_dir
        self.btn_lib_back.setVisible(self.current_dir != self.config["root_dir"])
        self.clear_grid(self.grid_all)
        self.library_widgets = []

        if not target_dir or not os.path.exists(target_dir):
            self.tab_stack.hide()
            self.empty_btn.show()
            return

        try:
            raw_items = os.listdir(target_dir)
        except Exception as e:
            logging.error(f"Ошибка чтения папки {target_dir}: {e}")
            raw_items = []

        row, col = 0, 0
        max_cols = self.get_max_columns()
        c_width = self.config.get("card_width", 220)
        has_items = False

        for item in natsorted(raw_items):
            item_path = os.path.join(target_dir, item)
            if os.path.isfile(item_path) and item.lower().endswith(ARCHIVE_EXTENSIONS):
                manga = MangaItem(item_path)
                if manga.pages:
                    card = self.create_manga_card(manga)
                    self.grid_all.addWidget(card, row, col)
                    self.library_widgets.append(card)
                    col += 1
                    has_items = True
            elif os.path.isdir(item_path):
                if item.startswith('.'): continue
                try:
                    sub_files = os.listdir(item_path)
                except Exception as e:
                    logging.error(f"Не удалось прочитать папку {item_path}: {e}")
                    sub_files = []

                has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in sub_files)
                has_archives = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in sub_files)
                has_subdirs = any(os.path.isdir(os.path.join(item_path, d)) for d in sub_files)

                if has_images and not has_archives and not has_subdirs:
                    manga = MangaItem(item_path)
                    if manga.pages:
                        card = self.create_manga_card(manga)
                        self.grid_all.addWidget(card, row, col)
                        self.library_widgets.append(card)
                        col += 1
                        has_items = True
                else:
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    f_card = LibraryFolderCard(item_path, item, f_read, f_total, card_width=c_width,
                                                status=self.get_item_status(item_path), rating=self.get_item_rating(item_path))
                    if has_archives or self._is_series_folder(item_path):
                        f_card.clicked.connect(self.open_series_info)
                    else:
                        f_card.clicked.connect(self.scan_library)
                    f_card.menu_action_triggered.connect(self.handle_menu_action)
                    self.grid_all.addWidget(f_card, row, col)
                    self.library_widgets.append(f_card)
                    col += 1
                    has_items = True

            if col >= max_cols:
                col = 0
                row += 1

        if not has_items:
            if target_dir == self.config["root_dir"]:
                self.tab_stack.hide()
                self.empty_btn.show()
            else:
                self.tab_stack.show()
                self.empty_btn.hide()
                self.show_empty_state(self.grid_all, "В этой папке пока пусто")
        else:
            self.empty_btn.hide()
            self.tab_stack.show()

        if self.search_input.isVisible():
            self.apply_library_filter(self.search_input.text())

    def on_search_changed(self, text):
        self.apply_library_filter(text)

    def rename_item(self, path):
        """Переименовывает папку или файл манги. Для файлов расширение (.cbz/.cbr/...)
        не показывается в поле ввода и сохраняется автоматически — как в Проводнике,
        чтобы нельзя было случайно стереть его при переименовании."""
        old_name = os.path.basename(path)
        if os.path.isfile(path):
            base_name, ext = os.path.splitext(old_name)
        else:
            base_name, ext = old_name, ""

        new_base, ok = QInputDialog.getText(
            self,
            "Переименовать",
            f"Введите новое имя для:\n{old_name}",
            text=base_name
        )

        if not ok or not new_base.strip():
            return

        new_base = new_base.strip()
        for char in r'<>:"/\|?*':
            new_base = new_base.replace(char, '_')

        new_name = new_base + ext

        if new_name == old_name:
            return

        parent_dir = os.path.dirname(path)
        new_path = os.path.join(parent_dir, new_name)

        if os.path.exists(new_path):
            QMessageBox.warning(self, "Ошибка", f"Файл или папка с именем '{new_name}' уже существует!")
            return

        try:
            os.rename(path, new_path)
            self._volumes_cache.clear()

            if path in self.config["progress"]:
                self.config["progress"][new_path] = self.config["progress"].pop(path)
            if path in self.config.get("metadata", {}):
                self.config["metadata"][new_path] = self.config["metadata"].pop(path)
            if path in COVER_CACHE:
                COVER_CACHE[new_path] = COVER_CACHE.pop(path)
            if path in MangaItem.GLOBAL_CACHE:
                MangaItem.GLOBAL_CACHE[new_path] = MangaItem.GLOBAL_CACHE.pop(path)

            self.save_config()
            self.scan_library(self.current_dir)
            QMessageBox.information(self, "Успех", f"Переименовано в:\n{new_name}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось переименовать:\n{str(e)}")

    def create_manga_card(self, manga, custom_handler=None):
        prog = self.config["progress"].get(manga.path, {})
        last_page = prog.get("page", 0) if isinstance(prog, dict) else 0
        card = LibraryCard(manga, current_page=last_page, card_width=self.config.get("card_width", 220),
                            status=self.get_item_status(manga.path), rating=self.get_item_rating(manga.path))
        if custom_handler:
            card.clicked.connect(custom_handler)
        else:
            card.clicked.connect(self.open_manga_info)
        card.menu_action_triggered.connect(self.handle_menu_action)
        return card

    def build_flat_tab(self, mode):
        grid = {"reading": self.grid_reading, "planned": self.grid_planned}.get(mode, self.grid_done)
        self.clear_grid(grid)
        self.btn_lib_back.hide()

        row, col = 0, 0
        max_cols = self.get_max_columns()
        root = self.config["root_dir"]
        c_width = self.config.get("card_width", 220)
        has_items = False

        if not root or not os.path.exists(root):
            self.show_empty_state(grid, "Тут пока пусто")
            return

        if mode == "reading":
            reading_top_items = set()
            for path, data in self.config["progress"].items():
                if not os.path.exists(path): continue
                if isinstance(data, dict):
                    if 0 < data.get("page", 0) < (data.get("total", 0) - 1):
                        rel = os.path.relpath(path, root)
                        top_item_name = rel.split(os.sep)[0]
                        reading_top_items.add(os.path.join(root, top_item_name))

            for item_path in natsorted(list(reading_top_items)):
                if os.path.isfile(item_path) and item_path.lower().endswith(ARCHIVE_EXTENSIONS):
                    manga = MangaItem(item_path)
                    if manga.pages:
                        card = self.create_manga_card(manga)
                        grid.addWidget(card, row, col)
                        col += 1
                        has_items = True
                elif os.path.isdir(item_path):
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    f_card = LibraryFolderCard(item_path, os.path.basename(item_path), f_read, f_total, card_width=c_width,
                                                status=self.get_item_status(item_path), rating=self.get_item_rating(item_path))
                    f_card.clicked.connect(self.open_folder_manga_continue)
                    f_card.menu_action_triggered.connect(self.handle_menu_action)
                    grid.addWidget(f_card, row, col)
                    col += 1
                    has_items = True
                if col >= max_cols: col = 0; row += 1
        elif mode == "planned":
            try:
                raw_top_items = os.listdir(root)
            except Exception as e:
                logging.error(f"Ошибка: {e}")
                raw_top_items = []

            planned_top_items = [
                os.path.join(root, item) for item in raw_top_items
                if not item.startswith('.') and self.get_item_status(os.path.join(root, item)) == "planned"
            ]

            for item_path in natsorted(planned_top_items):
                if os.path.isfile(item_path) and item_path.lower().endswith(ARCHIVE_EXTENSIONS):
                    manga = MangaItem(item_path)
                    if manga.pages:
                        card = self.create_manga_card(manga)
                        grid.addWidget(card, row, col)
                        col += 1
                        has_items = True
                elif os.path.isdir(item_path):
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    f_card = LibraryFolderCard(item_path, os.path.basename(item_path), f_read, f_total, card_width=c_width,
                                                status=self.get_item_status(item_path), rating=self.get_item_rating(item_path))
                    f_card.clicked.connect(self.open_folder_manga_planned)
                    f_card.menu_action_triggered.connect(self.handle_menu_action)
                    grid.addWidget(f_card, row, col)
                    col += 1
                    has_items = True
                if col >= max_cols: col = 0; row += 1
        else:
            completed_top_items = set()
            try:
                raw_top_items = os.listdir(root)
            except Exception as e:
                logging.error(f"Ошибка: {e}")
                raw_top_items = []

            for item in raw_top_items:
                if item.startswith('.'): continue
                item_path = os.path.join(root, item)

                if os.path.isfile(item_path) and item_path.lower().endswith(ARCHIVE_EXTENSIONS):
                    prog_data = self.config["progress"].get(item_path, None)
                    if isinstance(prog_data, dict):
                        if prog_data.get("page", 0) >= (prog_data.get("total", 0) - 1) and prog_data.get("total", 0) > 0:
                            completed_top_items.add(item_path)
                elif os.path.isdir(item_path):
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    if f_total > 0 and f_read >= (f_total - 5):
                        completed_top_items.add(item_path)

            for item_path in natsorted(list(completed_top_items)):
                if os.path.isfile(item_path):
                    manga = MangaItem(item_path)
                    if manga.pages:
                        card = self.create_manga_card(manga, custom_handler=self.open_manga_at_end)
                        grid.addWidget(card, row, col)
                        col += 1
                        has_items = True
                else:
                    f_read, f_total = self.calculate_folder_progress(item_path)
                    f_card = LibraryFolderCard(item_path, os.path.basename(item_path), f_read, f_total, card_width=c_width,
                                                status=self.get_item_status(item_path), rating=self.get_item_rating(item_path))
                    f_card.clicked.connect(self.open_folder_manga_completed)
                    f_card.menu_action_triggered.connect(self.handle_menu_action)
                    grid.addWidget(f_card, row, col)
                    col += 1
                    has_items = True
                if col >= max_cols: col = 0; row += 1

        if not has_items:
            self.show_empty_state(grid, "Тут пока пусто")

    def open_folder_manga_continue(self, folder_path):
        norm_folder = os.path.abspath(folder_path) + os.sep
        target_path = None

        for p, data in self.config["progress"].items():
            if os.path.abspath(p).startswith(norm_folder):
                if isinstance(data, dict):
                    if 0 < data.get("page", 0) < (data.get("total", 0) - 1):
                        target_path = p
                        break

        if not target_path:
            try:
                for root, _, files in os.walk(folder_path):
                    manga_files = [os.path.join(root, f) for f in files if f.lower().endswith(ARCHIVE_EXTENSIONS)]
                    if manga_files:
                        target_path = natsorted(manga_files)[0]
                        break
            except Exception as e:
                logging.error(f"Ошибка поиска манги в {folder_path}: {e}")

        if target_path:
            manga = MangaItem(target_path)
            if manga.pages:
                self.open_manga(manga)

    def open_folder_manga_completed(self, folder_path):
        all_files = []
        try:
            for root, _, files in os.walk(folder_path):
                for f in files:
                    if f.lower().endswith(ARCHIVE_EXTENSIONS):
                        all_files.append(os.path.join(root, f))
        except Exception as e:
            logging.error(f"Ошибка поиска файлов в {folder_path}: {e}")

        if all_files:
            last_file = natsorted(all_files)[-1]
            manga = MangaItem(last_file)
            if manga.pages:
                self.open_manga_at_end(manga)

    def open_folder_manga_planned(self, folder_path):
        """Открывает папку из вкладки "В планах" — либо сразу страница информации (для серии томов), либо заходит внутрь."""
        if self._is_series_folder(folder_path):
            self.open_series_info(folder_path)
            return
        self.custom_tab_bar.blockSignals(True)
        self.custom_tab_bar.setCurrentIndex(0)
        self.custom_tab_bar.blockSignals(False)
        self.tab_stack.setCurrentIndex(0)
        self.scan_library(folder_path)

    def open_manga_at_end(self, manga_item):
        total_pages = len(manga_item.pages)
        last_page = max(0, total_pages - 1)
        self.reader_page.set_title(manga_item.display_name)
        self.reader_view.load_manga(manga_item, last_page)
        self.reader_page.sync_webtoon_button()
        self.stacked_widget.setCurrentWidget(self.reader_page)
        self.reader_page.hint_frame.setVisible(self.config.get("show_navigation_hint", True))

    def handle_menu_action(self, action_type, item_path):
        if action_type == "reset":
            self.reset_item_progress(item_path)
            self.scan_library(self.current_dir)
        elif action_type == "mark_read":
            self.mark_item_as_read(item_path)
            self.scan_library(self.current_dir)
        elif action_type == "change_cover":
            self.change_item_cover(item_path)
            self.scan_library(self.current_dir)
        elif action_type == "remove_cover":
            self.remove_item_cover(item_path)
            self.scan_library(self.current_dir)
        elif action_type == "open_folder":
            self.open_in_explorer(item_path)
        elif action_type == "rename":
            self.rename_item(item_path)
        elif action_type == "delete":
            self.delete_item_from_device(item_path)
            self.scan_library(self.current_dir)
        elif action_type.startswith("status:"):
            self.set_item_status(item_path, action_type.split(":", 1)[1])
            self._refresh_current_tab()
        elif action_type.startswith("rating:"):
            self.set_item_rating(item_path, action_type.split(":", 1)[1])
            self._refresh_current_tab()

    def _refresh_current_tab(self):
        idx = self.custom_tab_bar.currentIndex()
        if idx == 0:
            self.scan_library(self.current_dir)
        else:
            self.handle_tab_changed(idx)

    def change_item_cover(self, item_path):
        msg = QMessageBox(self)
        msg.setWindowTitle("Изменить обложку")
        msg.setText("Выберите способ установки кастомной обложки:")
        btn_file = msg.addButton("Из файла на ПК", QMessageBox.ButtonRole.ActionRole)
        btn_url = msg.addButton("По ссылке из сети", QMessageBox.ButtonRole.ActionRole)
        btn_mangadex = msg.addButton("Загрузить с MangaDex", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        target_cp = get_custom_cover_path(item_path)

        if msg.clickedButton() == btn_file:
            file_path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
            if file_path:
                try:
                    shutil.copy(file_path, target_cp)
                    if item_path in COVER_CACHE: COVER_CACHE.pop(item_path)
                except Exception as e: QMessageBox.critical(self, "Ошибка", f"Не удалось скопировать файл: {e}")

        elif msg.clickedButton() == btn_url:
            url, ok = QInputDialog.getText(self, "Обложка по ссылке", "Вставьте URL-ссылку на картинку:")
            if ok and url.strip():
                try:
                    req = urllib.request.Request(url.strip(), headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = response.read()
                    with open(target_cp, 'wb') as f:
                        f.write(data)
                    if item_path in COVER_CACHE: COVER_CACHE.pop(item_path)
                except Exception as e: QMessageBox.critical(self, "Ошибка", f"Не удалось скачать: {e}")

        elif msg.clickedButton() == btn_mangadex:
            self._set_cover_from_mangadex(item_path, target_cp)

    def _set_cover_from_mangadex(self, item_path, target_cp):
        cached = info_data.load_cached_info(item_path)
        cover_url = cached.get("cover_url") if cached else None

        if not cover_url:
            query = os.path.splitext(os.path.basename(item_path))[0]
            try:
                results = info_data.search_mangadex_best(query, limit=1)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось найти мангу на MangaDex: {e}")
                return
            if results:
                cover_url = mangadex_client.get_cover_url(results[0]["id"], results[0].get("relationships"))

        if not cover_url:
            QMessageBox.warning(self, "Не найдено", "Не удалось найти обложку на MangaDex для этой манги.")
            return

        try:
            resp = requests.get(cover_url, timeout=15)
            resp.raise_for_status()
            with open(target_cp, 'wb') as f:
                f.write(resp.content)
            if item_path in COVER_CACHE: COVER_CACHE.pop(item_path)
            QMessageBox.information(self, "Успех", "Обложка с MangaDex установлена.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось скачать обложку: {e}")

    def remove_item_cover(self, item_path):
        target_cp = get_custom_cover_path(item_path)
        if os.path.exists(target_cp):
            try:
                os.remove(target_cp)
                if item_path in COVER_CACHE: COVER_CACHE.pop(item_path)
                QMessageBox.information(self, "Успех", "Кастомная обложка успешно удалена.")
            except Exception as e: QMessageBox.critical(self, "Ошибка", f"Не удалось удалить файл обложки: {e}")
        else:
            QMessageBox.information(self, "Инфо", "У этого элемента нет кастомной обложки.")

    def reset_item_progress(self, path):
        if os.path.isdir(path):
            norm = os.path.abspath(path) + os.sep
            to_remove = [p for p in self.config["progress"] if os.path.abspath(p).startswith(norm)]
            for p in to_remove: self.config["progress"].pop(p, None)
        else:
            self.config["progress"].pop(path, None)
        self.save_config()

    def mark_item_as_read(self, path):
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                has_images = any(f.lower().endswith(VALID_EXTENSIONS) for f in files)
                has_archives = any(f.lower().endswith(ARCHIVE_EXTENSIONS) for f in files)
                valid_dirs = [d for d in dirs if not d.startswith('.')]

                if has_images and not has_archives and not valid_dirs:
                    manga = MangaItem(root)
                    if manga.pages:
                        self.config["progress"][root] = {"page": len(manga.pages)-1, "total": len(manga.pages)}
                else:
                    for f in files:
                        if f.lower().endswith(ARCHIVE_EXTENSIONS):
                            p = os.path.join(root, f)
                            m = MangaItem(p)
                            if m.pages:
                                self.config["progress"][p] = {"page": len(m.pages)-1, "total": len(m.pages)}
        else:
            m = MangaItem(path)
            if m.pages:
                self.config["progress"][path] = {"page": len(m.pages)-1, "total": len(m.pages)}
        self.save_config()

    def delete_item_from_device(self, path):
        reply = QMessageBox.question(self, 'Удаление', f"Удалить файл/папку с устройства?\n{path}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.reset_item_progress(path)
                if os.path.isdir(path): shutil.rmtree(path)
                else: os.remove(path)
                self._volumes_cache.clear()
                if path in self.config.get("metadata", {}): self.config["metadata"].pop(path)
                if path in COVER_CACHE: COVER_CACHE.pop(path)
                if path in MangaItem.GLOBAL_CACHE: MangaItem.GLOBAL_CACHE.pop(path)
                target_cp = get_custom_cover_path(path)
                if os.path.exists(target_cp): os.remove(target_cp)
            except Exception as e: QMessageBox.critical(self, "Ошибка", str(e))

    def open_in_explorer(self, path):
        """Открывает папку в проводнике и выделяет файл/папку"""
        import subprocess

        path = os.path.abspath(path)

        if not os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", f"Путь не существует:\n{path}")
            return

        if os.path.isdir(path):
            os.startfile(path)
        else:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                subprocess.Popen(f'explorer /select, "{path}"')

    _VOL_FOLDER_RE = re.compile(r"^(vol|том)\b", re.IGNORECASE)

    def open_manga_info(self, manga_item):
        parent_dir = os.path.dirname(manga_item.path)
        root_dir = os.path.normpath(self.config.get("root_dir", ""))
        parent_name = os.path.basename(parent_dir)
        grandparent_dir = os.path.dirname(parent_dir)

        if os.path.normpath(parent_dir) == root_dir:
            is_nested = False
            series_dir = None
        elif self._VOL_FOLDER_RE.match(parent_name) and os.path.normpath(grandparent_dir) != os.path.normpath(parent_dir):
            # Родительская папка сама выглядит как том (Том NN/volNN) с главами внутри —
            # значит настоящий корень серии на уровень выше (см. Hellsing/Berserk/Tokyo Ghoul-re).
            is_nested = True
            series_dir = grandparent_dir
        else:
            is_nested = True
            series_dir = parent_dir

        if is_nested:
            search_title = os.path.basename(series_dir)
            cache_key = series_dir
            local_volumes = self._list_local_volumes(series_dir)
        else:
            search_title = manga_item.display_name
            cache_key = manga_item.path
            local_volumes = []

        self.info_page.show_for(
            manga_item, search_title=search_title, cache_key=cache_key, local_volumes=local_volumes,
            status=self.get_item_status(cache_key), rating=self.get_item_rating(cache_key),
        )
        self.stacked_widget.setCurrentWidget(self.info_page)

    def open_series_info(self, folder_path):
        local_volumes = self._list_local_volumes(folder_path)
        first_manga = None
        for entry in local_volumes:
            if entry["chapters"] and not entry.get("internal"):
                candidate_paths = [c[1] for c in entry["chapters"]]
            else:
                candidate_paths = [entry["path"]]
            for p in candidate_paths:
                if not p: continue
                candidate = MangaItem(p)
                if candidate.pages:
                    first_manga = candidate
                    break
            if first_manga:
                break

        if not first_manga:
            self.scan_library(folder_path)
            return

        search_title = os.path.basename(folder_path)
        self.info_page.show_for(
            first_manga, search_title=search_title, cache_key=folder_path, local_volumes=local_volumes,
            status=self.get_item_status(folder_path), rating=self.get_item_rating(folder_path),
        )
        self.stacked_widget.setCurrentWidget(self.info_page)

    def _is_series_folder(self, folder_path):
        """Папка считается сериями, если внутри есть архивы напрямую, либо если хотя бы
        один подкаталог (том) сам содержит архивы (например Hellsing/Том 01/Глава 001.cbr
        или Made in Abyss/Vol. 01/Made in Abyss - vol 01.cbz)."""
        try:
            sub_files = os.listdir(folder_path)
        except Exception:
            return False
        for f in sub_files:
            full = os.path.join(folder_path, f)
            if os.path.isfile(full) and f.lower().endswith(ARCHIVE_EXTENSIONS):
                return True
            if os.path.isdir(full) and not f.startswith('.'):
                try:
                    inner = os.listdir(full)
                except Exception:
                    continue
                if any(n.lower().endswith(ARCHIVE_EXTENSIONS) and os.path.isfile(os.path.join(full, n)) for n in inner):
                    return True
        return False

    def _classify_volume_folder(self, folder_path):
        """Если папка тома сама содержит несколько глав-архивов (или несколько подпапок-глав),
        возвращает список (имя_главы, путь). Если папка — это уже читаемый том (обычные
        страницы или ровно один архив внутри), возвращает None."""
        try:
            names = natsorted(os.listdir(folder_path))
        except Exception:
            return None
        archives = [n for n in names if os.path.isfile(os.path.join(folder_path, n)) and n.lower().endswith(ARCHIVE_EXTENSIONS)]
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

    def _resolve_single_archive(self, folder_path):
        """Если в папке тома лежит ровно один архив (например 'Vol. 01/Made in Abyss - vol 01.cbz'),
        возвращает путь к этому архиву, чтобы работать с томом прозрачно, как с обычным файлом."""
        try:
            names = os.listdir(folder_path)
        except Exception:
            return None
        archives = [n for n in names if os.path.isfile(os.path.join(folder_path, n)) and n.lower().endswith(ARCHIVE_EXTENSIONS)]
        if len(archives) == 1:
            return os.path.join(folder_path, archives[0])
        return None

    def _build_volume_entry(self, name, path):
        """Обычный том (один читаемый файл/папка). Дополнительно проверяет, не разбит ли он
        сам на главы ВНУТРИ себя (например Highschool of the Dead: vol1.cbz содержит несколько
        Ch_NNN-подпапок) — если да, помечает entry["internal"]=True, и главы в дереве томов
        будут открывать тот же файл с нужной страницы, а не отдельные файлы."""
        entry = {"name": name, "path": path, "chapters": None, "internal": False}
        try:
            manga = MangaItem(path)
            if manga.pages:
                internal_chapters = get_chapter_groups(manga)
                if internal_chapters:
                    entry["chapters"] = [(ch, None) for ch in internal_chapters]
                    entry["internal"] = True
        except Exception as e:
            logging.error(f"Не удалось проверить внутренние главы {path}: {e}")
        return entry

    def _list_local_volumes(self, folder_path):
        """Список томов папки-серии, закэшированный на время сессии — построение списка
        открывает КАЖДЫЙ том, чтобы проверить внутренние главы (см. _build_volume_entry),
        и без кэша пересчитывалось бы заново при каждом переключении тома на странице
        информации. Кэш сбрасывается при переименовании/удалении, см. rename_item /
        delete_item_from_device."""
        if folder_path in self._volumes_cache:
            return self._volumes_cache[folder_path]
        result = self._compute_local_volumes(folder_path)
        self._volumes_cache[folder_path] = result
        return result

    def _compute_local_volumes(self, folder_path):
        """Список томов папки-серии. Каждый элемент — dict {"name", "path", "chapters", "internal"}:
        - "chapters" is None — "path" уже читаемый файл/папка (обычный том без глав внутри);
        - "chapters" задан и internal=False — список (имя_главы, путь_к_отдельному_файлу),
          если сам том состоит из нескольких глав-архивов (Hellsing/Berserk/Tokyo Ghoul-re:
          'Том 01/Глава 001.cbr, Глава 002.cbr...');
        - "chapters" задан и internal=True — том сам является одним файлом, но внутри разбит
          на главы (Highschool of the Dead: vol1.cbz содержит Ch_NNN) — "path" остаётся тем же
          файлом для всех глав, различается только стартовая страница.
        Если для тома существуют и архив, и одноимённая папка (vol1.cbz и распакованная vol1/
        рядом), архив считается основным, а папка-дубликат пропускается."""
        try:
            names = natsorted(os.listdir(folder_path))
        except Exception:
            return []
        archive_stems = {
            os.path.splitext(n)[0] for n in names
            if os.path.isfile(os.path.join(folder_path, n)) and n.lower().endswith(ARCHIVE_EXTENSIONS)
        }
        volumes = []
        seen = set()
        for name in names:
            path = os.path.join(folder_path, name)
            if os.path.isfile(path) and name.lower().endswith(ARCHIVE_EXTENSIONS):
                stem = os.path.splitext(name)[0]
                if stem in seen: continue
                seen.add(stem)
                volumes.append(self._build_volume_entry(stem, path))
            elif os.path.isdir(path) and not name.startswith('.'):
                if name in archive_stems or name in seen: continue
                seen.add(name)
                chapters = self._classify_volume_folder(path)
                if chapters is not None:
                    volumes.append({"name": name, "path": None, "chapters": chapters, "internal": False})
                else:
                    single = self._resolve_single_archive(path)
                    volumes.append(self._build_volume_entry(name, single or path))
        return volumes

    def handle_info_page_status_rating(self, action_type, item_path):
        self.handle_menu_action(action_type, item_path)
        self.info_page.set_status_rating(self.get_item_status(item_path), self.get_item_rating(item_path))

    def handle_info_volume_selected(self, path):
        manga_item = MangaItem(path)
        if manga_item.pages:
            self.open_manga_info(manga_item)
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось открыть выбранный том")

    def handle_info_chapter_selected(self, manga_path, chapter_name):
        manga = MangaItem(manga_path)
        if not manga.pages:
            QMessageBox.warning(self, "Ошибка", "Не удалось открыть том")
            return
        page_idx = get_first_page_of_chapter(manga, chapter_name)
        if page_idx >= 0:
            self.open_manga(manga, start_page=page_idx)
        else:
            QMessageBox.warning(self, "Ошибка", f"Не удалось найти главу: {chapter_name}")

    def open_manga(self, manga_item, start_page=None):
        if start_page is None:
            prog = self.config["progress"].get(manga_item.path, {})
            start_page = prog.get("page", 0) if isinstance(prog, dict) else 0
        self.reader_page.set_title(manga_item.display_name)
        self.reader_view.load_manga(manga_item, start_page)
        self.reader_page.sync_webtoon_button()
        self.stacked_widget.setCurrentWidget(self.reader_page)
        self.reader_page.hint_frame.setVisible(self.config.get("show_navigation_hint", True))

    def handle_reader_to_info(self):
        manga = self.reader_view.current_manga
        if manga:
            manga.close_archive()
            self.open_manga_info(manga)

    def open_next_chapter(self):
        if not self.reader_view.current_manga: return
        current_path = self.reader_view.current_manga.path
        parent_dir = os.path.dirname(current_path)
        try:
            siblings = natsorted([os.path.join(parent_dir, f) for f in os.listdir(parent_dir)
                                  if (os.path.isfile(os.path.join(parent_dir, f)) and f.lower().endswith(ARCHIVE_EXTENSIONS))
                                  or (os.path.isdir(os.path.join(parent_dir, f)) and not f.startswith('.'))])
            idx = siblings.index(current_path)
            if idx < len(siblings) - 1:
                next_path = siblings[idx + 1]
                self.reader_view.current_manga.close_archive()

                next_manga = MangaItem(next_path)
                if next_manga.pages:
                    self.open_manga(next_manga)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка перехода", str(e))

    def show_library(self):
        if self.reader_view.current_manga: self.reader_view.current_manga.close_archive()
        self.stacked_widget.setCurrentWidget(self.main_library_page)
        self.handle_tab_changed(self.custom_tab_bar.currentIndex())

    def show_download_dialog(self):
        dialog = DownloadDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            site, url, output_format = dialog.get_data()
            if not url:
                QMessageBox.warning(self, "Ошибка", "Введите ссылку")
                return

            if not self.config.get("root_dir") or not os.path.exists(self.config["root_dir"]):
                QMessageBox.warning(self, "Ошибка", "Сначала укажите корневую папку для манги в настройках")
                return

            self.start_download(site, url, output_format)

    def start_download(self, site, url, output_format):
        root_dir = self.config["root_dir"]

        if "MangaLib" in site:
            token_path = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'mangalib_token.json'
            token = ""
            if token_path.exists():
                try:
                    with open(token_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        token = data.get("token", "")
                except Exception as e:
                    logging.error(f"Не удалось прочитать токен MangaLib: {e}")
            self.loader = MangaLibDownloadThread(url, root_dir, token=token, output_format=output_format)
        elif "ReadManga" in site:
            self.loader = GroupDownloadThread(url, root_dir, output_format=output_format)
            self.loader.need_auth.connect(self.handle_group_auth)
        else:
            self.loader = ComXDownloadThread(url, root_dir, output_format=output_format)
            self.loader.need_auth.connect(self.handle_comx_auth)

        self.progress_dialog = QDialog(self)
        self.progress_dialog.setWindowTitle("Скачивание")
        self.progress_dialog.setFixedSize(450, 180)
        layout = QVBoxLayout(self.progress_dialog)

        self.progress_label = QLabel("Подготовка...")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_chapter = QLabel("")
        layout.addWidget(self.progress_chapter)

        warning_label = QLabel("⚠️ Не закрывайте это окно до завершения загрузки")
        warning_label.setStyleSheet("color: #ff9800; font-size: 11px; margin-top: 8px;")
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(warning_label)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.cancel_download)
        layout.addWidget(btn_cancel)

        self.loader.progress.connect(self.update_download_progress)
        self.loader.status.connect(self.update_download_status)
        self.loader.finished.connect(self.download_finished)
        self.loader.error.connect(self.download_error)

        self.progress_dialog.show()
        self.loader.start()

    def update_download_progress(self, current, total, chapter_name):
        percent = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)
        self.progress_chapter.setText(f"Глава {current} из {total}: {chapter_name}")

    def update_download_status(self, status):
        self.progress_label.setText(status)

    def cancel_download(self):
        if hasattr(self, 'loader') and self.loader.isRunning():
            # Сначала просим загрузчик остановиться самостоятельно между
            # шагами (закрыть браузер, выйти из циклов ожидания) — жёсткий
            # terminate() обрывает поток мгновенно и может оставить недописанный
            # файл или не закрытый браузер авторизации.
            self.loader.request_cancel()
            if not self.loader.wait(3000):
                self.loader.terminate()
                self.loader.wait()
        self.progress_dialog.close()

    def download_finished(self, manga_title, folder_path):
        self.progress_dialog.close()
        QMessageBox.information(self, "Готово", f"Манга \"{manga_title}\" скачана в:\n{folder_path}")
        self.scan_library(self.config["root_dir"])

    def download_error(self, error_msg):
        self.progress_dialog.close()
        QMessageBox.critical(self, "Ошибка", f"Не удалось скачать:\n{error_msg}")
