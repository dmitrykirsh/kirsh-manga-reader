import QtQuick 2.15
import KirshUi 1.0

// Поле поиска: иконка, текст, кнопка очистки. Esc — очистить, повторный Esc — снять фокус.
Item {
    id: root
    property alias text: input.text
    property string placeholder: "Поиск по названию"
    property alias inputFocus: input.activeFocus
    signal escaped()
    signal accepted()
    function focusInput() { input.forceActiveFocus(); input.selectAll() }

    implicitHeight: Theme.hit
    implicitWidth: 280
    Accessible.role: Accessible.EditableText
    Accessible.name: placeholder

    Rectangle {
        anchors.fill: parent
        radius: Theme.rSm
        color: Theme.card
        border.width: input.activeFocus ? 2 : 1
        border.color: input.activeFocus ? Theme.accent : Theme.controlBorder
        Behavior on border.color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
    }
    Icon {
        id: lens
        x: Theme.s3
        anchors.verticalCenter: parent.verticalCenter
        name: "search"; size: 18
        color: input.activeFocus ? Theme.accent : Theme.textDim
    }
    TextInput {
        id: input
        anchors.left: lens.right
        anchors.leftMargin: Theme.s2
        anchors.right: clearBtn.left
        anchors.rightMargin: Theme.s1
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.text
        selectionColor: Theme.accent
        selectedTextColor: Theme.ink
        font.family: Theme.uiFont
        font.pixelSize: Theme.fsBody
        clip: true
        selectByMouse: true
        Keys.onEscapePressed: { if (text.length) text = ""; else root.escaped() }
        onAccepted: root.accepted()
        Text {
            visible: !input.text.length
            anchors.verticalCenter: parent.verticalCenter
            text: root.placeholder
            color: Theme.textDim
            font: input.font
        }
    }
    Item {
        id: clearBtn
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 32; height: 32
        visible: input.text.length > 0
        Icon { anchors.centerIn: parent; name: "close"; size: 16; color: clearHover.hovered ? Theme.text : Theme.textDim }
        HoverHandler { id: clearHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: { input.text = ""; input.forceActiveFocus() } }
        Accessible.role: Accessible.Button
        Accessible.name: "Очистить поиск"
    }
}
