pragma Singleton
import QtQuick 2.15

/*
  Единственный источник правды по оформлению.

  Цвета приходят из Python (app/theme.py → backend.palette): там же они проверяются на
  контраст. Здесь — только роли, размеры и шкалы.

  Правила:
  * Токены называются по роли, а не по внешнему виду. Компоненты используют только их.
  * Один цвет — одна работа: accent = «интерактивное/активное», success/warning/danger/info —
    статусы, star — оценка.
  * Возвышение — тон + hairline, теней нет.
  * Радиусы вложены: внешний = внутренний + отступ (16 → 15 у обложки с рамкой 1 px).
*/
QtObject {
    id: theme

    // палитра из Python; пустая — пока Main.qml не выставил (значения по умолчанию = «Закат»)
    property var p: ({})
    function c(key, fallback) { return p && p[key] !== undefined ? p[key] : fallback }

    // Меняется на время смены темы: на это время цветовые анимации отключены,
    // иначе все поверхности «плывут» разом.
    property bool switching: false
    // Клавиатурная навигация (аналог :focus-visible) — приходит из Python.
    property bool keyboardNav: false

    readonly property color accent:      c("accent", "#ff944f")
    readonly property color accentHi:    c("accent_hi", "#ff6682")
    readonly property color accentPress: c("accent_press", "#e87432")
    readonly property color ink:         c("ink", "#210c02")     // текст на акцентной заливке
    readonly property color inkDim:      c("ink_dim", "#63290d")

    readonly property color sunken:   c("sunken", "#0d0f12")
    readonly property color bg:       c("bg", "#12100f")
    readonly property color panel:    c("panel", "#1b1714")
    readonly property color card:     c("card", "#211b17")
    readonly property color elevated: c("elevated", "#2a221c")

    readonly property color hairline:       c("hairline", "#3a302a")
    readonly property color controlBorder:  c("control_border", "#7a6a60")
    readonly property color text:       c("text", "#f4f1ef")
    readonly property color textDim:    c("text_dim", "#bdb5b0")
    readonly property color textFaint:  c("text_faint", "#a89f99")

    readonly property color success: "#5fd88a"
    readonly property color warning: "#ffc14d"
    readonly property color danger:  "#ff6b6b"
    readonly property color info:    "#57c7ff"
    readonly property color star:    "#ffc14d"

    // обводка поверх изображений: чисто белая, низкая непрозрачность (не тонированная)
    readonly property color imageOutline: Qt.rgba(1, 1, 1, 0.10)

    function alpha(color, a) { return Qt.rgba(color.r, color.g, color.b, a) }
    function soft(color) { return alpha(color, 0.16) }
    function hex(color) {
        var r = Math.round(color.r * 255), g = Math.round(color.g * 255), b = Math.round(color.b * 255)
        function h(v) { return (v < 16 ? "0" : "") + v.toString(16) }
        return h(r) + h(g) + h(b)
    }

    // ---- геометрия: сетка 4/8/12/16/24/32/48 -------------------------------------------
    readonly property int s1: 4
    readonly property int s2: 8
    readonly property int s3: 12
    readonly property int s4: 16
    readonly property int s5: 24
    readonly property int s6: 32
    readonly property int s7: 48

    readonly property int rLg: 16   // панели, карточки
    readonly property int rMd: 12   // крупные контролы
    readonly property int rSm: 10   // контролы
    readonly property int rXs: 6    // мелкие плашки

    readonly property int hit: 40   // минимальная цель нажатия на десктопе

    // ---- типографика: три семейства максимум; размеры из шкалы --------------------------
    readonly property string uiFont: "Segoe UI"
    readonly property string displayFont: typeof appDisplayFont !== "undefined" ? appDisplayFont : "Unbounded"
    readonly property int fsCaption: 12   // нижний предел
    readonly property int fsSmall: 13
    readonly property int fsBody: 14
    readonly property int fsLead: 16
    readonly property int fsTitle: 20
    readonly property int fsDisplay: 28
}
