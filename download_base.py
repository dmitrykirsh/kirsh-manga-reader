import re
import shutil
import zipfile

import requests
from PyQt6.QtCore import QThread, pyqtSignal


class BaseDownloadThread(QThread):
    """Общий предок для загрузчиков манги с разных сайтов.

    Даёт единый набор сигналов для прогресс-диалога в MainWindow и
    общую упаковку скачанных глав в CBZ. Сама логика получения списка
    глав и скачивания страниц у каждого сайта своя и переопределяется
    в run() подкласса.
    """

    progress = pyqtSignal(int, int, str)
    status = pyqtSignal(str)
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)
    need_auth = pyqtSignal()

    def __init__(self, url, dest_root, output_format="Папки с картинками"):
        super().__init__()
        self.url = url
        self.dest_root = dest_root
        self.output_format = output_format
        self.session = requests.Session()
        self._cancel_requested = False

    def request_cancel(self):
        """Кооперативная отмена — сама загрузка/авторизация должна
        периодически проверять self._cancel_requested и аккуратно
        остановиться (закрыть браузер, выйти из цикла ожидания)."""
        self._cancel_requested = True

    @staticmethod
    def natural_sort_key(path):
        nums = re.findall(r'\d+', path.stem)
        return int(nums[0]) if nums else 0

    def pack_chapters_to_cbz(self, cbz_path, chapter_folders, arcname_prefix_fn):
        """Упаковывает картинки из каждой папки главы (отсортированные по номеру)
        в cbz_path, под именем arcname_prefix_fn(chapter_folder) + порядковый номер.
        Каждая папка главы удаляется после упаковки. Существующий cbz_path
        перезаписывается."""
        if cbz_path.exists():
            cbz_path.unlink()

        with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for ch_folder in chapter_folders:
                if not ch_folder.exists():
                    continue

                images = []
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                    images.extend(ch_folder.glob(ext))
                images.sort(key=self.natural_sort_key)

                prefix = arcname_prefix_fn(ch_folder)
                for i, img in enumerate(images, 1):
                    zf.write(img, f"{prefix}/{i:03d}{img.suffix}")

                shutil.rmtree(ch_folder)

        return cbz_path
