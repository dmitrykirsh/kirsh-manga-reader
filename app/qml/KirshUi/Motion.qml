pragma Singleton
import QtQuick 2.15

/*
  Токены движения.

  * Вход и выход — ease-out (сильная кривая cubic-bezier(.23,1,.32,1)); ease-in для интерфейса
    не используем: он задерживает начало движения ровно тогда, когда на него смотрят.
  * Потолок 260 мс. Выход быстрее входа. Без bounce.
  * Нажатие: масштаб ровно 0.96, отклик мгновенный.
  * Частые действия (переключение вкладок, наведение на карточки) — минимум движения.
  * Клавиатурные действия не анимируются.
  * enabled = false, если Windows отключил анимации: обнуляем движение,
    но оставляем короткие смены цвета и прозрачности — они помогают понять, что произошло.
*/
QtObject {
    id: motion

    property bool enabled: true
    readonly property real k: enabled ? 1.0 : 0.0

    readonly property int press: Math.round(120 * k)
    readonly property int fast:  Math.round(150 * k)
    readonly property int base:  Math.round(200 * k)
    readonly property int page:  Math.round(240 * k)   // смена экрана
    readonly property int exit:  Math.round(140 * k)   // всегда быстрее входа
    readonly property int color: 140                   // цвет и прозрачность не обнуляются
    readonly property int fade:  160

    readonly property real pressScale: 0.96

    readonly property var outStrong: [0.23, 1.0, 0.32, 1.0, 1.0, 1.0]
    readonly property var inOut:     [0.77, 0.0, 0.175, 1.0, 1.0, 1.0]
    readonly property int easeOut: Easing.OutCubic
}
