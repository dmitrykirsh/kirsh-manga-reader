import re
import time
import requests

API_BASE = "https://api.jikan.moe/v4"
TIMEOUT = 15
RETRIES = 3
RETRY_DELAY = 2


def parse_mal_id(url_or_id):
    """Достаёт числовой ID из ссылки вида myanimelist.net/manga/2/Berserk или принимает готовый ID."""
    s = str(url_or_id).strip()
    if s.isdigit():
        return s
    match = re.search(r"myanimelist\.net/manga/(\d+)", s)
    return match.group(1) if match else None


def get_manga_by_id(mal_id):
    """Данные тайтла с MyAnimeList через Jikan. Jikan нестабилен (частые 504) — ретраи с паузой."""
    last_error = None
    for attempt in range(RETRIES):
        try:
            resp = requests.get(f"{API_BASE}/manga/{mal_id}", timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.json().get("data")
            try:
                last_error = resp.json().get("message") or f"HTTP {resp.status_code}"
            except ValueError:
                last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as e:
            last_error = str(e)
        if attempt < RETRIES - 1:
            time.sleep(RETRY_DELAY)
    raise RuntimeError(f"MyAnimeList/Jikan недоступен: {last_error}")
