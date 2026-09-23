import QtQuick 2.15
import KirshUi 1.0

// Подтверждение. Кнопка повторяет последствие («Удалить», а не «Да»).
Modal {
    id: root
    property string message: ""
    property string confirmText: "Подтвердить"
    property bool danger: false
    signal confirmed()

    panelWidth: 460
    Text {
        width: parent.width
        text: root.message
        wrapMode: Text.WordWrap
        color: Theme.textDim
        font.family: Theme.uiFont
        font.pixelSize: Theme.fsBody
        lineHeight: 1.4
        bottomPadding: Theme.s2
    }
    footer: [
        AppButton { text: "Отмена"; variant: "ghost"; onClicked: root.close() },
        AppButton {
            text: root.confirmText
            variant: root.danger ? "dangerFill" : "primary"
            onClicked: { root.close(); root.confirmed() }
        }
    ]
}
