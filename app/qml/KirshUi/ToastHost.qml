import QtQuick 2.15
import KirshUi 1.0

// Уведомления в правом нижнем углу. Ошибки живут дольше; при наведении таймер стоит.
// Ошибка — role=alert, остальное — status (скринридер читает без перебивания).
Item {
    id: root
    function show(kind, text) {
        model.append({ kind: kind, text: text })
        if (model.count > 4) model.remove(0)
    }

    width: 400
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    anchors.margins: Theme.s5
    height: col.height

    ListModel { id: model }

    Column {
        id: col
        width: parent.width
        spacing: Theme.s2
        move: Transition { NumberAnimation { properties: "y"; duration: Motion.base; easing.type: Motion.easeOut } }
        Repeater {
            model: model
            delegate: Rectangle {
                id: toast
                required property string kind
                required property string text
                required property int index
                readonly property color tone: kind === "error" ? Theme.danger : kind === "success" ? Theme.success
                                            : kind === "warn" ? Theme.warning : Theme.info
                width: col.width
                height: content.implicitHeight + Theme.s3 * 2
                radius: Theme.rMd
                color: Theme.elevated
                border.width: 1
                border.color: Theme.alpha(tone, 0.5)
                opacity: 0
                property real slide: 12
                transform: Translate { y: toast.slide }
                Accessible.role: kind === "error" ? Accessible.AlertMessage : Accessible.StaticText
                Accessible.name: text

                Component.onCompleted: { opacity = 1; slide = 0 }
                Behavior on opacity { NumberAnimation { duration: Motion.fade; easing.type: Motion.easeOut } }
                Behavior on slide { NumberAnimation { duration: Motion.base; easing.type: Motion.easeOut } }

                Rectangle { x: 0; width: 3; height: parent.height - 16; y: 8; radius: 1.5; color: toast.tone }
                Row {
                    id: content
                    x: Theme.s4
                    y: Theme.s3
                    width: parent.width - Theme.s4 - Theme.s2 - 32
                    spacing: Theme.s3
                    Icon {
                        y: 1
                        name: toast.kind === "error" ? "warning" : toast.kind === "success" ? "check" : toast.kind === "warn" ? "warning" : "info"
                        size: 18; stroke: 2; color: toast.tone
                    }
                    Text {
                        width: parent.width - 18 - Theme.s3
                        text: toast.text
                        wrapMode: Text.WordWrap
                        color: Theme.text
                        font.family: Theme.uiFont
                        font.pixelSize: Theme.fsBody
                        lineHeight: 1.3
                    }
                }
                IconButton {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 2
                    width: 32; height: 32
                    icon: "close"; iconSize: 16
                    tip: "Закрыть уведомление"
                    onClicked: toast.dismiss()
                }
                HoverHandler { id: toastHover }
                Timer {
                    id: life
                    interval: toast.kind === "error" ? 9000 : 5000
                    running: !toastHover.hovered
                    repeat: false
                    onTriggered: toast.dismiss()
                }
                function dismiss() {
                    fadeOut.start()
                }
                SequentialAnimation {
                    id: fadeOut
                    NumberAnimation { target: toast; property: "opacity"; to: 0; duration: Motion.exit }
                    ScriptAction { script: model.remove(toast.index) }
                }
            }
        }
    }
}
