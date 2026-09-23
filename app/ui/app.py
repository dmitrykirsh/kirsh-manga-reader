"""Запуск QML-приложения."""

import os
import sys
import logging

from PyQt6.QtCore import QObject, QEvent, Qt, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtWidgets import QApplication

from app import theme
from app.constants import DATA_DIR
from app.ui.backend import Backend
from app.ui.providers import IconProvider, CoverProvider, PageProvider

QML_DIR = os.path.join(DATA_DIR, "app", "qml")


class _KeyNavFilter(QObject):
    """Различает клавиатурную и мышиную навигацию (аналог :focus-visible): кольцо фокуса
    рисуется только когда пользователь идёт по интерфейсу с клавиатуры."""

    def __init__(self, backend):
        super().__init__(backend)
        self._backend = backend

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.KeyPress and event.key() in (
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Up, Qt.Key.Key_Down,
                Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._backend.set_keyboard_nav(True)
        elif t in (QEvent.Type.MouseButtonPress, QEvent.Type.TouchBegin):
            self._backend.set_keyboard_nav(False)
        return False


def run():
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QApplication(sys.argv)
    app.setApplicationName("Kirsh Manga Reader")
    icon = os.path.join(DATA_DIR, "icon.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    theme.load_fonts()

    backend = Backend()
    app.installEventFilter(_KeyNavFilter(backend))

    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    engine.addImageProvider("icon", IconProvider())
    engine.addImageProvider("cover", CoverProvider())
    engine.addImageProvider("page", PageProvider(backend.reader))
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("appDisplayFont", theme.DISPLAY_FONT)
    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
    if not engine.rootObjects():
        logging.error("Не удалось загрузить Main.qml")
        return 1
    backend.start()
    code = app.exec()
    backend.save_config()
    return code
