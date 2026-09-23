import QtQuick 2.15
import KirshUi 1.0

// Кольцо фокуса 2 px — только при клавиатурной навигации (аналог :focus-visible).
// Рисуется снаружи родителя, поэтому не двигает вёрстку и не перекрывается границей.
Rectangle {
    property real baseRadius: Theme.rSm
    property Item host: parent

    anchors.fill: parent
    anchors.margins: -3
    radius: baseRadius + 3
    color: "transparent"
    border.width: 2
    border.color: Theme.accent
    visible: Theme.keyboardNav && host && host.activeFocus
    z: 100
}
