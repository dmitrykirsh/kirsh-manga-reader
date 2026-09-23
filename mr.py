import sys
import os
import logging

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.gui.icc=false;qt.gui.imageio=false"

import ctypes
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('KirshMangaReader.3.6')
except Exception as e:
    logging.warning(f"Не удалось задать AppUserModelID: {e}")

from app.ui.app import run

if __name__ == "__main__":
    sys.exit(run())
