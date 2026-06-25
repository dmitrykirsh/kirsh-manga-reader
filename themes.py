import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePalette:
    """Хранит итоговые цвета интерфейса для выбранной темы и акцента."""
    background: str
    panel: str
    accent: str
    text: str = "#ffffff"
    muted: str = "#888888"
    border: str = "#444444"


# Единый список тем нужен, чтобы настройки и применение темы не расходились.
THEMES = {
    "Тёмная": {
        "background": "#1e1e1e",
        "panel": "#2a2a2a",
        "background_svg": "dark_hearts.svg",
    },
    "Глубокая чёрная": {
        "background": "#000000",
        "panel": "#111111",
        "background_svg": "black_guitar.svg",
    },
    "Тёмно-синяя": {
        "background": "#111a2e",
        "panel": "#1b263b",
        "background_svg": "blue_neon_city.svg",
    },
    "Тёмно-красная": {
        "background": "#2b1111",
        "panel": "#3d1818",
        "background_svg": "red_roses.svg",
    },
    "Тёмно-зелёная": {
        "background": "#112415",
        "panel": "#1b331e",
        "background_svg": "green_fireflies.svg",
    },
    "Тёмно-фиолетовая": {
        "background": "#1f112e",
        "panel": "#2e1b40",
        "background_svg": "purple_crystals.svg",
    },
    "Тёмно-серая": {
        "background": "#2d3238",
        "panel": "#3a3f47",
        "background_svg": "gray_manga_panels.svg",
    },
}


ACCENTS = {
    "Розовый": "#ff69b4",
    "Оранжевый": "#ff9800",
    "Синий": "#0078D7",
    "Зелёный": "#28a745",
    "Красный": "#dc3545",
    "Фиолетовый": "#9c27b0",
}

DEFAULT_THEME = "Тёмная"
DEFAULT_ACCENT = "Розовый"


def theme_names():
    """Возвращает доступные темы в порядке показа в настройках."""
    return list(THEMES.keys())


def accent_names():
    """Возвращает доступные акценты в порядке показа в настройках."""
    return list(ACCENTS.keys())


def resolve_theme(theme_name, accent_name):
    """Собирает безопасную палитру даже для старого или повреждённого конфига."""
    theme = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    accent = ACCENTS.get(accent_name, ACCENTS[DEFAULT_ACCENT])
    return ThemePalette(
        background=theme["background"],
        panel=theme["panel"],
        accent=accent,
    )


def theme_background_path(theme_name, data_dir):
    """Возвращает путь к SVG-фону выбранной темы для обычного запуска и PyInstaller."""
    theme = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    filename = theme.get("background_svg")
    if not filename:
        return None
    path = os.path.join(data_dir, "theme_backgrounds", filename)
    return path if os.path.exists(path) else None


def build_app_stylesheet(palette, background_image_path=None):
    """Создаёт общий Qt stylesheet приложения из выбранной палитры."""
    bg = palette.background
    panel = palette.panel
    accent = palette.accent
    text = palette.text
    border = palette.border
    background_rule = ""

    if background_image_path:
        # Qt stylesheet надёжнее читает пути с прямыми слешами, включая Windows-пути.
        image_path = background_image_path.replace("\\", "/")
        background_rule = f"""
        QWidget#MainLibraryPage, QWidget#ReaderPage {{
            background-image: url("{image_path}");
            background-repeat: repeat;
            background-position: top left;
        }}
        """

    return f"""
        QMainWindow, QWidget {{ background-color: {bg}; color: {text}; }}
        QWidget#TabScrollContent, QWidget#TransparentViewport {{
            background: transparent;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        {background_rule}
        QPushButton {{ background-color: {panel}; color: {text}; border: 1px solid {border}; padding: 6px; border-radius: 4px; }}
        QPushButton:hover {{ background-color: {accent}; color: white; }}
        QDialog {{ background-color: {bg}; }}
        QLineEdit, QListWidget, QComboBox, QCheckBox {{
            background-color: {panel};
            color: {text};
            padding: 4px;
            border: 1px solid {border};
            border-radius: 4px;
        }}

        QProgressBar {{ background-color: #333333; border: none; border-radius: 3px; }}
        QProgressBar::chunk {{ background-color: {accent}; border-radius: 3px; }}

        QSlider::groove:horizontal {{
            border: 1px solid {border};
            height: 8px;
            background: {panel};
            border-radius: 4px;
        }}
        QSlider::sub-page:horizontal {{
            background: {accent};
            border-radius: 4px;
        }}
        QSlider::add-page:horizontal {{ background: transparent; }}
        QSlider::handle:horizontal {{
            background: {text};
            border: 1px solid {border};
            width: 16px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{ background: {accent}; }}

        QScrollBar:vertical {{
            border: none;
            background: {panel};
            width: 12px;
            border-radius: 6px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {accent};
            min-height: 30px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {text}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
            height: 0px;
        }}

        QScrollBar:horizontal {{
            border: none;
            background: {panel};
            height: 12px;
            border-radius: 6px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {accent};
            min-width: 30px;
            border-radius: 6px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {text}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
            width: 0px;
        }}

        QTabBar {{ background: transparent; }}
        QTabBar::tab {{
            background: {panel};
            color: {text};
            padding: 8px 24px;
            font-weight: bold;
            border: 2px solid {accent};
            border-radius: 12px;
            margin: 0 4px;
        }}
        QTabBar::tab:hover {{ background: {accent}; color: white; }}
        QTabBar::tab:selected {{ background: {accent}; color: white; border: 2px solid {accent}; }}

        QTabWidget::pane {{ border: 1px solid {border}; background: {bg}; border-radius: 8px; margin-top: -1px; }}

        QPushButton#EmptyLibraryButton {{
            background-color: {panel};
            border: 2px dashed {accent};
            padding: 30px;
            font-size: 15px;
            font-weight: bold;
            border-radius: 12px;
            min-width: 400px;
        }}
        QPushButton#EmptyLibraryButton:hover {{
            background-color: {accent};
            color: white;
            border-style: solid;
        }}

        QMenu {{ background-color: {panel}; color: {text}; border: 1px solid {border}; padding: 5px; border-radius: 6px; }}
        QMenu::item {{ padding: 6px 28px 6px 16px; border-radius: 4px; background-color: transparent; }}
        QMenu::item:selected {{ background-color: {accent}; color: white; }}
        QMenu::separator {{ height: 1px; background-color: {border}; margin: 4px 6px; }}
    """
