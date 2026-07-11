import logging
import re
import html

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QInputDialog, QMenu, QFrame
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QThread
import requests

from app import info_data
from app.models import get_chapter_list, get_first_page_of_chapter
from app.library_cards import STATUS_LABELS, RATING_LABELS, _add_status_actions, _add_rating_actions

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_VOLUME_NUM_RE = re.compile(r"\d+")

STATUS_TEXT = dict(STATUS_LABELS)
RATING_TEXT = dict(RATING_LABELS)


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

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_panel = QWidget()
        top_panel.setObjectName("TopPanel")
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(15, 5, 15, 5)

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
        main_layout.addWidget(top_panel)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(24, 24, 24, 24)
        body_layout.setSpacing(28)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(270, 385)
        self.cover_label.setStyleSheet("background-color: #2a2a2a; border-radius: 8px;")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setScaledContents(False)
        body_layout.addWidget(self.cover_label, 0, Qt.AlignmentFlag.AlignTop)

        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 23px; font-weight: bold;")
        right_col.addWidget(self.title_label)

        self.original_title_label = QLabel("")
        self.original_title_label.setWordWrap(True)
        self.original_title_label.setStyleSheet("color: #999999; font-style: italic; font-size: 13px;")
        right_col.addWidget(self.original_title_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.btn_status = QPushButton()
        self.btn_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_status.setStyleSheet(_TAG_BUTTON_STYLE)
        self.btn_status.clicked.connect(self._show_status_menu)
        status_row.addWidget(self.btn_status)

        self.btn_rating = QPushButton()
        self.btn_rating.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rating.setStyleSheet(_TAG_BUTTON_STYLE)
        self.btn_rating.clicked.connect(self._show_rating_menu)
        status_row.addWidget(self.btn_rating)

        status_row.addStretch()
        right_col.addLayout(status_row)

        right_col.addWidget(_separator())

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background-color: #4a2f1a; color: #ffcc80; padding: 8px 12px; "
            "border-radius: 6px; border: 1px solid #ff9800;"
        )
        self.status_label.hide()
        right_col.addWidget(self.status_label)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setTextFormat(Qt.TextFormat.RichText)
        self.meta_label.setStyleSheet("font-size: 13px;")
        right_col.addWidget(self.meta_label)

        self.btn_read = QPushButton("▶  Читать")
        self.btn_read.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_read.setStyleSheet(
            "QPushButton { background-color: #ff9800; color: black; font-weight: bold; font-size: 14px; "
            "padding: 8px 22px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background-color: #ffb74d; }"
        )
        self.btn_read.clicked.connect(lambda: self.current_manga and self.read_clicked.emit(self.current_manga))
        right_col.addWidget(self.btn_read, 0, Qt.AlignmentFlag.AlignLeft)

        self.volumes_label = _section_header("Локальные тома")
        right_col.addWidget(self.volumes_label)
        self.volumes_list = QTreeWidget()
        self.volumes_list.setHeaderHidden(True)
        self.volumes_list.setMaximumHeight(220)
        self.volumes_list.itemClicked.connect(self._on_volume_clicked)
        right_col.addWidget(self.volumes_list)
        self.volumes_label.hide()
        self.volumes_list.hide()

        self.local_chapters_label = _section_header("Главы в файле")
        right_col.addWidget(self.local_chapters_label)
        self.local_chapters_list = QListWidget()
        self.local_chapters_list.setMaximumHeight(150)
        self.local_chapters_list.itemDoubleClicked.connect(self._on_local_chapter_double_clicked)
        right_col.addWidget(self.local_chapters_list)
        self.local_chapters_label.hide()
        self.local_chapters_list.hide()

        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        self.description_label.setTextFormat(Qt.TextFormat.RichText)
        self.description_label.setOpenExternalLinks(True)
        self.description_label.setStyleSheet("font-size: 13px; line-height: 140%;")
        right_col.addWidget(self.description_label)

        right_col.addWidget(_section_header("Главы на MangaDex/MAL"))
        self.chapters_list = QListWidget()
        self.chapters_list.setMaximumHeight(220)
        right_col.addWidget(self.chapters_list)

        right_col.addStretch()
        body_layout.addLayout(right_col, 1)

        scroll.setWidget(body)
        main_layout.addWidget(scroll, 1)

    def show_for(self, manga_item, search_title=None, status="none", rating=None,
                 cache_key=None, local_volumes=None):
        self.current_manga = manga_item
        self._search_title = search_title or manga_item.display_name
        self._cache_key = cache_key or manga_item.path
        self.set_status_rating(status, rating)
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
            self.volumes_label.hide()
            self.volumes_list.hide()
            return
        self.volumes_label.show()
        self.volumes_list.show()
        current_path = self.current_manga.path if self.current_manga else None

        for entry in local_volumes:
            label = _format_volume_label(entry["name"])
            is_internal = entry.get("internal", False)

            if entry["chapters"] and not is_internal:
                # Внешние главы-файлы (Hellsing/Berserk/Tokyo Ghoul-re): раскрывающийся том,
                # дети — отдельные файлы глав.
                parent_item = QTreeWidgetItem([label])
                parent_item.setData(0, Qt.ItemDataRole.UserRole, None)
                expand_this = False
                for ch_name, ch_path in entry["chapters"]:
                    is_current = ch_path == current_path
                    child = QTreeWidgetItem([f"▶ {ch_name}" if is_current else ch_name])
                    child.setData(0, Qt.ItemDataRole.UserRole, ("volume", ch_path))
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

    def _populate_local_chapters(self):
        self.local_chapters_list.clear()
        self._local_chapters = []
        if self._local_volumes or not self.current_manga:
            self.local_chapters_label.hide()
            self.local_chapters_list.hide()
            return
        try:
            chapters = get_chapter_list(self.current_manga)
        except Exception as e:
            logging.error(f"Ошибка получения списка глав {self.current_manga.path}: {e}")
            chapters = []
        if len(chapters) <= 1:
            self.local_chapters_label.hide()
            self.local_chapters_list.hide()
            return
        self._local_chapters = chapters
        self.local_chapters_label.show()
        self.local_chapters_list.show()
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
        self.meta_label.setText("")
        self.original_title_label.setText("")
        self.description_label.setText("")
        self.chapters_list.clear()

    def _show_status_banner(self, text):
        self.status_label.setText(text)
        self.status_label.show()

    def _hide_status_banner(self):
        self.status_label.setText("")
        self.status_label.hide()

    def _render_loading(self):
        self.title_label.setText(self.current_manga.display_name if self.current_manga else "")
        self.original_title_label.setText("")
        self.meta_label.setText("Загрузка информации...")
        self.description_label.setText("")
        self._hide_status_banner()
        self.chapters_list.clear()
        self.cover_label.setPixmap(QPixmap())

    def _render(self, info):
        title = info.get("title_ru") or info.get("title") or (self.current_manga.display_name if self.current_manga else "")
        self.title_label.setText(title)

        original = info.get("title") or ""
        self.original_title_label.setText(original if original and original != title else "")

        rows = []
        if info.get("author"):
            rows.append(("Автор", html.escape(info["author"])))
        if info.get("artist") and info.get("artist") != info.get("author"):
            rows.append(("Художник", html.escape(info["artist"])))
        if info.get("genres"):
            rows.append(("Жанры", html.escape(", ".join(info["genres"]))))
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

        html_rows = "".join(
            f'<tr><td style="color:#999999; padding-right:12px; padding-bottom:4px; vertical-align:top;">{label}:</td>'
            f'<td style="padding-bottom:4px;">{value}</td></tr>'
            for label, value in rows
        )
        self.meta_label.setText(f"<table>{html_rows}</table>")

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
        self.cover_label.setPixmap(pixmap.scaled(
            self.cover_label.width(), self.cover_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))


_TAG_BUTTON_STYLE = (
    "QPushButton { padding: 5px 14px; border-radius: 14px; border: 1px solid #555; font-size: 12px; }"
    "QPushButton:hover { border-color: #ff9800; }"
)


def _section_header(text):
    label = QLabel(text)
    label.setStyleSheet("color: #ff9800; font-weight: bold; font-size: 13px; margin-top: 6px;")
    return label


def _separator():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #444;")
    line.setFixedHeight(1)
    return line
