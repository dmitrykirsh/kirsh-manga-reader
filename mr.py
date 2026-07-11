import sys
import os
import logging

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.gui.icc=false;qt.gui.imageio=false"

import ctypes
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('KirshMangaReader.2.0')
except Exception as e:
    logging.warning(f"Не удалось задать AppUserModelID: {e}")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app.constants import DATA_DIR
from app.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    icon_path = os.path.join(DATA_DIR, "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
