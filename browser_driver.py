"""Запуск Selenium-браузера для интерактивной авторизации (MangaLib/HentaiLib/SlashLIB,
Com-X.life, ReadManga/MintManga и зеркала).

Пробует Chrome первым (используя локальный chromedriver.exe рядом с exe,
если он есть, иначе автоматически скачивает через webdriver_manager).
Если Chrome не установлен или не запускается — автоматически пробует Edge
(он есть по умолчанию на любой Windows 10/11, поэтому это надёжный fallback).
"""
import os
import sys
import logging


def _base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_chrome_driver_path():
    local_driver = os.path.join(_base_dir(), "chromedriver.exe")
    return local_driver if os.path.exists(local_driver) else None


def _launch_chrome():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService

    options = ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver_path = get_chrome_driver_path()
    if not driver_path:
        from webdriver_manager.chrome import ChromeDriverManager
        driver_path = ChromeDriverManager().install()

    return webdriver.Chrome(service=ChromeService(driver_path), options=options)


def _launch_edge():
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.edge.service import Service as EdgeService
    from webdriver_manager.microsoft import EdgeChromiumDriverManager

    options = EdgeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver_path = EdgeChromiumDriverManager().install()
    return webdriver.Edge(service=EdgeService(driver_path), options=options)


def launch_authenticated_browser():
    """Возвращает (driver, browser_name). Бросает RuntimeError, если не
    удалось запустить ни Chrome, ни Edge."""
    errors = []

    try:
        return _launch_chrome(), "Chrome"
    except Exception as e:
        errors.append(f"Chrome: {e}")
        logging.warning(f"Не удалось запустить Chrome, пробую Edge: {e}")

    try:
        return _launch_edge(), "Edge"
    except Exception as e:
        errors.append(f"Edge: {e}")
        logging.error(f"Не удалось запустить Edge: {e}")

    raise RuntimeError(
        "Не удалось запустить ни Chrome, ни Edge для авторизации. "
        "Установите один из этих браузеров.\n" + "\n".join(errors)
    )
