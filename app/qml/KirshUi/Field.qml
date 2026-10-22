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
    property bool showPaste: false   // кнопка «Вставить из буфера» справа в поле
    signal accepted()
    function focusInput() { input.forceActiveFocus() }
    // Заменяет содержимое поля текстом из буфера обмена.
    function pasteReplace() {
        input.selectAll()
        input.paste()
        var t = input.text.trim()
        if (t !== input.text) input.text = t
        input.forceActiveFocus()
    }

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
                anchors.rightMargin: root.showPaste ? pasteBtn.width : Theme.s3
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
                // Правый клик — меню «Вырезать / Копировать / Вставить / Выделить всё».
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: (point) => editMenu.show(point.position.x, point.position.y)
                }
            }
            IconButton {
                id: pasteBtn
                visible: root.showPaste
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                icon: "paste"
                iconSize: 18
                tip: "Вставить из буфера обмена (Ctrl+V)"
                onClicked: root.pasteReplace()
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

    ContextMenu {
        id: editMenu
        // Меню забирает фокус, а без фокуса TextInput сбрасывает выделение — запоминаем его.
        property int selStart: 0
        property int selEnd: 0
        function show(x, y) {
            selStart = input.selectionStart
            selEnd = input.selectionEnd
            var hasSel = selEnd > selStart
            var secret = input.echoMode !== TextInput.Normal
            var m = []
            if (hasSel && !secret) m.push({ text: "Вырезать", icon: "cut", action: "cut" })
            if (hasSel && !secret) m.push({ text: "Копировать", icon: "copy", action: "copy" })
            if (input.canPaste) m.push({ text: "Вставить", icon: "paste", action: "paste" })
            if (input.text.length) m.push({ text: "Выделить всё", action: "selectAll" })
            if (!m.length) return
            model = m
            openAt(input, x, y)
        }
        onTriggered: (item) => {
            input.forceActiveFocus()
            input.select(selStart, selEnd)
            if (item.action === "cut") input.cut()
            else if (item.action === "copy") input.copy()
            else if (item.action === "paste") input.paste()
            else if (item.action === "selectAll") input.selectAll()
        }
    }
}
