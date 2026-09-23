"""Единая система оформления — дизайн-токены и 4 проработанные темы.

Модель токенов (глубина слоёв, а не «один цвет на всё»):
* bg_base            — холст: главный фон окна / библиотеки
* bg_surface         — сайдбар, модалки, тулбары
* bg_surface_elevated— поля ввода, карточки внутри настроек, неактивные кнопки
* border_subtle      — тонкие разделители и рамки инпутов
* text_primary       — заголовки, названия
* text_secondary     — второстепенные подписи, иконки, счётчики
* accent_primary     — основной акцент: подтверждение, активная вкладка, бейджи
* accent_hover       — состояние наведения/нажатия на акцентные элементы

Остальные ключи (sunken, card, control_border, text_faint, ink, ink_press...)
выводятся из этих восьми, чтобы не описывать вручную каждую тему целиком —
но именно восемь токенов выше определяют характер темы.

Движение: только ease-out, ≤ 260 мс, выход быстрее входа, без bounce;
уважаем системное отключение анимаций Windows.
"""

import os
import sys

from app.constants import DATA_DIR

# ---- темы ---------------------------------------------------------------

PRESET_ORDER = ["Onyx & Amber", "Catppuccin Mocha", "Nordic Slate", "Shonen Crimson"]
DEFAULT_PRESET = "Onyx & Amber"

# Имена из версий до этого редизайна → ближайшая новая тема, чтобы сохранённый
# конфиг не сбрасывался на дефолт молча.
LEGACY_NAMES = {
    "Закат": "Onyx & Amber",
    "Янтарь": "Onyx & Amber",
    "Сакура": "Catppuccin Mocha",
    "Аметист": "Catppuccin Mocha",
    "Полночь": "Catppuccin Mocha",
    "Алый": "Shonen Crimson",
    "Мята": "Nordic Slate",
    "Изумруд": "Nordic Slate",
    "Океан": "Nordic Slate",
    "Серебро": "Nordic Slate",
}

# Восемь токенов на тему — источник истины для остального (см. get_preset).
_TOKENS = {
    "Onyx & Amber": {
        "bg_base": "#121214", "bg_surface": "#18181C", "bg_surface_elevated": "#222228",
        "border_subtle": "#2D2D35", "text_primary": "#F3F4F6", "text_secondary": "#8A8F9E",
        "accent_primary": "#F97316", "accent_hover": "#EA580C",
    },
    "Catppuccin Mocha": {
        "bg_base": "#1E1E2E", "bg_surface": "#181825", "bg_surface_elevated": "#313244",
        "border_subtle": "#45475A", "text_primary": "#CDD6F4", "text_secondary": "#9399B2",
        "accent_primary": "#CBA6F7", "accent_hover": "#B4BEFE",
    },
    "Nordic Slate": {
        "bg_base": "#0F172A", "bg_surface": "#0B1120", "bg_surface_elevated": "#1E293B",
        "border_subtle": "#334155", "text_primary": "#F8FAFC", "text_secondary": "#94A3B8",
        "accent_primary": "#06B6D4", "accent_hover": "#0891B2",
    },
    "Shonen Crimson": {
        "bg_base": "#141414", "bg_surface": "#1A1A1A", "bg_surface_elevated": "#262626",
        "border_subtle": "#333333", "text_primary": "#FFFFFF", "text_secondary": "#737373",
        "accent_primary": "#E11D48", "accent_hover": "#BE123C",
    },
}

SUCCESS = "#5fd88a"
WARNING = "#ffc14d"
DANGER = "#ff6b6b"
INFO = "#57c7ff"


def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(base, tint, amount):
    """Смесь двух #rrggbb: amount=0 → base, 1 → tint."""
    a, b = _rgb(base), _rgb(tint)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * amount) for i in range(3))


def _luminance(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _ink_for(accent):
    """Текст поверх акцентной заливки: тёмный на светлом/ярком акценте, светлый на тёмном."""
    return "#150c06" if _luminance(accent) > 0.42 else "#faf7f4"


def normalize_name(name):
    name = LEGACY_NAMES.get(str(name or ""), str(name or ""))
    return name if name in _TOKENS else DEFAULT_PRESET


def get_preset(name):
    name = normalize_name(name)
    t = _TOKENS[name]
    accent, hover = t["accent_primary"], t["accent_hover"]
    ink = _ink_for(accent)
    p = {
        "name": name,
        # ---- акцент: активные состояния, главная кнопка, прогресс
        "accent": accent, "accent_hi": hover, "accent_press": mix(accent, "#000000", 0.22),
        "ink": ink, "ink_dim": mix(ink, accent, 0.35),
        # ---- глубина поверхностей: холст → сайдбар/модалки → карточки → поля ввода
        "sunken": mix(t["bg_base"], "#000000", 0.35),
        "bg": t["bg_base"],
        "panel": t["bg_surface"],
        "card": mix(t["bg_surface"], t["bg_surface_elevated"], 0.5),
        "elevated": t["bg_surface_elevated"],
        # ---- линии и текст
        "hairline": t["border_subtle"],
        "hairline_strong": mix(t["border_subtle"], t["text_primary"], 0.22),
        "text": t["text_primary"],
        "text_dim": t["text_secondary"],
        "text_faint": mix(t["text_secondary"], t["bg_surface"], 0.25),
        # Граница интерактивного контрола (поле ввода, чекбокс): WCAG 1.4.11 требует 3:1.
        "control_border": mix(t["border_subtle"], t["text_primary"], 0.45),
    }
    # Старые ключи — на них завязан прежний код (info_page, dialogs).
    p["accent1"], p["accent2"] = p["accent"], p["accent_hi"]
    return p


# ---- шрифты ---------------------------------------------------------------

UI_FONT = "Segoe UI"
DISPLAY_FONT = "Unbounded"  # только верхнеуровневые заголовки; не для плотного текста
_display_loaded = False


def load_fonts():
    """Регистрирует бандл-шрифт Unbounded (поддерживает кириллицу). Нужен живой
    QApplication. Если файла нет — молча остаёмся на системном шрифте."""
    global _display_loaded, DISPLAY_FONT
    from PyQt6.QtGui import QFontDatabase
    path = os.path.join(DATA_DIR, "app", "assets", "fonts", "Unbounded-Variable.ttf")
    if not os.path.exists(path):
        DISPLAY_FONT = UI_FONT
        return
    fid = QFontDatabase.addApplicationFont(path)
    families = QFontDatabase.applicationFontFamilies(fid) if fid != -1 else []
    DISPLAY_FONT = families[0] if families else UI_FONT
    _display_loaded = bool(families)


# ---- движение -----------------------------------------------------------

_MOTION_CACHE = None


def motion_enabled():
    """Windows умеет отключать анимации системно (SPI_GETCLIENTAREAANIMATION)."""
    global _MOTION_CACHE
    if _MOTION_CACHE is not None:
        return _MOTION_CACHE
    enabled = True
    if sys.platform == "win32":
        try:
            import ctypes
            flag = ctypes.c_int(1)
            SPI_GETCLIENTAREAANIMATION = 0x1042
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(flag), 0):
                enabled = bool(flag.value)
        except Exception:
            pass
    _MOTION_CACHE = enabled
    return enabled
