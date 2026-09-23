import QtQuick 2.15
import KirshUi 1.0

// Пустое состояние: где вы, почему пусто и что делать дальше (одно главное действие).
Item {
    id: root
    property string icon: "library"
    property string title: ""
    property string description: ""
    property string actionText: ""
    property string actionIcon: ""
    signal action()

    implicitWidth: 420
    implicitHeight: col.implicitHeight

    Column {
        id: col
        anchors.centerIn: parent
        width: Math.min(parent.width, 420)
        spacing: Theme.s4
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 72; height: 72; radius: 22
            color: Theme.card
            border.width: 1
            border.color: Theme.hairline
            Icon { anchors.centerIn: parent; name: root.icon; size: 32; stroke: 1.5; color: Theme.accent }
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: root.title
            color: Theme.text
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsTitle
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: root.description
            color: Theme.textDim
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsBody
            lineHeight: 1.4
            wrapMode: Text.WordWrap
        }
        AppButton {
            visible: root.actionText !== ""
            anchors.horizontalCenter: parent.horizontalCenter
            variant: "primary"
            text: root.actionText
            icon: root.actionIcon
            onClicked: root.action()
        }
    }
}
