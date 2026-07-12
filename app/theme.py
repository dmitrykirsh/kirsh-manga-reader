"""Единая система оформления.

Раньше фон (7 вариантов) и акцентный цвет (6 вариантов) выбирались
независимо друг от друга — часть сочетаний просто не смотрелась. Теперь
это 5 готовых пресетов: фон, поверхности (панель/карточка/приподнятая
карточка) и акцентный градиент подобраны вместе, в духе приглушённой,
многоуровневой палитры macOS/iOS, а не плоских неоновых заливок.

Цвета текста и акценты вдохновлены системной палитрой Apple (systemBlue,
systemGreen, systemPurple, systemOrange, systemPink) — как отправная точка
для собственных градиентов, не копия чьего-то готового набора.
"""

PRESET_ORDER = ["Сакура", "Океан", "Аметист", "Изумруд", "Янтарь"]

PRESETS = {
    "Сакура": {
        "bg": "#1c1b1f", "panel": "#242327", "card": "#2a292e", "elevated": "#323136",
        "accent1": "#ff6482", "accent2": "#ff9a8b",
    },
    "Океан": {
        "bg": "#12161d", "panel": "#181e28", "card": "#1e2530", "elevated": "#252d3a",
        "accent1": "#0a84ff", "accent2": "#5ac8fa",
    },
    "Аметист": {
        "bg": "#18151f", "panel": "#201c29", "card": "#262032", "elevated": "#2e2739",
        "accent1": "#8e5ff5", "accent2": "#c86dfa",
    },
    "Изумруд": {
        "bg": "#121915", "panel": "#18211c", "card": "#1e2b23", "elevated": "#25332a",
        "accent1": "#30d158", "accent2": "#66d9a8",
    },
    "Янтарь": {
        "bg": "#1f1811", "panel": "#291f16", "card": "#33281c", "elevated": "#3c2f21",
        "accent1": "#ff9f0a", "accent2": "#ff6482",
    },
}

TEXT_PRIMARY = "#f5f5f7"
TEXT_MUTED = "#98989d"
BORDER = "rgba(255,255,255,0.08)"
BORDER_STRONG = "rgba(255,255,255,0.14)"

# Единая шкала размеров шрифта — вместо разбросанных по коду 11/13/14/23px.
FONT_DISPLAY = 28
FONT_TITLE = 18
FONT_BODY = 14
FONT_BODY_SMALL = 13
FONT_CAPTION = 12
FONT_MICRO = 11

RADIUS_LG = 16
RADIUS_MD = 12
RADIUS_SM = 8


def get_preset(name):
    return PRESETS.get(name, PRESETS[PRESET_ORDER[0]])


def accent_gradient(preset_name, angle="x1:0, y1:0, x2:1, y2:1"):
    p = get_preset(preset_name)
    return f"qlineargradient({angle}, stop:0 {p['accent1']}, stop:1 {p['accent2']})"


def accent_gradient_from(p, angle="x1:0, y1:0, x2:1, y2:1"):
    """То же самое, но принимает уже полученный словарь пресета — чтобы не
    искать его по имени повторно там, где он уже под рукой."""
    return f"qlineargradient({angle}, stop:0 {p['accent1']}, stop:1 {p['accent2']})"
