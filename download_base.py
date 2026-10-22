import os
import re
import shutil
import logging
import zipfile
from pathlib import Path

import requests
from PyQt6.QtCore import QThread, pyqtSignal


class BaseDownloadThread(QThread):
    """Общий предок для загрузчиков манги с разных сайтов.

    Даёт единый набор сигналов для прогресс-диалога в MainWindow,
    общую упаковку скачанных глав в CBZ и выбор глав (chapter_filter).
    Сама логика получения списка глав и скачивания страниц у каждого
    сайта своя и переопределяется в run() подкласса.
    """

    progress = pyqtSignal(int, int, str)
    status = pyqtSignal(str)
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)
    need_auth = pyqtSignal()
    # Некритичное предупреждение при частичном успехе (часть глав не скачалась,
    # но остальное скачано и finished всё равно будет отправлен) — в отличие
    # от error, не отменяет скачивание и не блокирует finished.
    warning = pyqtSignal(str)

    def __init__(self, url, dest_root, output_format="Папки с картинками", chapter_filter=None):
        super().__init__()
        self.url = url
        self.dest_root = dest_root
        self.output_format = output_format
        # None — все главы; {"start": a, "end": b} — по номерам глав (одна глава: a == b,
        # любая граница может быть None); {"keys": [...]} — главы, отмеченные в списке
        # (ключи из list_chapters() того же загрузчика).
        self.chapter_filter = chapter_filter or None
        self.session = requests.Session()
        self._cancel_requested = False

    def request_cancel(self):
        """Кооперативная отмена — сама загрузка/авторизация должна
        периодически проверять self._cancel_requested и аккуратно
        остановиться (закрыть браузер, выйти из цикла ожидания)."""
        self._cancel_requested = True

    # -- выбор глав

    def list_chapters(self):
        """Список глав для окна выбора: [{"key", "label", "number"}] от первой главы к последней.
        Вызывается в фоновом потоке до запуска скачивания; сигналы тут не эмитим."""
        raise NotImplementedError

    @staticmethod
    def chapter_number(value):
        """Номер главы числом ("7.5", "7,5", 12) или None, если номера нет."""
        try:
            return float(str(value).strip().replace(',', '.'))
        except (TypeError, ValueError):
            return None

    def filter_chapters(self, chapters, number, key=None):
        """Оставляет главы, выбранные в chapter_filter. number(ch) — номер главы,
        key(ch) — ключ из list_chapters(). Без фильтра возвращает все главы."""
        f = self.chapter_filter
        if not f:
            return list(chapters)
        keys = f.get("keys")
        if keys is not None:
            wanted = {str(k) for k in keys}
            return [ch for ch in chapters if key is not None and str(key(ch)) in wanted]
        start, end = f.get("start"), f.get("end")
        result = []
        for ch in chapters:
            n = self.chapter_number(number(ch))
            if n is None:
                continue  # главу без номера в диапазон не отнести
            if start is not None and n < start:
                continue
            if end is not None and n > end:
                continue
            result.append(ch)
        return result

    def describe_filter(self):
        """Человекочитаемое описание выбора для сообщений об ошибках."""
        f = self.chapter_filter or {}
        if f.get("keys") is not None:
            return "отмеченные главы"
        start, end = f.get("start"), f.get("end")
        fmt = lambda n: f"{n:g}"
        if start is not None and start == end:
            return f"глава {fmt(start)}"
        if start is not None and end is not None:
            return f"главы {fmt(start)}–{fmt(end)}"
        if start is not None:
            return f"главы с {fmt(start)}"
        if end is not None:
            return f"главы до {fmt(end)}"
        return "все главы"

    @staticmethod
    def remove_empty_dirs(folder):
        """Убирает пустые папки внутри folder и саму folder, если она опустела.
        В отличие от rmtree не трогает главы, скачанные раньше, — при докачке
        отдельных глав папка манги уже может быть не пустой."""
        folder = Path(folder)
        if not folder.is_dir():
            return
        for sub in sorted(folder.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if sub.is_dir():
                try:
                    sub.rmdir()
                except OSError:
                    pass
        try:
            folder.rmdir()
        except OSError:
            pass

    # -- упаковка

    @staticmethod
    def natural_sort_key(path):
        nums = re.findall(r'\d+', path.stem)
        return int(nums[0]) if nums else 0

    def pack_chapters_to_cbz(self, cbz_path, chapter_folders, arcname_prefix_fn, keep_existing=None):
        """Упаковывает картинки из каждой папки главы (отсортированные по номеру)
        в cbz_path, под именем arcname_prefix_fn(chapter_folder) + порядковый номер.
        Каждая папка главы удаляется после упаковки.

        keep_existing (по умолчанию — когда скачивается часть глав): главы, которые уже
        лежат в существующем cbz_path, сохраняются, заменяются только скачанные сейчас.
        Иначе докачка одной главы перезаписала бы архив тома этой одной главой."""
        if keep_existing is None:
            keep_existing = bool(self.chapter_filter)
        folders = [f for f in chapter_folders if f.exists()]
        new_prefixes = {arcname_prefix_fn(f) for f in folders}

        tmp_path = cbz_path.with_name(cbz_path.name + ".tmp")
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            if keep_existing and cbz_path.exists():
                try:
                    with zipfile.ZipFile(cbz_path) as old:
                        for info in old.infolist():
                            if info.filename.rsplit('/', 1)[0] not in new_prefixes:
                                zf.writestr(info, old.read(info))
                except zipfile.BadZipFile as e:
                    logging.warning(f"{cbz_path}: старый архив повреждён и будет заменён: {e}")

            for ch_folder in folders:
                images = []
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp', '*.gif']:
                    images.extend(ch_folder.glob(ext))
                images.sort(key=self.natural_sort_key)

                prefix = arcname_prefix_fn(ch_folder)
                for i, img in enumerate(images, 1):
                    zf.write(img, f"{prefix}/{i:03d}{img.suffix}")

        os.replace(tmp_path, cbz_path)
        for ch_folder in folders:
            shutil.rmtree(ch_folder, ignore_errors=True)
        return cbz_path
