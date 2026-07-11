import sys
import os
import re
import shutil
import logging

if getattr(sys, 'frozen', False):
    DATA_DIR = sys._MEIPASS
    CONFIG_DIR = os.path.dirname(sys.executable)
else:
    DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_DIR = DATA_DIR

USER_DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local')), 'KirshMangaReader')
os.makedirs(USER_DATA_DIR, exist_ok=True)

LOG_PATH = os.path.join(USER_DATA_DIR, "app.log")
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    encoding="utf-8"
)

CONFIG_PATH = os.path.join(USER_DATA_DIR, "reader_config.json")
TOKEN_PATH = os.path.join(USER_DATA_DIR, "mangalib_token.json")
COVERS_DIR = os.path.join(USER_DATA_DIR, "custom_covers")
os.makedirs(COVERS_DIR, exist_ok=True)

INFO_CACHE_DIR = os.path.join(USER_DATA_DIR, "manga_info_cache")
os.makedirs(INFO_CACHE_DIR, exist_ok=True)

# Перенос конфига со старого расположения (рядом с exe) на новое (LOCALAPPDATA)
OLD_CONFIG_PATH = os.path.join(CONFIG_DIR, "reader_config.json")
if os.path.exists(OLD_CONFIG_PATH) and not os.path.exists(CONFIG_PATH):
    try:
        shutil.move(OLD_CONFIG_PATH, CONFIG_PATH)
    except Exception as e:
        logging.error(f"Не удалось перенести старый конфиг: {e}")

try:
    import rarfile
    unrar_path = os.path.join(DATA_DIR, "UnRAR.exe")
    if os.path.exists(unrar_path):
        rarfile.UNRAR_TOOL = unrar_path
        RAR_SUPPORT = True
    else:
        RAR_SUPPORT = False
except ImportError:
    RAR_SUPPORT = False

VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
ARCHIVE_EXTENSIONS = ('.zip', '.cbz', '.rar', '.cbr')

APP_VERSION = "3.0"
GITHUB_REPO = "dmitrykirsh/kirsh-manga-reader"


def is_newer_version(remote_version, local_version):
    """Сравнивает версии вида '2.0.10' по числовым сегментам (не как строки)."""
    def parts(v):
        return tuple(int(p) for p in re.findall(r'\d+', v))
    return parts(remote_version) > parts(local_version)
