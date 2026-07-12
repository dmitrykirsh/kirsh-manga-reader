import os
import re
import json
import logging
import threading
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QDialog, QMessageBox, QComboBox, QTabWidget,
    QLineEdit, QScrollArea)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from app.constants import APP_VERSION
from app import theme
from comx_downloader import ComXDownloadThread
from group_downloader import GroupDownloadThread, GROUP_DOMAINS
from mangahub_downloader import MangaHubDownloadThread

MANGALIB_DOMAINS = ("mangalib.me", "mangalib.org", "hentailib.me", "hentailib.org", "shlib.life", "slashlib.me")


class AuthWaitDialog(QDialog):
    """Общее неблокирующее окно ожидания входа в аккаунт.

    Раньше кнопка "Я вошёл" существовала только внутри диалога скачивания
    и пропадала вместе с ним, как только реальная авторизация запускалась
    сама по себе при попытке скачать без предварительного входа — в
    результате подтвердить вход было просто не из чего. Теперь один и тот
    же диалог используется и при явном нажатии "Авторизоваться", и когда
    авторизация всплывает сама по себе при скачивании — кнопки "Я вошёл"
    и "Отмена" всегда рядом с тем, что реально происходит."""
    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, parent, site_label):
        super().__init__(parent)
        self.setWindowTitle("Авторизация")
        self.setFixedSize(420, 150)
        self.setModal(False)
        self._resolved = False

        layout = QVBoxLayout(self)
        self.status_label = QLabel(f"Открываю браузер для входа на {site_label}...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch()

        btn_row = QHBoxLayout()
        self.btn_confirm = QPushButton("✅ Я вошёл — продолжить")
        self.btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm.clicked.connect(self.confirmed.emit)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_row.addWidget(self.btn_confirm)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

    def set_status(self, text):
        self.status_label.setText(text)

    def mark_resolved(self):
        self._resolved = True

    def _on_cancel_clicked(self):
        self._resolved = True
        self.cancelled.emit()
        self.close()

    def closeEvent(self, event):
        # Крестик окна тоже считаем отменой, если до этого никто явно не
        # подтвердил завершение (успех/отмену/ошибку) через mark_resolved().
        if not self._resolved:
            self._resolved = True
            self.cancelled.emit()
        super().closeEvent(event)


def run_auth_with_dialog(parent, loader, site_label, on_finished=None):
    """Запускает loader.auth_via_browser() в фоновом потоке и показывает
    рядом AuthWaitDialog с живым статусом, кнопкой ручного подтверждения
    и кнопкой отмены. on_finished(cookies_loaded: bool) вызывается один раз
    по завершении (успех/таймаут/отмена/ошибка) в главном потоке.

    Общий код для DownloadDialog (явное нажатие "Авторизоваться") и
    MainWindow (авторизация, всплывшая сама по себе при скачивании) —
    раньше это были два независимых пути с разным поведением."""
    dlg = AuthWaitDialog(parent, site_label)
    dlg.confirmed.connect(loader.confirm_manual_auth)
    dlg.cancelled.connect(loader.request_cancel)
    loader.status.connect(dlg.set_status)

    thread = threading.Thread(target=loader.auth_via_browser, daemon=True)

    timer = QTimer(parent)

    def check_done():
        if thread.is_alive():
            return
        timer.stop()
        dlg.mark_resolved()
        dlg.close()
        if on_finished:
            on_finished(getattr(loader, '_cookies_loaded', False))

    timer.timeout.connect(check_done)

    # Держим ссылки на объекты в атрибутах parent, иначе Python может
    # собрать их мусором раньше, чем поток/таймер успеют отработать.
    parent._active_auth_dialog = dlg
    parent._active_auth_thread = thread
    parent._active_auth_timer = timer

    thread.start()
    timer.start(300)
    dlg.show()
    return dlg


class SettingsDialog(QDialog):
    def __init__(self, parent, current_root, current_theme):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setFixedSize(480, 560)
        self.rescan_requested = False

        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()

        tab_general = QWidget()
        gen_layout = QVBoxLayout(tab_general)

        lbl_app_title = QLabel("Kirsh Manga Reader")
        lbl_app_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff9800;")
        lbl_app_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_app_version = QLabel(f"Версия: {APP_VERSION}")
        lbl_app_version.setStyleSheet("font-size: 12px; color: #888888; margin-bottom: 10px;")
        lbl_app_version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        gen_layout.addWidget(lbl_app_title)
        gen_layout.addWidget(lbl_app_version)
        gen_layout.addSpacing(5)

        gen_layout.addWidget(QLabel("Корневая папка Manga:"))
        self.lbl_path = QLabel(current_root if current_root else "Не выбрана")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("font-weight: bold;")
        gen_layout.addWidget(self.lbl_path)

        btn_browse = QPushButton("Обзор...")
        btn_browse.clicked.connect(self.browse)
        gen_layout.addWidget(btn_browse)
        gen_layout.addSpacing(10)

        gen_layout.addWidget(QLabel("Тема оформления:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(theme.PRESET_ORDER)
        self.combo_theme.setCurrentText(current_theme)
        gen_layout.addWidget(self.combo_theme)

        self.theme_preview = QLabel()
        self.theme_preview.setFixedHeight(28)
        self.theme_preview.setStyleSheet("border-radius: 8px;")
        gen_layout.addWidget(self.theme_preview)
        self.combo_theme.currentTextChanged.connect(self._update_theme_preview)
        self._update_theme_preview(current_theme)
        gen_layout.addSpacing(15)

        gen_layout.addWidget(QLabel("Обновления:"))
        btn_check_update = QPushButton("🔄 Проверить обновления")
        btn_check_update.clicked.connect(lambda: self.parent().check_for_updates(manual=True))
        gen_layout.addWidget(btn_check_update)
        gen_layout.addSpacing(15)

        gen_layout.addWidget(QLabel("Прогресс чтения:"))
        progress_btns_layout = QHBoxLayout()
        btn_export_progress = QPushButton("📤 Экспорт")
        btn_export_progress.clicked.connect(lambda: self.parent().export_progress())
        btn_import_progress = QPushButton("📥 Импорт")
        btn_import_progress.clicked.connect(lambda: self.parent().import_progress())
        progress_btns_layout.addWidget(btn_export_progress)
        progress_btns_layout.addWidget(btn_import_progress)
        gen_layout.addLayout(progress_btns_layout)

        tab_help = QWidget()
        help_layout = QVBoxLayout(tab_help)

        help_text = QLabel(
            "<b>Kirsh Manga Reader</b><br><br>"
            "<b>📖 Чтение манги:</b><br>"
            "• Стрелки влево/вправо или Колесико — Листать страницы<br>"
            "• <b>Ctrl + Колесико</b> — Изменение масштаба страницы (работает и в вертикальном режиме)<br>"
            "• <b>ПКМ (Правый клик)</b> — Сброс масштаба по высоте окна<br>"
            "• Двойной клик ЛКМ — Приблизить в точку<br>"
            "• <b>F11</b> — Полноэкранный режим<br>"
            "• <b>Esc</b> — Вернуться в библиотеку<br><br>"
            "<b>📜 Вертикальный режим (для манхвы/веб-тунов):</b><br>"
            "• Кнопка «📜 Вертикальный режим» вверху ридера — переключает конкретную мангу "
            "на непрерывную ленту вместо постраничного режима<br>"
            "• Запоминается отдельно для каждой манги<br><br>"
            "<b>📖 Страница информации о манге:</b><br>"
            "• Открывается автоматически при клике на серию/тайтл в библиотеке (данные с MangaDex)<br>"
            "• Для многотомных серий строится оглавление том → главы — поддерживаются все "
            "распространённые способы организации файлов (том-архив, том-папка с главами внутри, "
            "архив с главами внутри самого файла)<br>"
            "• Кнопка «📖 К манге» в ридере — вернуться со страницы чтения к странице информации<br>"
            "• Статус и оценка задаются прямо на странице отдельными кнопками<br>"
            "• Кнопка «🔗 Изменить ссылку» — вставьте ссылку на MyAnimeList, если автопоиск на "
            "MangaDex ошибся или ничего не нашёл. Данные по-прежнему берутся с MangaDex (сверка идёт по "
            "ID из ссылки); сам MyAnimeList/Jikan используется только как резерв, если сверка не удалась<br>"
            "• Кнопка «🔄 Обновить» — принудительно обновить данные, если что-то поменялось или "
            "нашлось неверно<br><br>"
            "<b>📥 Скачивание манги:</b><br>"
            "• Кнопка <b>📥</b> на верхней панели — открыть диалог скачивания<br>"
            "• Поддерживаются сайты: <b>MangaLib</b>, <b>HentaiLib</b>, <b>SlashLIB/YaoiLib</b>, "
            "<b>Com-X.life</b>, <b>MangaHub.ru</b>, а также сеть <b>ReadManga/MintManga</b> (SeiManga, Usagi, Zazaza и их зеркала)<br>"
            "• Сайт определяется автоматически по вставленной ссылке<br>"
            "• Для 18+ контента MangaLib/HentaiLib/SlashLIB и для Com-X.life/ReadManga нужна авторизация "
            "(кнопка в диалоге). MangaHub.ru авторизация обычно не требуется — она входит в процесс скачивания сама<br>"
            "• Авторизация через браузер: кнопка «✅ Я вошёл» подтверждает вход вручную, "
            "если автоопределение не сработало; «Отмена» останавливает процесс в любой момент<br>"
            "• Для сайтов, которые блокируют автовход — кнопка «📁 Импортировать куки из файла» "
            "(экспорт куки расширением браузера вроде \"Get cookies.txt LOCALLY\")<br>"
            "• Прогресс скачивания отображается в отдельном окне<br>"
            "• После скачивания манга <b>автоматически добавляется в библиотеку</b><br><br>"
            "<b>🏷 Статус и оценка:</b><br>"
            "• Правый клик по карточке → <b>Статус</b> (читаю / прочитано / в планах / брошено) "
            "и <b>Оценка</b> (1-5 звёзд)<br>"
            "• Отображается бейджем на карточке<br>"
            "• Вкладка <b>«В планах»</b> собирает всё с таким статусом<br><br>"
            "<b>⚙ Управление библиотекой:</b><br>"
            "• <b>Ползунок справа</b> — изменение размера обложек<br>"
            "• <b>Правый клик по карточке</b> — контекстное меню:<br>"
            " • Удалить прогресс / Отметить как прочитанное<br>"
            " • Статус / Оценка<br>"
            " • Изменить / удалить обложку (из файла, по ссылке или автоматически с MangaDex)<br>"
            " • <b>Открыть в проводнике</b> — выделить файл/папку<br>"
            " • Переименовать / Удалить с устройства<br>"
            "• Вкладки: <b>Библиотека</b> / <b>Продолжить чтение</b> / <b>Завершено</b> / <b>В планах</b><br>"
            "• Поиск по библиотеке — кнопка 🔍 рядом со слайдером размера<br><br>"
            "<b>🔑 Авторизация — токен или куки?</b><br>"
            "• <b>MangaLib / HentaiLib / SlashLIB (18+):</b> токен. В диалоге скачивания нажмите "
            "«Получить токен» — один аккаунт работает для всех трёх сайтов<br>"
            "• <b>Com-X.life:</b> куки. В диалоге скачивания нажмите «Авторизоваться»<br>"
            "• <b>ReadManga/MintManga и зеркала:</b> куки. Выберите/введите домен для входа и нажмите "
            "«Авторизоваться»<br>"
            "• <b>MangaHub.ru:</b> куки, но нужны редко — только для приватного/18+ контента, запрашиваются "
            "автоматически по ходу скачивания, если понадобятся<br>"
            "• Браузер откроется автоматически, после входа данные сохранятся; кнопка «✅ Я вошёл» "
            "подтверждает вход вручную, если автоопределение не сработало, «Отмена» — прерывает в любой момент<br><br>"
            "<b>📁 Если сайт блокирует автовход через браузер</b> (для сайтов с куки — Com-X.life, "
            "ReadManga/MintManga и зеркала):<br>"
            "1. Установите расширение браузера "
            "<a href=\"https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc\">"
            "Get cookies.txt LOCALLY</a><br>"
            "2. Войдите в аккаунт на нужном сайте в своём обычном браузере (Chrome/Brave/Edge)<br>"
            "3. Откройте расширение на странице сайта, выберите формат <b>JSON</b> и нажмите <b>Export</b><br>"
            "4. В диалоге скачивания нажмите «📁 Импортировать куки из файла» и выберите сохранённый файл"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("font-size: 12px; line-height: 1.4;")
        help_text.setOpenExternalLinks(True)
        help_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        scroll_help = QScrollArea()
        scroll_help.setWidgetResizable(True)
        scroll_help_content = QWidget()
        sh_layout = QVBoxLayout(scroll_help_content)
        sh_layout.addWidget(help_text)
        scroll_help.setWidget(scroll_help_content)
        help_layout.addWidget(scroll_help)

        self.tab_widget.addTab(tab_general, "Основные")
        self.tab_widget.addTab(tab_help, "Справка")
        main_layout.addWidget(self.tab_widget)

        p = theme.get_preset(current_theme)
        grad = theme.accent_gradient_from(p)

        btn_rescan = QPushButton("🔄 Пересканировать")
        btn_rescan.setStyleSheet(
            f"QPushButton {{ background: {grad}; color: white; padding: 10px; font-weight: 700; border-radius: {theme.RADIUS_SM}px; border: none; }}"
            f"QPushButton:hover {{ background: {p['accent1']}; }}"
        )
        btn_rescan.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rescan.clicked.connect(self.trigger_rescan)
        main_layout.addWidget(btn_rescan)

        btn_save = QPushButton("Сохранить изменения")
        btn_save.setStyleSheet(
            f"QPushButton {{ background: {grad}; color: white; padding: 10px; font-weight: 700; border-radius: {theme.RADIUS_SM}px; border: none; }}"
            f"QPushButton:hover {{ background: {p['accent1']}; }}"
        )
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.accept)
        main_layout.addWidget(btn_save)

    def _update_theme_preview(self, preset_name):
        p = theme.get_preset(preset_name)
        grad = theme.accent_gradient_from(p)
        self.theme_preview.setStyleSheet(
            f"background: {grad}; border-radius: 8px;"
        )

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите корневую папку Manga", self.lbl_path.text())
        if folder:
            self.lbl_path.setText(folder)

    def trigger_rescan(self):
        self.rescan_requested = True
        self.accept()

class DownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Скачать мангу")
        self.setFixedSize(550, 400)
        self.selected_loader = None
        self.url = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Сайт:"))
        self.site_combo = QComboBox()
        self.site_combo.addItems(["MangaLib", "Com-X.life", "ReadManga/MintManga", "MangaHub.ru"])
        self.site_combo.currentTextChanged.connect(self.on_site_changed)
        layout.addWidget(self.site_combo)

        self.auth_status_label = QLabel("")
        self.auth_status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.auth_status_label)

        self.group_domain_label = QLabel("Сайт для авторизации (зеркала часто меняются — можно ввести свой):")
        self.group_domain_label.hide()
        layout.addWidget(self.group_domain_label)

        self.group_domain_combo = QComboBox()
        self.group_domain_combo.setEditable(True)
        self.group_domain_combo.addItems(GROUP_DOMAINS)
        self.group_domain_combo.hide()
        self.group_domain_combo.editTextChanged.connect(lambda _t: self.check_group_auth_status())
        layout.addWidget(self.group_domain_combo)

        self.auth_button = QPushButton("🔑 Авторизация")
        self.auth_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auth_button.clicked.connect(self.do_auth)
        self.auth_button.hide()
        layout.addWidget(self.auth_button)

        self.import_cookies_button = QPushButton("📁 Импортировать куки из файла (если сайт блокирует автовход)")
        self.import_cookies_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_cookies_button.clicked.connect(self.import_group_cookies)
        self.import_cookies_button.hide()
        layout.addWidget(self.import_cookies_button)

        layout.addWidget(QLabel("Ссылка на мангу:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://mangalib.me/ru/manga/..., https://com-x.life/..., https://readmanga.live/... или https://mangahub.ru/title/...")
        self.url_input.textChanged.connect(self.on_url_changed)
        layout.addWidget(self.url_input)

        self._detected_site_hint = QLabel("")
        self._detected_site_hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._detected_site_hint)

        layout.addWidget(QLabel("Формат сохранения:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Папки с картинками", "CBZ (архив)"])
        self.format_combo.setCurrentIndex(1)
        layout.addWidget(self.format_combo)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Скачать")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.on_site_changed(self.site_combo.currentText())

    def on_site_changed(self, site):
        is_group = "ReadManga" in site
        self.group_domain_label.setVisible(is_group)
        self.group_domain_combo.setVisible(is_group)
        self.import_cookies_button.setVisible(is_group)

        if "Com-X" in site:
            self.check_comx_auth_status()
        elif "MangaLib" in site:
            self.check_mangalib_auth_status()
        elif "MangaHub" in site:
            self.check_mangahub_auth_status()
        elif is_group:
            self.check_group_auth_status()

    def on_url_changed(self, text):
        text = text.strip()
        domain = urlparse(text).netloc if text else ""

        # Автоопределение сайта по вставленной ссылке — чтобы не приходилось
        # вручную синхронизировать выбор сайта с тем, что реально вставлено.
        # Пользователь всегда может переключить комбобокс сам — это только
        # подсказка, а не жёсткая привязка.
        detected = None
        if domain:
            if any(d in domain for d in MANGALIB_DOMAINS):
                detected = "MangaLib"
            elif "com-x.life" in domain:
                detected = "Com-X.life"
            elif "mangahub.ru" in domain:
                detected = "MangaHub.ru"
            elif any(d in domain for d in GROUP_DOMAINS) or domain.startswith(("readmanga", "mintmanga", "seimanga")):
                detected = "ReadManga/MintManga"

        if detected and detected != self.site_combo.currentText():
            self._detected_site_hint.setText(f"↪ Определён сайт: {detected}")
            self.site_combo.blockSignals(True)
            self.site_combo.setCurrentText(detected)
            self.site_combo.blockSignals(False)
            self.on_site_changed(detected)
        else:
            self._detected_site_hint.setText("")

        if "ReadManga" not in self.site_combo.currentText():
            return
        if domain:
            self.group_domain_combo.blockSignals(True)
            self.group_domain_combo.setCurrentText(domain)
            self.group_domain_combo.blockSignals(False)
        self.check_group_auth_status()

    def check_comx_auth_status(self):
        cookies_file = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'comx_cookies.json'
        if cookies_file.exists():
            self.auth_status_label.setText("✅ Авторизован (куки есть)")
            self.auth_status_label.setStyleSheet("color: #28a745; font-size: 11px;")
            self.auth_button.setText("🔄 Обновить авторизацию")
        else:
            self.auth_status_label.setText("❌ Не авторизован (нужно авторизоваться для большинства манг)")
            self.auth_status_label.setStyleSheet("color: #dc3545; font-size: 11px;")
            self.auth_button.setText("🔑 Авторизоваться")
        self.auth_button.show()

    def check_mangalib_auth_status(self):
        token_path = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'mangalib_token.json'

        token = None
        if token_path.exists():
            try:
                with open(token_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    token = data.get("token", "")
            except Exception as e:
                logging.error(f"Не удалось прочитать токен MangaLib: {e}")

        if token:
            self.auth_status_label.setText("✅ Токен есть (можно скачивать 18+)")
            self.auth_status_label.setStyleSheet("color: #28a745; font-size: 11px;")
            self.auth_button.setText("🔄 Обновить токен")
        else:
            self.auth_status_label.setText("❌ Нет токена (для 18+ нужна авторизация)")
            self.auth_status_label.setStyleSheet("color: #ff9800; font-size: 11px;")
            self.auth_button.setText("🔑 Получить токен")
        self.auth_button.show()

    def check_mangahub_auth_status(self):
        cookies_file = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'mangahub_cookies.json'
        if cookies_file.exists():
            self.auth_status_label.setText("✅ Авторизован (куки есть)")
            self.auth_status_label.setStyleSheet("color: #28a745; font-size: 11px;")
            self.auth_button.setText("🔄 Обновить авторизацию")
        else:
            self.auth_status_label.setText("ℹ Без авторизации скачивается большинство манг — вход нужен только для приватного/18+ контента")
            self.auth_status_label.setStyleSheet("color: #888; font-size: 11px;")
            self.auth_button.setText("🔑 Авторизоваться")
        self.auth_button.show()

    def check_group_auth_status(self):
        domain = self.group_domain_combo.currentText().strip()
        if not domain:
            self.auth_status_label.setText("ℹ Выберите или введите домен сайта для авторизации")
            self.auth_status_label.setStyleSheet("color: #888; font-size: 11px;")
            self.auth_button.setText("🔑 Авторизоваться")
            self.auth_button.show()
            return

        safe_domain = re.sub(r'[^a-zA-Z0-9.]', '_', domain)
        cookies_file = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / f'group_cookies_{safe_domain}.json'
        if cookies_file.exists():
            self.auth_status_label.setText(f"✅ Авторизован на {domain}")
            self.auth_status_label.setStyleSheet("color: #28a745; font-size: 11px;")
            self.auth_button.setText("🔄 Обновить авторизацию")
        else:
            self.auth_status_label.setText(f"❌ Не авторизован на {domain} (нужно для 18+ и части глав)")
            self.auth_status_label.setStyleSheet("color: #dc3545; font-size: 11px;")
            self.auth_button.setText("🔑 Авторизоваться")
        self.auth_button.show()

    def do_auth(self):
        site = self.site_combo.currentText()
        if "ReadManga" in site:
            domain = self.group_domain_combo.currentText().strip()
            if not domain:
                QMessageBox.warning(self, "Ошибка", "Выберите или введите домен сайта для авторизации")
                return

            self.auth_button.setEnabled(False)
            loader = GroupDownloadThread(f"https://{domain}/", "")

            def on_finished(cookies_loaded):
                self.auth_button.setEnabled(True)
                self.check_group_auth_status()

            run_auth_with_dialog(self, loader, domain, on_finished=on_finished)

        elif "Com-X" in site:
            self.auth_button.setEnabled(False)
            loader = ComXDownloadThread("https://com-x.life", "")

            def on_finished(cookies_loaded):
                self.auth_button.setEnabled(True)
                self.check_comx_auth_status()

            run_auth_with_dialog(self, loader, "com-x.life", on_finished=on_finished)

        elif "MangaHub" in site:
            self.auth_button.setEnabled(False)
            loader = MangaHubDownloadThread("https://mangahub.ru/", "")

            def on_finished(cookies_loaded):
                self.auth_button.setEnabled(True)
                self.check_mangahub_auth_status()

            run_auth_with_dialog(self, loader, "mangahub.ru", on_finished=on_finished)

        elif "MangaLib" in site:
            QMessageBox.information(self, "Авторизация MangaLib",
                "Откроется браузер.\n\nВойдите в аккаунт на mangalib.me\n\nПосле входа токен будет сохранён автоматически.")

            self.auth_button.setEnabled(False)
            self.auth_button.setText("⏳ Открываю браузер...")

            self._mangalib_auth_result = {"token": None}
            self._mangalib_auth_thread = threading.Thread(
                target=self._mangalib_auth_worker, daemon=True
            )
            self._mangalib_auth_thread.start()

            self._mangalib_auth_timer = QTimer(self)
            self._mangalib_auth_timer.timeout.connect(self._check_mangalib_auth_finished)
            self._mangalib_auth_timer.start(500)

    def import_group_cookies(self):
        """Импорт куки из файла, экспортированного расширением браузера
        (например "Get cookies.txt LOCALLY"). Нужен для сайтов с защитой,
        которую наш встроенный автовход через Selenium не может обойти —
        куки, снятые из уже залогиненного обычного браузера пользователя,
        работают надёжнее."""
        domain = self.group_domain_combo.currentText().strip()
        if not domain:
            QMessageBox.warning(self, "Ошибка", "Сначала укажите домен сайта для авторизации")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл с куки", "",
            "Куки (*.json *.txt);;Все файлы (*.*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать файл:\n{e}")
            return

        cookies = self._parse_cookie_file(raw)
        if not cookies:
            QMessageBox.critical(
                self, "Ошибка",
                "Не удалось распознать куки в этом файле.\n\n"
                "Поддерживаются: JSON-список объектов с полями name/value "
                "(экспорт расширений вроде Cookie-Editor) или формат "
                "Netscape cookies.txt (экспорт \"Get cookies.txt LOCALLY\")."
            )
            return

        safe_domain = re.sub(r'[^a-zA-Z0-9.]', '_', domain)
        cookies_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader'
        cookies_dir.mkdir(parents=True, exist_ok=True)
        target = cookies_dir / f'group_cookies_{safe_domain}.json'
        with open(target, 'w', encoding='utf-8') as f:
            json.dump(cookies, f)

        QMessageBox.information(self, "Успех", f"Импортировано куки для {domain}: {len(cookies)} шт.")
        self.check_group_auth_status()

    @staticmethod
    def _parse_cookie_file(raw):
        """Возвращает список {"name": ..., "value": ...} из содержимого
        файла куки — сперва пробуем JSON, затем формат Netscape cookies.txt."""
        raw = raw.strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
            if isinstance(data, list):
                cookies = [
                    {"name": c["name"], "value": c["value"]}
                    for c in data if isinstance(c, dict) and "name" in c and "value" in c
                ]
                if cookies:
                    return cookies
        except (json.JSONDecodeError, TypeError):
            pass

        cookies = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith('#') and not line.startswith('#HttpOnly_'):
                continue
            if line.startswith('#HttpOnly_'):
                line = line[len('#HttpOnly_'):]
            parts = line.split('\t')
            if len(parts) >= 7:
                cookies.append({"name": parts[5], "value": parts[6]})
        return cookies

    def _mangalib_auth_worker(self):
        """Выполняется в фоновом потоке — сюда НЕЛЬЗЯ добавлять QMessageBox и другие вызовы интерфейса"""
        from browser_driver import launch_authenticated_browser
        import time

        token = None
        driver = None
        try:
            driver, browser_name = launch_authenticated_browser()
            logging.info(f"Авторизация MangaLib через {browser_name}")
            driver.get("https://mangalib.me")

            for i in range(120):
                time.sleep(1)
                try:
                    token = driver.execute_script("""
                        try {
                            var auth = localStorage.getItem('auth');
                            if (auth) {
                                var data = JSON.parse(auth);
                                return data.token.access_token;
                            }
                        } catch(e) {}
                        return null;
                    """)
                    if token:
                        break
                except Exception:
                    pass
        except Exception:
            token = None
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        self._mangalib_auth_result["token"] = token

    def _check_mangalib_auth_finished(self):
        """Выполняется в главном потоке — тут МОЖНО показывать окна и трогать кнопки"""
        if self._mangalib_auth_thread.is_alive():
            return
        self._mangalib_auth_timer.stop()

        token = self._mangalib_auth_result.get("token")
        if token:
            token_path = Path(os.environ.get('LOCALAPPDATA', '')) / 'KirshMangaReader' / 'mangalib_token.json'
            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, 'w', encoding='utf-8') as f:
                json.dump({"token": token}, f)
            QMessageBox.information(self, "Успех", "Токен сохранён!")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось получить токен")

        self.auth_button.setEnabled(True)
        self.check_mangalib_auth_status()

    def get_data(self):
        site = self.site_combo.currentText()
        url = self.url_input.text().strip()
        output_format = self.format_combo.currentText()
        return site, url, output_format
