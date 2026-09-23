import os
import json
import hashlib
import logging

import mangadex_client as mangadex
import jikan_client as jikan
from app.constants import INFO_CACHE_DIR


def _cache_path(item_path):
    h = hashlib.md5(os.path.abspath(item_path).encode('utf-8')).hexdigest()
    return os.path.join(INFO_CACHE_DIR, f"{h}.json")


def load_cached_info(item_path):
    path = _cache_path(item_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Не удалось прочитать кэш информации о манге {path}: {e}")
        return None


def save_cached_info(item_path, info):
    path = _cache_path(item_path)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Не удалось сохранить кэш информации о манге {path}: {e}")


def clear_cached_info(item_path):
    path = _cache_path(item_path)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logging.error(f"Не удалось удалить кэш информации о манге {path}: {e}")


def rename_cached_info(old_item_path, new_item_path):
    """Переносит кэш инфы (ключ — md5 пути) на новый путь после переименования
    на диске — иначе кэш остаётся привязан к старому пути и следующий вход в
    мангу выглядит как промах кэша, вызывая повторный автозапрос к MangaDex."""
    old_path = _cache_path(old_item_path)
    new_path = _cache_path(new_item_path)
    if old_path == new_path or not os.path.exists(old_path):
        return
    try:
        os.replace(old_path, new_path)
    except Exception as e:
        logging.error(f"Не удалось перенести кэш информации о манге {old_path} -> {new_path}: {e}")


def _pick_description(desc_dict):
    if not desc_dict:
        return ""
    return desc_dict.get("ru") or desc_dict.get("en") or next(iter(desc_dict.values()), "")


def _pick_genres(tags):
    genres = []
    for t in (tags or []):
        attrs = t.get("attributes", {})
        if attrs.get("group") != "genre":
            continue
        names = attrs.get("name", {})
        name = names.get("en") or next(iter(names.values()), None)
        if name:
            genres.append(name)
    return genres


def _dedup_chapters(raw_chapters):
    seen = set()
    chapters = []
    for ch in raw_chapters:
        attrs = ch.get("attributes", {})
        num = attrs.get("chapter")
        if num in seen:
            continue
        seen.add(num)
        chapters.append({"chapter": num, "title": attrs.get("title") or None})
    return chapters


def from_mangadex(manga_id):
    details = mangadex.get_manga_details(manga_id)
    attrs = details["attributes"]
    raw_chapters = mangadex.get_chapter_feed(manga_id)
    return {
        "source": "mangadex",
        "source_id": manga_id,
        "title": next(iter(attrs["title"].values()), ""),
        "title_ru": mangadex.get_russian_title(attrs),
        "author": mangadex.get_name_from_relationship(details["relationships"], "author"),
        "artist": mangadex.get_name_from_relationship(details["relationships"], "artist"),
        "genres": _pick_genres(attrs.get("tags")),
        "status": attrs.get("status"),
        "year": attrs.get("year"),
        "description": _pick_description(attrs.get("description")),
        "cover_url": mangadex.get_cover_url(manga_id, details["relationships"]),
        "rating": None,
        "content_rating": attrs.get("contentRating"),
        "last_chapter": attrs.get("lastChapter") or None,
        "chapters": _dedup_chapters(raw_chapters),
        "mal_url": (f"https://myanimelist.net/manga/{mangadex.get_mal_id(attrs)}" if mangadex.get_mal_id(attrs) else None),
    }


def search_mangadex(query, limit=5):
    """Возвращает сырые результаты поиска (для будущего disambiguation UI); текущий UI берёт первый."""
    return mangadex.search_manga(query, limit=limit)


def _titles_of(result):
    attrs = result["attributes"]
    titles = list(attrs.get("title", {}).values())
    for alt in attrs.get("altTitles", []):
        titles.extend(alt.values())
    return titles


def _matches(result, needle):
    needle = needle.lower()
    for t in _titles_of(result):
        t = t.lower()
        if needle in t or t in needle:
            return True
    return False


def _suffix_query(folder_name):
    """Если папка названа по конвенции 'Автор - Название' (например
    'Miura Kentarou - Berserk'), возвращает часть после последнего ' - '.
    Короткие суффиксы (<=3 символов, например 'Tokyo Ghoul - re' -> 're') не
    возвращаются, чтобы не подменять тире, которое является частью самого названия."""
    if " - " not in folder_name:
        return None
    suffix = folder_name.rsplit(" - ", 1)[-1].strip()
    return suffix if len(suffix) > 3 else None


def search_mangadex_best(folder_name, limit=1):
    """Ищет по полному имени папки; если это не даёт явно совпадающего результата и
    папка похожа на конвенцию 'Автор - Название', пробует резервный запрос по части
    после тире и предпочитает его результат."""
    full_results = mangadex.search_manga(folder_name, limit=limit)

    suffix = _suffix_query(folder_name)
    if suffix:
        full_matches = bool(full_results) and _matches(full_results[0], folder_name)
        if not full_matches:
            suffix_results = mangadex.search_manga(suffix, limit=limit)
            if suffix_results and _matches(suffix_results[0], suffix):
                return suffix_results

    return full_results


def _find_by_mal_id(mal_id, search_title):
    """Ищет на MangaDex запись с тем же MAL ID среди результатов поиска по названию
    (включая резервный запрос по части после тире, см. _suffix_query) — так ручная
    ссылка на MyAnimeList работает даже если сам Jikan сейчас недоступен, потому что
    все данные в этом случае берутся с MangaDex, а MAL используется только как
    надёжный идентификатор для выбора ПРАВИЛЬНОГО результата поиска."""
    if not search_title:
        return None
    queries = [search_title]
    suffix = _suffix_query(search_title)
    if suffix:
        queries.append(suffix)

    for query in queries:
        try:
            results = mangadex.search_manga(query, limit=20)
        except Exception as e:
            logging.error(f"Не удалось выполнить поиск на MangaDex для сверки MAL ID: {e}")
            continue
        for r in results:
            if str(mangadex.get_mal_id(r["attributes"]) or "") == str(mal_id):
                return from_mangadex(r["id"])
    return None


def from_mal_smart(url_or_id, search_title=None):
    """Сначала пытается найти тот же тайтл на MangaDex по MAL ID (не зависит от Jikan).
    Если среди результатов поиска по названию папки такого не нашлось — обращается
    к Jikan напрямую (нужен доступный MyAnimeList)."""
    mal_id = jikan.parse_mal_id(url_or_id)
    if not mal_id:
        raise ValueError("Не удалось распознать ID MyAnimeList в ссылке")
    via_mangadex = _find_by_mal_id(mal_id, search_title)
    if via_mangadex:
        return via_mangadex
    return from_mal(url_or_id)


def from_mal(url_or_id):
    mal_id = jikan.parse_mal_id(url_or_id)
    if not mal_id:
        raise ValueError("Не удалось распознать ID MyAnimeList в ссылке")
    data = jikan.get_manga_by_id(mal_id)
    authors = [a["name"] for a in data.get("authors", []) if a.get("name")]
    return {
        "source": "mal",
        "source_id": mal_id,
        "title": data.get("title") or "",
        "title_ru": None,
        "author": ", ".join(authors) if authors else None,
        "artist": None,
        "genres": [g["name"] for g in data.get("genres", [])],
        "status": data.get("status"),
        "year": (data.get("published") or {}).get("prop", {}).get("from", {}).get("year"),
        "description": data.get("synopsis") or "",
        "cover_url": (data.get("images", {}).get("jpg", {}) or {}).get("large_image_url"),
        "rating": data.get("score"),
        "last_chapter": None,
        "content_rating": None,
        "chapters": [],
        "mal_url": data.get("url"),
    }
