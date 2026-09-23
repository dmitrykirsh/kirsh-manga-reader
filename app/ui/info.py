"""Контроллер страницы манги: данные MangaDex/MAL, тома и главы, статус и оценка."""

import os
import re
import html
import logging

from PyQt6.QtCore import pyqtSignal, pyqtSlot

from app import info_data
from app.models import MangaItem, get_first_page_of_chapter, get_chapter_groups
from app.ui import volumes
from app.ui.base import Bag, P
from app.ui.providers import cover_url
from app.ui.tasks import run_async

STATUS_RU = {"ongoing": "Продолжается", "completed": "Завершено", "hiatus": "Приостановлено", "cancelled": "Отменено"}
CONTENT_RATING_RU = {"safe": None, "suggestive": None, "erotica": "18+", "pornographic": "18+"}
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def description_to_html(text):
    if not text:
        return ""
    parts, last = [], 0
    for m in _MD_LINK_RE.finditer(text):
        parts.append(html.escape(text[last:m.start()]))
        parts.append(f'<a href="{html.escape(m.group(2))}">{html.escape(m.group(1))}</a>')
        last = m.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts).replace("\n", "<br>")


def _fmt_progress(prog):
    """(доля 0..1, подпись) по записи прогресса {"page","total"}."""
    if not isinstance(prog, dict) or not prog.get("total"):
        return 0.0, "Не начат"
    page, total = prog.get("page", 0), prog["total"]
    if page >= total - 1:
        return 1.0, "Прочитан"
    if page <= 0:
        return 0.0, "Не начат"
    return (page + 1) / total, f"Страница {page + 1} из {total}"


