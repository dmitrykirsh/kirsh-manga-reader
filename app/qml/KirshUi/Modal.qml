import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import KirshUi 1.0

// Модальное окно поверх приложения. Esc и клик по затемнению закрывают; фокус остаётся внутри.
// Появление — из scale 0.97 + прозрачность (модалки не привязаны к триггеру, поэтому центр);
// исчезновение быстрее появления.
C.Popup {
    id: root
    property string title: ""
    property string subtitle: ""
    property int panelWidth: 560
    property bool showClose: true
    property bool dismissible: true
    default property alias content: body.data
    property alias footer: footerRow.data
    property bool hasFooter: footerRow.children.length > 0

    parent: C.Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    padding: 0
    width: Math.min(panelWidth, parent ? parent.width - Theme.s6 * 2 : panelWidth)
    height: Math.min(implicitHeight, parent ? parent.height - Theme.s6 * 2 : implicitHeight)
    closePolicy: dismissible ? (C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutside) : C.Popup.NoAutoClose

    C.Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.6) }

    // См. PopupTracker.qml: считаем сами, вместо того чтобы полагаться только на modal:true.
    onOpenedChanged: PopupTracker.openCount += opened ? 1 : -1

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Motion.base; easing.type: Motion.easeOut }
            NumberAnimation { property: "scale"; from: Motion.enabled ? 0.97 : 1; to: 1; duration: Motion.base; easing.type: Motion.easeOut }
        }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; to: 0; duration: Motion.exit; easing.type: Motion.easeOut }
    }

    background: Rectangle {
        color: Theme.panel
        radius: Theme.rLg
        border.width: 1
        border.color: Theme.hairline
    }

    contentItem: Item {
        implicitHeight: header.height + body.implicitHeight + (root.hasFooter ? footerBar.height : 0) + Theme.s5
        Item {
            id: header
            width: parent.width
            height: (root.title !== "" ? titleCol.implicitHeight : 0) + Theme.s5 + Theme.s3
            visible: root.title !== ""
            Column {
                id: titleCol
                x: Theme.s5
                y: Theme.s5
                width: parent.width - Theme.s5 * 2 - (root.showClose ? Theme.hit : 0)
                spacing: 2
                Text {
                    width: parent.width
                    text: root.title
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: Theme.fsTitle
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
                Text {
                    visible: root.subtitle !== ""
                    width: parent.width
                    text: root.subtitle
                    color: Theme.textDim
                    font.family: Theme.uiFont
                    font.pixelSize: Theme.fsSmall
                    wrapMode: Text.WordWrap
                }
            }
            IconButton {
                visible: root.showClose
                anchors.right: parent.right
                anchors.rightMargin: Theme.s3
                y: Theme.s3
                icon: "close"
                tip: "Закрыть"
                onClicked: root.close()
            }
        }
        Item {
            id: body
            x: Theme.s5
            y: header.height
            width: parent.width - Theme.s5 * 2
            implicitHeight: childrenRect.height
            height: implicitHeight
        }
        Rectangle {
            id: footerBar
            visible: root.hasFooter
            anchors.bottom: parent.bottom
            width: parent.width
            height: visible ? Theme.hit + Theme.s4 * 2 : 0
            color: "transparent"
            Rectangle { width: parent.width; height: 1; color: Theme.hairline }
            Row {
                id: footerRow
                anchors.right: parent.right
                anchors.rightMargin: Theme.s5
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.s2
            }
        }
    }
}
