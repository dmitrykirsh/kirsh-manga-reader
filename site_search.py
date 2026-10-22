"""Поиск манги на поддерживаемых сайтах для окна «Скачать мангу».

Каждая функция search_* принимает строку запроса и возвращает список словарей
{title, subtitle, cover, url} — url подходит для соответствующего загрузчика.
Бросает исключение при сетевой ошибке; пустой список — «ничего не найдено».
"""
import time
import logging
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from group_downloader import is_group_domain

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
LIMIT = 24
TIMEOUT = 15


def _clean(text):
    return " ".join((text or "").split())


def search_mangalib(query):
    headers = {
        "Origin": "https://mangalib.me",
        "Referer": "https://mangalib.me/",
        "Site-Id": "1",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    resp = requests.get("https://api.cdnlibs.org/api/manga", params={"q": query, "site_id[]": "1"},
                        headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    results = []
    for m in resp.json().get("data", [])[:LIMIT]:
        slug = m.get("slug_url") or m.get("slug")
        if not slug:
            continue
        title = m.get("rus_name") or m.get("name") or slug
        kind = (m.get("type") or {}).get("label") or ""
        original = m.get("name") if m.get("rus_name") and m.get("name") != m.get("rus_name") else ""
        cover = m.get("cover") or {}
        results.append({
            "title": _clean(title),
            "subtitle": _clean(" · ".join(x for x in (kind, original) if x)),
            "cover": cover.get("thumbnail") or cover.get("default") or "",
            "url": f"https://mangalib.me/ru/manga/{slug}",
        })
    return results


# readmanga.live перенаправляет на текущее зеркало; остальные — запасные варианты.
READMANGA_HOSTS = ("readmanga.live", "a.zazaza.me", "web.usagi.one", "1.seimanga.me")


def search_readmanga(query):
    last_error = None
    for host in READMANGA_HOSTS:
        try:
            resp = requests.get(f"https://{host}/search/suggestion", params={"query": query},
                                headers={"User-Agent": USER_AGENT, "Referer": f"https://{host}/",
                                         "X-Requested-With": "XMLHttpRequest"},
                                timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            last_error = e
            logging.info(f"ReadManga: поиск через {host} не удался: {e}")
            continue
        base = f"https://{urlparse(resp.url).netloc or host}"
        results = []
        for s in data.get("suggestions", []):
            el = s.get("elementId") or {}
            link = s.get("link") or ""
            if el.get("type") not in (None, "MANGA") or not link:
                continue
            url = link if link.startswith("http") else base + link
            # Подсказки общие на всю федерацию сайтов: сериалы (mose.live), книги и т.п.
            # загрузчик ReadManga скачать не сможет — показываем только хосты его сети.
            if not is_group_domain(urlparse(url).netloc):
                continue
            results.append({
                "title": _clean(s.get("value")),
                "subtitle": _clean(" · ".join(x for x in (el.get("typeName"), s.get("additional")) if x)),
                "cover": s.get("thumbnail") or "",
                "url": url,
            })
            if len(results) >= LIMIT:
                break
        return results
    raise last_error or RuntimeError("сайт недоступен")


def search_mangahub(query):
    resp = requests.get("https://mangahub.ru/search", params={"query": query},
                        headers={"User-Agent": USER_AGENT, "Referer": "https://mangahub.ru/"}, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results, seen = [], set()
    for item in soup.select("div.item-slide"):
        link = item.select_one('a[href^="/title/"]')
        if not link or link["href"] in seen:
            continue
        seen.add(link["href"])
        img = item.select_one("img")
        name = item.select_one("a.fw-medium")
        meta = item.select_one("div.text-muted")
        results.append({
            "title": _clean(name.get_text() if name else (img.get("alt") if img else link["href"])),
            "subtitle": _clean(meta.get_text() if meta else ""),
            "cover": (img.get("src") or img.get("data-src") or "") if img else "",
            "url": "https://mangahub.ru" + link["href"],
        })
        if len(results) >= LIMIT:
            break
    return results


def search_mangabuff(query):
    # Те же подсказки, что в строке поиска сайта (страница /search сама грузит их через JS).
    resp = requests.get("https://mangabuff.ru/search/suggestions", params={"q": query},
                        headers={"User-Agent": USER_AGENT, "Referer": "https://mangabuff.ru/",
                                 "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
                        timeout=TIMEOUT)
    resp.raise_for_status()
    results = []
    for m in resp.json()[:LIMIT]:
        slug = m.get("slug")
        if not slug:
            continue
        kind = (m.get("type") or {}).get("name") or ""
        year = (m.get("release") or "")[:4]
        cover = m.get("image") or ""
        if cover.startswith("/"):
            cover = "https://mangabuff.ru" + cover
        results.append({
            "title": _clean(m.get("name") or slug),
            "subtitle": _clean(" · ".join(x for x in (year, kind) if x)),
            "cover": cover,
            "url": f"https://mangabuff.ru/manga/{slug}",
        })
    return results


def search_comx(query):
    """Com-X закрыт JS-проверкой — ищем через браузер без окна."""
    from browser_driver import launch_headless_browser

    driver = launch_headless_browser()
    try:
        driver.get("https://com-x.life/index.php?do=search&subaction=search&story=" + quote(query))
        for _ in range(40):
            if driver.execute_script("return !!document.querySelector('#dle-content')"):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("сайт не открыл страницу поиска")
        items = driver.execute_script("""
            return Array.from(document.querySelectorAll('#dle-content .readed.short')).map(el => {
                const a = el.querySelector('a.readed__img') || el.querySelector('.readed__title a');
                const img = el.querySelector('img');
                const t = el.querySelector('.readed__title');
                const meta = Array.from(el.querySelectorAll('.readed__meta-item'))
                    .map(m => m.textContent.trim()).filter(Boolean);
                return {url: a ? a.href : '', title: t ? t.textContent : '',
                        cover: img ? (img.getAttribute('data-src') || img.src || '') : '', meta: meta.join(' · ')};
            });""") or []
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    results = []
    for it in items:
        if not it.get("url"):
            continue
        cover = it.get("cover") or ""
        if cover.startswith("//"):
            cover = "https:" + cover
        results.append({"title": _clean(it.get("title")), "subtitle": _clean(it.get("meta")),
                        "cover": cover, "url": it["url"]})
    return results[:LIMIT]


# Ключ — значение сайта из DownloadController.SITES; подпись — как в переключателе сайта.
SEARCHERS = {
    "MangaLib": ("MangaLib", search_mangalib),
    "Com-X.life": ("Com-X", search_comx),
    "ReadManga/MintManga": ("ReadManga", search_readmanga),
    "MangaHub.ru": ("MangaHub", search_mangahub),
    "MangaBuff": ("MangaBuff", search_mangabuff),
}