class InfoController(Bag):
    loadingChanged = pyqtSignal()
    bannerChanged = pyqtSignal()
    titleChanged = pyqtSignal()
    originalChanged = pyqtSignal()
    coverChanged = pyqtSignal()
    genresChanged = pyqtSignal()
    metaChanged = pyqtSignal()
    descriptionChanged = pyqtSignal()
    chaptersChanged = pyqtSignal()
    chaptersSourceChanged = pyqtSignal()
    statusChanged = pyqtSignal()
    ratingChanged = pyqtSignal()
    volumesChanged = pyqtSignal()
    localChaptersChanged = pyqtSignal()
    readLabelChanged = pyqtSignal()
    readSubChanged = pyqtSignal()
    hasProgressChanged = pyqtSignal()
    isSeriesChanged = pyqtSignal()
    sourceChanged = pyqtSignal()
    keyPathChanged = pyqtSignal()

    loading = P(bool, "loading", loadingChanged, False)
    banner = P(str, "banner", bannerChanged, "")
    title = P(str, "title", titleChanged, "")
    original = P(str, "original", originalChanged, "")
    cover = P(str, "cover", coverChanged, "")
    genres = P("QVariantList", "genres", genresChanged, [])
    meta = P("QVariantList", "meta", metaChanged, [])
    description = P(str, "description", descriptionChanged, "")
    chapters = P("QVariantList", "chapters", chaptersChanged, [])
    chaptersSource = P(str, "chaptersSource", chaptersSourceChanged, "")
    status = P(str, "status", statusChanged, "none")
    rating = P(int, "rating", ratingChanged, 0)
    volumes = P("QVariantList", "volumes", volumesChanged, [])
    localChapters = P("QVariantList", "localChapters", localChaptersChanged, [])
    readLabel = P(str, "readLabel", readLabelChanged, "Читать")
    readSub = P(str, "readSub", readSubChanged, "")
    hasProgress = P(bool, "hasProgress", hasProgressChanged, False)
    isSeries = P(bool, "isSeries", isSeriesChanged, False)
    source = P(str, "source", sourceChanged, "")
    keyPath = P(str, "keyPath", keyPathChanged, "")

    def __init__(self, backend):
        super().__init__(backend)
        self._backend = backend
        self._manga = None
        self._search_title = ""
        self._cache_key = None
        self._local_volumes = []
        self._fetch_token = 0
        self._fetch_source = "mangadex"
        self._v.update(loading=False, banner="", title="", original="", cover="", genres=[], meta=[],
                       description="", chapters=[], chaptersSource="", status="none", rating=0,
                       volumes=[], localChapters=[], readLabel="Читать", readSub="", hasProgress=False,
                       isSeries=False, source="", keyPath="")

    @property
    def cache_key(self):
        return self._cache_key

    @property
    def current_manga(self):
        return self._manga

    # -- вход
    def show_for(self, manga, search_title, cache_key, local_volumes):
        self._manga = manga
        self._search_title = search_title or manga.display_name
        self._cache_key = cache_key or manga.path
        self._local_volumes = local_volumes or []
        self.set("keyPath", self._cache_key)
        self.set("isSeries", bool(local_volumes))
        self._refresh_local()
        self._render_loading()
        cached = info_data.load_cached_info(self._cache_key)
        if cached:
            self._render(cached)
        elif self._backend.config.get("mangadex_enabled", True):
            self._fetch_mangadex()
        else:
            self._on_mangadex_disabled()

    def refresh_progress(self):
        """Обновить прогресс томов/кнопку «Читать» (после чтения, сброса, отметки)."""
        if self._manga is not None:
            self._refresh_local()

    # -- локальные тома, прогресс, кнопка «Читать»
    def _refresh_local(self):
        cfg = self._backend.config
        progress = cfg.get("progress", {})
        meta = cfg.get("metadata", {}).get(self._cache_key, {})
        self.set("status", meta.get("status", "none"))
        self.set("rating", int(meta.get("rating") or 0))

        current = self._manga.path if self._manga else None
        vols = []
        last = volumes.find_last_progress(progress, self._local_volumes)
        for entry in self._local_volumes:
            label = volumes.format_volume_label(entry["name"])
            chapters = entry.get("chapters")
            if chapters and not entry.get("internal"):
                ch_items, fracs = [], []
                for name, path in chapters:
                    frac, detail = _fmt_progress(progress.get(path))
                    fracs.append(frac)
                    ch_items.append({"name": name, "path": path, "detail": detail, "progress": frac,
                                     "current": path == current})
                vols.append({"name": label, "path": "", "kind": "files", "current": any(c["current"] for c in ch_items),
                             "progress": (sum(fracs) / len(fracs)) if fracs else 0.0,
                             "detail": f"{sum(1 for f in fracs if f >= 1.0)} из {len(fracs)} глав прочитано",
                             "chapters": ch_items})
            else:
                frac, detail = _fmt_progress(progress.get(entry["path"]))
                item = {"name": label, "path": entry["path"] or "", "kind": "internal" if entry.get("internal") else "leaf",
                        "current": entry["path"] == current, "progress": frac, "detail": detail, "chapters": []}
                if entry.get("internal"):
                    item["chapters"] = [{"name": n, "path": entry["path"], "detail": "", "progress": 0.0,
                                         "current": False} for n, _ in chapters]
                vols.append(item)
        self.set("volumes", vols)

        # Внутренние главы единственного файла (том вне серии)
        local_chapters = []
        if not self._local_volumes and self._manga is not None:
            try:
                groups = get_chapter_groups(self._manga)
                if groups:
                    local_chapters = [{"name": g} for g in groups]
            except Exception as e:
                logging.error(f"Не удалось получить главы файла: {e}")
        self.set("localChapters", local_chapters)

        # Кнопка «Читать / Продолжить»
        if last:
            path, prog = last
            name = os.path.splitext(os.path.basename(path))[0]
            parent = os.path.basename(os.path.dirname(path))
            where = volumes.format_volume_label(parent) + " · " if volumes.VOL_FOLDER_RE.match(parent) else ""
            self.set("hasProgress", True)
            self.set("readLabel", "Продолжить")
            self.set("readSub", f"{where}{volumes.format_volume_label(name)} · стр. {prog.get('page', 0) + 1}")
        else:
            cur = progress.get(current, {}) if current else {}
            has = isinstance(cur, dict) and cur.get("page", 0) > 0
            self.set("hasProgress", has)
            self.set("readLabel", "Продолжить" if has else "Читать")
            first = volumes.format_volume_label(self._manga.display_name) if self._manga else ""
            self.set("readSub", f"Начать: {first}" if first and not has else "")

    def _render_loading(self):
        self.set("loading", True)
        self.set("banner", "")
        self.set("title", self._manga.display_name if self._manga else "")
        self.set("original", "")
        self.set("genres", [])
        self.set("meta", [])
        self.set("description", "")
        self.set("chapters", [])
        self.set("chaptersSource", "")
        self.set("source", "")
        local = ""
        if self._manga:
            local = cover_url(self._manga.path, not self._manga.is_archive, self._backend.cover_version(self._manga.path))
        self.set("cover", local)

    def _render(self, info):
        title = info.get("title_ru") or info.get("title") or (self._manga.display_name if self._manga else "")
        original = info.get("title") or ""
        self.set("loading", False)
        self.set("banner", "")
        self.set("title", title)
        self.set("original", original if original and original != title else "")
        self.set("genres", info.get("genres") or [])

        rows = []
        if info.get("author"):
            rows.append({"label": "Автор", "value": info["author"]})
        if info.get("artist") and info.get("artist") != info.get("author"):
            rows.append({"label": "Художник", "value": info["artist"]})
        if info.get("status"):
            rows.append({"label": "Статус", "value": STATUS_RU.get(info["status"], info["status"])})
        if info.get("year"):
            rows.append({"label": "Год", "value": str(info["year"])})
        if info.get("rating"):
            rows.append({"label": "Оценка MAL", "value": str(info["rating"])})
        badge = CONTENT_RATING_RU.get(info.get("content_rating"))
        if badge:
            rows.append({"label": "Возраст", "value": badge})
        if info.get("last_chapter"):
            rows.append({"label": "Последняя глава", "value": str(info["last_chapter"])})
        self.set("meta", rows)
        self.set("description", description_to_html(info.get("description")))

        chapters = []
        for ch in info.get("chapters", [])[:500]:
            label = f"Глава {ch['chapter']}" if ch.get("chapter") else "Глава без номера"
            if ch.get("title"):
                label += f" — {ch['title']}"
            chapters.append({"label": label})
        self.set("chapters", chapters)
        src = "MangaDex" if info.get("source") == "mangadex" else "MyAnimeList"
        self.set("chaptersSource", src if chapters else "")
        self.set("source", src)
        if info.get("cover_url"):
            self.set("cover", info["cover_url"])

    # -- сеть
    def _run_fetch(self, fn, source):
        self._fetch_source = source
        self._fetch_token += 1
        token, key = self._fetch_token, self._cache_key

        def done(result, error):
            if token != self._fetch_token:
                return  # пользователь уже открыл другую мангу/том
            if error is not None or result is None:
                self._on_error(str(error) if error else "ничего не найдено")
                return
            if key:
                info_data.save_cached_info(key, result)
            self._render(result)

        run_async(fn, done)

    def _fetch_mangadex(self):
        query = self._search_title

        def fetch():
            results = info_data.search_mangadex_best(query, limit=1)
            return info_data.from_mangadex(results[0]["id"]) if results else None

        self._run_fetch(fetch, "mangadex")

    def _on_mangadex_disabled(self):
        self.set("loading", False)
        self.set("banner", "Интеграция с MangaDex отключена в настройках. Нажмите «Указать ссылку» "
                           "и вставьте адрес страницы на MyAnimeList, чтобы загрузить данные вручную.")

    def _on_error(self, message):
        self.set("loading", False)
        if self._fetch_source == "mal":
            self.set("banner", f"Не удалось загрузить данные с MyAnimeList ({message}). "
                               "MyAnimeList или Jikan сейчас недоступны. Повторите попытку позже.")
        else:
            self.set("banner", f"Не удалось найти мангу на MangaDex ({message}). "
                               "Нажмите «Указать ссылку» и вставьте адрес страницы на MyAnimeList.")

    # -- слоты
    @pyqtSlot()
    def refresh(self):
        if self._manga is None:
            return
        info_data.clear_cached_info(self._cache_key)
        self._render_loading()
        if self._backend.config.get("mangadex_enabled", True):
            self._fetch_mangadex()
        else:
            self._on_mangadex_disabled()

    @pyqtSlot(str)
    def changeLink(self, url):
        url = (url or "").strip()
        if not url or self._manga is None:
            return
        self._render_loading()
        title = self._search_title
        self._run_fetch(lambda: info_data.from_mal_smart(url, title), "mal")

    @pyqtSlot(str)
    def setStatus(self, key):
        self._backend.set_item_status(self._cache_key, key)
        self.set("status", key)
        self._backend.refresh_library_soft()

    @pyqtSlot(int)
    def setRating(self, value):
        self._backend.set_item_rating(self._cache_key, value if value else None)
        self.set("rating", value)
        self._backend.refresh_library_soft()

    @pyqtSlot()
    def read(self):
        progress = self._backend.config.get("progress", {})
        last = volumes.find_last_progress(progress, self._local_volumes)
        target = last[0] if last else (self._manga.path if self._manga else None)
        if target:
            manga = MangaItem(target)
            if manga.pages:
                self._backend.open_manga(manga)

    @pyqtSlot(str)
    def openVolume(self, path):
        manga = MangaItem(path)
        if manga.pages:
            self._backend.open_manga_info(manga)
        else:
            self._backend.toast("error", "Не удалось открыть том. Проверьте, что файл не повреждён.")

    @pyqtSlot(str)
    def openFile(self, path):
        manga = MangaItem(path)
        if manga.pages:
            self._backend.open_manga(manga)
        else:
            self._backend.toast("error", "Не удалось открыть главу. Проверьте, что файл не повреждён.")

    @pyqtSlot(str, str)
    def openChapter(self, path, chapter_name):
        manga = MangaItem(path or (self._manga.path if self._manga else ""))
        if not manga.pages:
            self._backend.toast("error", "Не удалось открыть том. Проверьте, что файл не повреждён.")
            return
        idx = get_first_page_of_chapter(manga, chapter_name)
        if idx >= 0:
            self._backend.open_manga(manga, start_page=idx)
        else:
            self._backend.toast("error", f"Не удалось найти главу «{chapter_name}» в файле.")
