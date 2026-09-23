import QtQuick 2.15
import KirshUi 1.0

// Поле ввода с постоянной подписью сверху (плейсхолдер подпись не заменяет).
Item {
    id: root
    property string label: ""
    property string placeholder: ""
    property string help: ""
    property string error: ""
    property alias text: input.text
    property alias echoMode: input.echoMode
    signal accepted()
    function focusInput() { input.forceActiveFocus() }

    implicitHeight: col.implicitHeight
    implicitWidth: 320
    Accessible.role: Accessible.EditableText
    Accessible.name: label

    Column {
        id: col
        width: parent.width
        spacing: Theme.s2
        Text {
            visible: root.label !== ""
            text: root.label
            color: Theme.text
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsSmall
            font.weight: Font.DemiBold
        }
        Rectangle {
            width: parent.width
            height: Theme.hit
            radius: Theme.rSm
            color: Theme.card
            border.width: input.activeFocus ? 2 : 1
            border.color: root.error !== "" ? Theme.danger : (input.activeFocus ? Theme.accent : Theme.controlBorder)
            Behavior on border.color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
            TextInput {
                id: input
                anchors.fill: parent
                anchors.leftMargin: Theme.s3
                anchors.rightMargin: Theme.s3
                verticalAlignment: TextInput.AlignVCenter
                color: Theme.text
                selectionColor: Theme.accent
                selectedTextColor: Theme.ink
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsBody
                clip: true
                selectByMouse: true
                onAccepted: root.accepted()
                Text {
                    visible: !input.text.length
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width
                    elide: Text.ElideRight
                    text: root.placeholder
                    color: Theme.textDim
                    font: input.font
                }
            }
        }
        Text {
            visible: root.error !== "" || root.help !== ""
            width: parent.width
            wrapMode: Text.WordWrap
            text: root.error !== "" ? root.error : root.help
            color: root.error !== "" ? Theme.danger : Theme.textDim
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsCaption
        }
    }
}
