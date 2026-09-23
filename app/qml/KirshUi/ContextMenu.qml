import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import KirshUi 1.0

// Контекстное меню. model: [{text, icon?, action?, danger?, checked?, header?, separator?}]
// Раскрывается из точки вызова (origin-aware): scale 0.96 + opacity, 120 мс.
C.Popup {
    id: root
    property var model: []
    signal triggered(var item)

    // Открывается всегда вниз-вправо от точки вызова — но если там не хватает места
    // (карточка у нижнего/правого края окна), меню не должно вылезать за пределы окна
    // невидимым куском: поджимаем вбок и, если нужно, разворачиваем вверх от точки клика.
    property bool flippedUp: false

    function openAt(item, x, y) {
        var overlay = C.Overlay.overlay
        var pos = overlay ? item.mapToItem(overlay, x, y) : Qt.point(x, y)
        root.parent = overlay || item
        var w = root.implicitWidth > 0 ? root.implicitWidth : root.width
        var h = root.implicitHeight > 0 ? root.implicitHeight : root.height
        var bounds = overlay ? overlay.width : (item.parent ? item.parent.width : pos.x + w)
        var boundsH = overlay ? overlay.height : (item.parent ? item.parent.height : pos.y + h)

        var px = Math.max(8, Math.min(pos.x, bounds - w - 8))
        var py = pos.y
        root.flippedUp = py + h > boundsH - 8
        if (root.flippedUp) py = pos.y - h
        py = Math.max(8, Math.min(py, boundsH - h - 8))

        root.x = px
        root.y = py
        open()
    }

    padding: 6
    width: 248
    focus: true
    // modal (без затемнения) — иначе, будучи немодальным Popup, меню не перехватывает клик:
    // выбор пункта одновременно «проваливается» на то, что находится под меню.
    modal: true
    dim: false
    closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutside
    // См. PopupTracker.qml: считаем сами, вместо того чтобы полагаться только на modal:true.
    onOpenedChanged: PopupTracker.openCount += opened ? 1 : -1

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Motion.fast; easing.type: Motion.easeOut }
            NumberAnimation { property: "scale"; from: Motion.enabled ? 0.96 : 1; to: 1; duration: Motion.fast; easing.type: Motion.easeOut }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: Motion.exit } }
    transformOrigin: flippedUp ? C.Popup.BottomLeft : C.Popup.TopLeft

    background: Rectangle {
        color: Theme.elevated
        radius: Theme.rMd
        border.width: 1
        border.color: Theme.controlBorder
    }

    contentItem: ListView {
        id: list
        implicitHeight: contentHeight
        model: root.model
        interactive: false
        clip: true
        currentIndex: -1
        keyNavigationEnabled: false
        Keys.onPressed: (e) => {
            if (e.key === Qt.Key_Down) { list.move(1); e.accepted = true }
            else if (e.key === Qt.Key_Up) { list.move(-1); e.accepted = true }
            else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter) {
                if (list.currentItem && list.currentItem.actionable) list.currentItem.fire()
                e.accepted = true
            }
        }
        function move(d) {
            var i = currentIndex
            for (var n = 0; n < count; n++) {
                i = (i + d + count) % count
                var m = root.model[i]
                if (!m.header && !m.separator) { currentIndex = i; return }
            }
        }
        delegate: Item {
            id: it
            required property var modelData
            required property int index
            readonly property bool actionable: !modelData.header && !modelData.separator
            function fire() { if (!modelData.keepOpen) root.close(); root.triggered(modelData) }
            width: list.width
            height: modelData.separator ? 13 : (modelData.header ? 30 : 38)
            Accessible.role: Accessible.MenuItem
            Accessible.name: modelData.text || ""

            Rectangle {
                visible: modelData.separator === true
                anchors.verticalCenter: parent.verticalCenter
                x: 6; width: parent.width - 12; height: 1
                color: Theme.hairline
            }
            Text {
                visible: modelData.header === true
                anchors.verticalCenter: parent.verticalCenter
                x: 10
                text: modelData.text || ""
                color: Theme.textDim
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsCaption
                font.weight: Font.DemiBold
            }
            Rectangle {
                visible: it.actionable
                anchors.fill: parent
                radius: Theme.rSm - 2
                readonly property bool active: rowHover.hovered || list.currentIndex === it.index
                color: active ? (modelData.danger ? Theme.alpha(Theme.danger, 0.16) : Theme.soft(Theme.accent)) : "transparent"
                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    x: 10
                    spacing: Theme.s3
                    Icon {
                        visible: !!modelData.icon
                        anchors.verticalCenter: parent.verticalCenter
                        name: modelData.icon || ""
                        size: 18
                        color: modelData.danger ? Theme.danger : (parent.parent.active ? Theme.accent : Theme.textDim)
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.text || ""
                        color: modelData.danger ? Theme.danger : Theme.text
                        font.family: Theme.uiFont
                        font.pixelSize: Theme.fsBody
                        font.weight: modelData.checked ? Font.DemiBold : Font.Normal
                    }
                }
                Icon {
                    visible: modelData.checked === true
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    name: "check"; size: 16; stroke: 2; color: Theme.accent
                }
                HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: it.fire() }
            }
        }
    }
    onOpened: { list.currentIndex = -1; list.forceActiveFocus() }
}
