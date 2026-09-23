import QtQuick 2.15
import KirshUi 1.0

// Запрос одной строки (новое имя, ссылка).
Modal {
    id: root
    property string message: ""
    property string label: ""
    property string placeholder: ""
    property string confirmText: "Сохранить"
    property alias value: field.text
    signal submitted(string value)

    panelWidth: 480
    onOpened: field.focusInput()

    Column {
        width: parent.width
        spacing: Theme.s3
        bottomPadding: Theme.s2
        Text {
            visible: root.message !== ""
            width: parent.width
            text: root.message
            wrapMode: Text.WordWrap
            color: Theme.textDim
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsBody
            lineHeight: 1.4
        }
        Field {
            id: field
            width: parent.width
            label: root.label
            placeholder: root.placeholder
            onAccepted: if (text.trim() !== "") { root.close(); root.submitted(text) }
        }
    }
    footer: [
        AppButton { text: "Отмена"; variant: "ghost"; onClicked: root.close() },
        AppButton {
            text: root.confirmText
            variant: "primary"
            enabled: field.text.trim() !== ""
            onClicked: { root.close(); root.submitted(field.text) }
        }
    ]
}
