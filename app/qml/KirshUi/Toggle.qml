import QtQuick 2.15
import KirshUi 1.0

// Переключатель вкл/выкл. Трек — тон поверхности/акцент, ручка скользит с ease-out.
Item {
    id: root
    property bool checked: false
    property string text: ""
    property string description: ""
    signal toggled(bool value)

    readonly property int trackW: 44
    readonly property int trackH: 26
    readonly property int knob: 20

    implicitWidth: label.visible ? label.implicitWidth + Theme.s3 + trackW : trackW
    implicitHeight: Math.max(trackH, label.implicitHeight)
    activeFocusOnTab: true
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    Accessible.checked: checked

    // Не пишем в checked напрямую: свойство обычно привязано к бэкенду,
    // который сам пришлёт новое значение после обработки сигнала.
    function flip() { root.toggled(!root.checked) }

    Column {
        id: label
        visible: root.text !== ""
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - trackW - Theme.s3
        spacing: 2
        Text {
            width: parent.width
            text: root.text
            color: Theme.text
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsBody
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        Text {
            visible: root.description !== ""
            width: parent.width
            text: root.description
            color: Theme.textDim
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsSmall
            wrapMode: Text.WordWrap
            lineHeight: 1.3
        }
    }

    Rectangle {
        id: track
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: root.trackW
        height: root.trackH
        radius: height / 2
        color: root.checked ? Theme.accent : Theme.elevated
        border.width: 1
        border.color: root.checked ? Theme.alpha(Theme.accent, 0.6) : Theme.controlBorder
        Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }

        Rectangle {
            id: dot
            width: root.knob
            height: root.knob
            radius: height / 2
            anchors.verticalCenter: parent.verticalCenter
            x: root.checked ? track.width - width - 3 : 3
            color: root.checked ? Theme.ink : Theme.textDim
            Behavior on x { NumberAnimation { duration: Motion.fast; easing.type: Motion.easeOut } }
            Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
        }
    }

    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: root.flip() }
    Keys.onPressed: (e) => { if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { root.flip(); e.accepted = true } }
    FocusRing { baseRadius: track.radius; anchors.fill: track }
}
