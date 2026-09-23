import QtQuick 2.15
import KirshUi 1.0

// Слот экрана. Входящий: 20 px по оси + fade 240 мс; уходящий: только fade, быстрее.
// slide = false (читалка) — мгновенный fade без сдвига.
Item {
    id: root
    property bool shown: false
    property bool slide: true
    default property alias content: holder.data

    visible: opacity > 0.001
    opacity: shown ? 1 : 0
    enabled: shown
    Behavior on opacity {
        NumberAnimation { duration: root.shown ? Motion.page : Motion.exit; easing.type: Motion.easeOut }
    }

    Item {
        id: holder
        width: parent.width
        height: parent.height
        transform: Translate {
            y: root.shown || !root.slide ? 0 : 20
            Behavior on y { NumberAnimation { duration: Motion.page; easing.type: Motion.easeOut } }
        }
    }
    onShownChanged: if (shown) forceActiveFocus()
}
