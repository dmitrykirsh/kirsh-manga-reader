"""Картинки с сайтов, защищённых от хотлинка (обложки в поиске окна «Скачать мангу»).

QML Image не умеет задавать заголовки запроса, а обложки MangaLib (cover.imglib.info)
без Referer сайта отвечают 403 — в поиске вместо обложек были пустые карточки.
Такие адреса QML получает в виде image://remote/<url-encoded адрес>, а скачивает их
RemoteImageProvider через requests с нужным Referer.
"""

import logging
import threading
from collections import OrderedDict
from urllib.parse import quote, unquote, urlparse

import requests
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImage
from PyQt6.QtQuick import QQuickImageProvider

from app.image_utils import load_image_bounded

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")

# Окончание имени хоста -> Referer, без которого хост не отдаёт картинки.
REFERERS = {
    "imglib.info": "https://mangalib.me/",
    "cdnlibs.org": "https://mangalib.me/",
    "mixlib.me": "https://mangalib.me/",
    "hentaicdn.org": "https://hentailib.me/",
}


def referer_for(host):
    host = (host or "").lower()
    for suffix, referer in REFERERS.items():
        if host == suffix or host.endswith("." + suffix):
            return referer
    return None


def qml_image_url(url):
    """Адрес картинки для QML: защищённые хосты — через image://remote, остальные как есть."""
    if url and url.startswith(("http://", "https://")) and referer_for(urlparse(url).hostname):
        return "image://remote/" + quote(url, safe="")
    return url


class RemoteImageProvider(QQuickImageProvider):
    """image://remote/<url-encoded адрес> — картинка с подстановкой Referer сайта."""

    CACHE_SIZE = 200  # обложек; повторный поиск не качает их заново

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._cache = OrderedDict()
        self._lock = threading.Lock()  # провайдер вызывается из нескольких потоков загрузки QML

    def _fetch(self, url):
        with self._lock:
            if url in self._cache:
                self._cache.move_to_end(url)
                return self._cache[url]
        headers = {"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
        referer = referer_for(urlparse(url).hostname)
        if referer:
            headers["Referer"] = referer
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        data = resp.content
        with self._lock:
            self._cache[url] = data
            while len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)
        return data

    def requestImage(self, id, requestedSize):
        url = unquote(id)
        try:
            data = self._fetch(url)
        except Exception as e:
            logging.info(f"Картинка {url} не загрузилась: {e}")
            return QImage(), QSize()
        img = load_image_bounded(data)
        if img.isNull():
            return QImage(), QSize()
        if requestedSize.width() > 0 and img.width() > requestedSize.width():
            img = img.scaledToWidth(requestedSize.width(), Qt.TransformationMode.SmoothTransformation)
        return img, QSize(img.width(), img.height())
