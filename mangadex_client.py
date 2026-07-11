import requests

API_BASE = "https://api.mangadex.org"
UPLOADS_BASE = "https://uploads.mangadex.org"
TIMEOUT = 15


def search_manga(query, limit=5):
    """Ищет мангу по названию (кириллица работает благодаря altTitles). Возвращает список dict'ов (сырые attributes+id)."""
    resp = requests.get(
        f"{API_BASE}/manga",
        params={
            "title": query,
            "limit": limit,
            "includes[]": ["cover_art"],
            "order[relevance]": "desc",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_manga_details(manga_id):
    """Полная карточка манги с автором/художником/обложкой."""
    resp = requests.get(
        f"{API_BASE}/manga/{manga_id}",
        params={"includes[]": ["author", "artist", "cover_art"]},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("data")


def get_chapter_feed(manga_id, lang="ru", limit=500):
    """Список глав (может быть постранично, если глав больше limit)."""
    chapters = []
    offset = 0
    while True:
        resp = requests.get(
            f"{API_BASE}/manga/{manga_id}/feed",
            params={
                "translatedLanguage[]": [lang],
                "order[chapter]": "asc",
                "limit": limit,
                "offset": offset,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("data", [])
        chapters.extend(batch)
        total = data.get("total", len(chapters))
        offset += limit
        if offset >= total or not batch:
            break
    return chapters


def get_russian_title(attributes):
    for entry in attributes.get("altTitles", []):
        if "ru" in entry:
            return entry["ru"]
    return None


def get_cover_url(manga_id, relationships, size=512):
    for rel in relationships or []:
        if rel.get("type") == "cover_art":
            filename = (rel.get("attributes") or {}).get("fileName")
            if filename:
                return f"{UPLOADS_BASE}/covers/{manga_id}/{filename}.{size}.jpg"
    return None


def get_name_from_relationship(relationships, rel_type):
    for rel in relationships or []:
        if rel.get("type") == rel_type:
            return (rel.get("attributes") or {}).get("name")
    return None


def get_mal_id(attributes):
    return (attributes.get("links") or {}).get("mal")
