import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import KirshUi 1.0

// Тонкая полоса прокрутки: 6 px в покое, шире и акцентная при наведении.
C.ScrollBar {
    id: bar
    implicitWidth: 12
    padding: 3
    minimumSize: 0.08
    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 40
        radius: width / 2
        color: bar.pressed || bar.hovered ? Theme.accent : Theme.alpha(Theme.text, 0.28)
        opacity: bar.size < 1 ? 1 : 0
        Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
    }
    background: Item {}
}
