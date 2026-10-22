"""Контроллер читалки для QML: состояние текущей манги, страницы, главы, режимы."""

import os
import logging

from PyQt6.QtCore import pyqtSignal, pyqtSlot, QBuffer, QByteArray
from PyQt6.QtGui import QImageReader

from app.models import (MangaItem, get_chapter_groups, get_first_page_of_chapter)
from app.ui import volumes
from app.ui.base import Bag, P
from app.ui.tasks import run_async


def _probe_sizes(manga, total):
    out = []
    for idx in range(total):
        w, h = 800, 1200
        known = manga.get_page_size(idx)  # PDF: размер без отрисовки страницы
        if known:
            out.append(list(known))
            continue
        data = manga.get_page_data(idx)
        if data:
            buf = QBuffer()
            buf.setData(QByteArray(data))
            buf.open(QBuffer.OpenModeFlag.ReadOnly)
            size = QImageReader(buf).size()
            buf.close()
            if size.isValid() and size.width() > 0 and size.height() > 0:
                w, h = size.width(), size.height()
        out.append([w, h])
    return out


class ReaderController(Bag):
    activeChanged = pyqtSignal()
    titleChanged = pyqtSignal()
    pageCountChanged = pyqtSignal()
    pageChanged = pyqtSignal()
    webtoonChanged = pyqtSignal()
    genChanged = pyqtSignal()
    chaptersChanged = pyqtSignal()
    chapterNameChanged = pyqtSignal()
    hasNextChanged = pyqtSignal()
    chapterEndChanged = pyqtSignal()
    sizesChanged = pyqtSignal()
    hintVisibleChanged = pyqtSignal()
    volumeNameChanged = pyqtSignal()
    # QML → перейти на страницу (программная смена, например прыжок по главе)
    pageJump = pyqtSignal(int)
    requestInfo = pyqtSignal()
    requestClose = pyqtSignal()

    active = P(bool, "active", activeChanged, False)
    title = P(str, "title", titleChanged, "")
    pageCount = P(int, "pageCount", pageCountChanged, 0)
    page = P(int, "page", pageChanged, 0)
    webtoon = P(bool, "webtoon", webtoonChanged, False)
    gen = P(int, "gen", genChanged, 0)
    chapters = P("QVariantList", "chapters", chaptersChanged, [])
    chapterName = P(str, "chapterName", chapterNameChanged, "")
    hasNext = P(bool, "hasNext", hasNextChanged, False)
    chapterEnd = P(bool, "chapterEnd", chapterEndChanged, False)
    sizes = P("QVariantList", "sizes", sizesChanged, [])
    hintVisible = P(bool, "hintVisible", hintVisibleChanged, False)
    volumeName = P(str, "volumeName", volumeNameChanged, "")

    def __init__(self, backend):
        super().__init__(backend)
        self._backend = backend
        self._manga = None
        self._gen = 0
        self._starts = []      # (page, name) начала глав внутри файла
        self._series_paths = []  # пути глав всей серии по порядку — для nextChapter() через границу тома
        self._sibling = None
        self._v.update(active=False, title="", pageCount=0, page=0, webtoon=False, gen=0,
                       chapters=[], chapterName="", hasNext=False, chapterEnd=False, sizes=[],
                       hintVisible=False, volumeName="")

    # -- для PageProvider (вызывается из потока загрузки картинок)
    def manga_for_gen(self, gen):
        return self._manga if gen == self._gen and self._manga is not None else None

    @property
    def manga(self):
        return self._manga

    # -- открытие
    def open_manga(self, manga, start_page=0, force_webtoon=None, series_volumes=None):
        if self._manga is not None and self._manga is not manga:
            self._manga.close_archive()
        self._manga = manga
        manga.open_archive()
        self._gen += 1
        total = len(manga.pages)
        start_page = max(0, min(int(start_page or 0), total - 1))

        groups = get_chapter_groups(manga) or []
        chapters = []
        for name in groups:
            idx = get_first_page_of_chapter(manga, name)
            if idx >= 0:
                chapters.append({"name": name, "page": idx})
        chapters.sort(key=lambda c: c["page"])
        # убрать дубли с одинаковой стартовой страницей
        seen, uniq = set(), []
        for c in chapters:
            if c["page"] not in seen:
                seen.add(c["page"])
                uniq.append(c)
        self._starts = [(c["page"], c["name"]) for c in uniq] if len(uniq) >= 2 else []

        # Оглавление всей серии (тома/главы — отдельные файлы), а не только
        # разбивки внутри текущего открытого файла — иначе для серий с главами
        # по отдельным файлам (а не одним томом с внутренними главами) кнопка
        # «Оглавление» просто не появлялась, хотя переходить было куда.
        self._series_paths = self._build_series_chapters(manga.path, series_volumes or [])

        want_webtoon = force_webtoon if force_webtoon is not None else self._backend.get_webtoon_pref(manga.path)
        self._sibling = self._next_series_path() or volumes.next_sibling(manga.path, self._backend.config.get("root_dir"))

        self.set("gen", self._gen)
        # В серии заголовок — название серии, том идёт подзаголовком.
        parent = os.path.basename(os.path.dirname(manga.path))
        root = os.path.basename(os.path.normpath(self._backend.config.get("root_dir") or ""))
        title, vol = manga.display_name, ""
        if manga.is_archive and parent and parent != root:
            if volumes.VOL_FOLDER_RE.match(parent):
                grand = os.path.basename(os.path.dirname(os.path.dirname(manga.path)))
                title, vol = (grand or parent), volumes.format_volume_label(parent)
            else:
                title, vol = parent, volumes.format_volume_label(manga.display_name)
        self.set("title", title)
        self.set("volumeName", vol)
        self.set("pageCount", total)
        # Список серии приоритетнее внутренней разбивки файла: если манга — часть
        # серии из нескольких файлов, показываем оглавление по ней целиком.
        if len(self._series_paths) >= 2:
            self.set("chapters", self._series_paths)
        else:
            self.set("chapters", uniq if len(uniq) >= 2 else [])
        self.set("sizes", [])
        self.set("webtoon", bool(want_webtoon))
        self.set("hintVisible", bool(self._backend.config.get("show_navigation_hint", True)))
        self.set("active", True)
        self.set("page", start_page)
        self._refresh_position()
        if want_webtoon:
            self._probe()

    def _build_series_chapters(self, current_path, local_volumes):
        """Плоский список глав всей серии (каждая — свой файл): {name, path, page:0,
        detail, current}. Внутренние под-главы одного файла сюда не разворачиваются —
        для них остаётся отдельное оглавление внутри самого файла (см. _starts)."""
        if not local_volumes:
            return []
        progress = self._backend.config.get("progress", {})
        cur_norm = os.path.normpath(current_path)
        multi_vol = len(local_volumes) > 1
        out = []
        for entry in local_volumes:
            vol_label = volumes.format_volume_label(entry.get("name") or "")
            if entry.get("chapters") and not entry.get("internal"):
                for name, path in entry["chapters"]:
                    if not path:
                        continue
                    label = f"{vol_label} · {volumes.format_volume_label(name)}" if multi_vol else volumes.format_volume_label(name)
                    out.append(self._series_row(label, path, cur_norm, progress))
            elif entry.get("path"):
                out.append(self._series_row(vol_label, entry["path"], cur_norm, progress))
        return out

    @staticmethod
    def _series_row(label, path, cur_norm, progress):
        prog = progress.get(path)
        detail = ""
        if isinstance(prog, dict) and prog.get("total"):
            page, total = prog.get("page", 0), prog["total"]
            if page >= total - 1:
                detail = "Прочитано"
            elif page > 0:
                detail = f"стр. {page + 1}"
        return {"name": label, "path": path, "page": 0, "detail": detail,
                "current": os.path.normpath(path) == cur_norm}

    def _next_series_path(self):
        if len(self._series_paths) < 2 or self._manga is None:
            return None
        cur = os.path.normpath(self._manga.path)
        norm_paths = [os.path.normpath(c["path"]) for c in self._series_paths]
        try:
            idx = norm_paths.index(cur)
        except ValueError:
            return None
        return self._series_paths[idx + 1]["path"] if idx < len(self._series_paths) - 1 else None

    def close_reader(self):
        if self._manga is not None:
            self._manga.close_archive()
        self.set("active", False)

    # -- позиция
    def _refresh_position(self):
        page = self.get("page", 0)
        name = ""
        end = False
        for start, n in self._starts:
            if start <= page:
                name = n
        nxt = next((s for s, _ in self._starts if s > page), None)
        if nxt is not None:
            end = page == nxt - 1
        else:
            end = page >= self.get("pageCount", 0) - 1
        has_next = (nxt is not None) or (self._sibling is not None)
        self.set("chapterName", name)
        self.set("chapterEnd", end)
        self.set("hasNext", has_next)

    def _probe(self):
        manga, gen = self._manga, self._gen
        if manga is None:
            return

        def done(result, error):
            if error is None and gen == self._gen:
                self.set("sizes", result)

        run_async(lambda: _probe_sizes(manga, len(manga.pages)), done)

    # -- слоты для QML
    @pyqtSlot(int)
    def setPage(self, page):
        total = self.get("pageCount", 0)
        page = max(0, min(int(page), total - 1))
        if page == self.get("page"):
            return
        self.set("page", page)
        self._refresh_position()
        if self._manga is not None:
            self._backend.report_progress(self._manga.path, page, total)

    @pyqtSlot(int)
    def jumpTo(self, page):
        """Прыжок (оглавление, слайдер): меняет страницу и сообщает QML прокрутить ленту."""
        self.setPage(page)
        self.pageJump.emit(int(page))

    @pyqtSlot()
    def nextPage(self):
        self.jumpTo(self.get("page", 0) + 1)

    @pyqtSlot()
    def prevPage(self):
        self.jumpTo(self.get("page", 0) - 1)

    @pyqtSlot()
    def toggleWebtoon(self):
        self.setWebtoonMode(not self.get("webtoon", False))

    @pyqtSlot(bool)
    def setWebtoonMode(self, enabled):
        if enabled == self.get("webtoon"):
            return
        self.set("webtoon", enabled)
        if self._manga is not None:
            self._backend.set_webtoon_pref(self._manga.path, enabled)
        if enabled and not self.get("sizes"):
            self._probe()

    @pyqtSlot(str)
    def openChapter(self, path):
        """Переход на главу серии из оглавления читалки — это другой файл, не просто
        прыжок по странице текущего (см. jumpTo)."""
        manga = MangaItem(path)
        if manga.pages:
            self._backend.open_manga(manga, force_webtoon=self.get("webtoon", False))
        else:
            self._backend.toast("error", "Не удалось открыть главу. Проверьте, что файл не повреждён.")

    @pyqtSlot()
    def nextChapter(self):
        page = self.get("page", 0)
        nxt = next((s for s, _ in self._starts if s > page), None)
        if nxt is not None:
            self.jumpTo(nxt)
            return
        if self._sibling:
            manga = MangaItem(self._sibling)
            if manga.pages:
                self._backend.open_manga(manga, force_webtoon=self.get("webtoon", False))
            else:
                self._backend.toast("error", "Не удалось открыть следующую главу. Проверьте, что файл не повреждён.")

    @pyqtSlot()
    def dismissHint(self):
        self.set("hintVisible", False)
        self._backend.config["show_navigation_hint"] = False
        self._backend.save_config()

    @pyqtSlot()
    def toggleHint(self):
        self.set("hintVisible", not self.get("hintVisible", False))

    @pyqtSlot()
    def hideHintOnce(self):
        self.set("hintVisible", False)

    @pyqtSlot()
    def goInfo(self):
        self.requestInfo.emit()

    @pyqtSlot()
    def goBack(self):
        self.requestClose.emit()
