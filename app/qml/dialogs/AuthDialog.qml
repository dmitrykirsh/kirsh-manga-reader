import QtQuick 2.15
import KirshUi 1.0

// Ожидание входа в аккаунт в браузере. Не закрывается по Esc/клику мимо: закрыть можно
// только осознанно («Отмена») — иначе вход может оборваться на середине.
Modal {
    id: root
    property var d: backend.downloads.authDialog
    title: "Вход в аккаунт"
    subtitle: d && d.site ? d.site : ""
    panelWidth: 480
    dismissible: false
    showClose: false
    visible: false

    Connections {
        target: backend.downloads
        function onAuthDialogChanged() {
            var v = backend.downloads.authDialog
            if (v && v.visible && !root.opened) root.open()
            else if ((!v || !v.visible) && root.opened) root.close()
        }
    }

    Column {
        width: parent.width
        spacing: Theme.s3
        bottomPadding: Theme.s5
        Text {
            width: parent.width
            text: root.d ? root.d.message : ""
            wrapMode: Text.WordWrap
            color: Theme.text
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsBody
            lineHeight: 1.4
        }
        Text {
            width: parent.width
            text: "Войдите в аккаунт в открывшемся окне браузера. Когда закончите, нажмите «Я вошёл»."
            wrapMode: Text.WordWrap
            color: Theme.textDim
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsSmall
            lineHeight: 1.4
        }
        Meter { width: parent.width; indeterminate: true }
    }
    footer: [
        AppButton { text: "Отмена"; variant: "ghost"; onClicked: backend.downloads.cancelAuth() },
        AppButton { text: "Я вошёл — продолжить"; variant: "primary"; onClicked: backend.downloads.confirmAuth() }
    ]
}
