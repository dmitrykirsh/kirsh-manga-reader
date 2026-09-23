import QtQuick 2.15
import KirshUi 1.0

// Строка главы: название, статус чтения, значок «читать».
Item {
    id: cr
    property string name: ""
    property string detail: ""
    property bool current: false
    signal clicked()

    implicitHeight: 48
    height: 48
    activeFocusOnTab: true
    scale: crTap.pressed ? 0.99 : 1
    Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
    Accessible.role: Accessible.Button
    Accessible.name: name

    Rectangle {
        anchors.fill: parent
        radius: Theme.rSm
        color: crHover.hovered ? Theme.elevated : (cr.current ? Theme.soft(Theme.accent) : "transparent")
        Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
    }
    Text {
        x: Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - Theme.s4 * 2 - 220
        text: cr.name
        elide: Text.ElideRight
        color: Theme.text
        font.family: Theme.uiFont
        font.pixelSize: Theme.fsBody
    }
    Text {
        visible: cr.detail !== ""
        anchors.right: parent.right
        anchors.rightMargin: Theme.s4 + 28
        anchors.verticalCenter: parent.verticalCenter
        text: cr.detail
        color: Theme.textDim
        font.family: Theme.uiFont
        font.pixelSize: Theme.fsSmall
    }
    Icon {
        anchors.right: parent.right
        anchors.rightMargin: Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        name: "play"; size: 16; stroke: 2
        color: crHover.hovered ? Theme.accent : Theme.textDim
    }
    HoverHandler { id: crHover; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: crTap; gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: cr.clicked() }
    Keys.onPressed: (e) => { if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { cr.clicked(); e.accepted = true } }
    FocusRing { baseRadius: Theme.rSm }
}
