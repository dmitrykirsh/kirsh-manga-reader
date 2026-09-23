import QtQuick 2.15
import KirshUi 1.0

// Пункт левой рейки: иконка всегда на месте, подпись появляется при раскрытии рейки.
Item {
    id: item
    property string text: ""
    property string icon: ""
    property bool active: false
    property bool badge: false
    property bool expanded: false
    property int itemWidth: 200
    property int rowHeight: 44
    signal activated()
    signal keyFocus(bool on)
    onActiveFocusChanged: keyFocus(activeFocus)

    x: 12
    width: itemWidth
    height: rowHeight
    activeFocusOnTab: true
    scale: tap.pressed ? Motion.pressScale : 1
    Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.checked: active
    Accessible.onPressAction: item.activated()

    Rectangle {
        anchors.fill: parent
        radius: Theme.rSm
        color: rowHover.hovered && !item.active ? Theme.alpha(Theme.elevated, 0.9) : "transparent"
        Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
    }
    Icon {
        x: 12
        anchors.verticalCenter: parent.verticalCenter
        size: 24
        name: item.icon
        stroke: item.active ? 2 : 1.5
        filled: item.active
        color: item.active ? Theme.accent : (rowHover.hovered ? Theme.text : Theme.textDim)
    }
    Rectangle {
        visible: item.badge
        x: 30; y: 8; width: 10; height: 10; radius: 5
        color: Theme.accent
        border.width: 2
        border.color: Theme.panel
    }
    Text {
        x: 52
        width: parent.width - 60
        anchors.verticalCenter: parent.verticalCenter
        text: item.text
        elide: Text.ElideRight
        opacity: item.expanded ? 1 : 0
        color: item.active || rowHover.hovered ? Theme.text : Theme.textDim
        font.family: Theme.uiFont
        font.pixelSize: Theme.fsBody
        font.weight: item.active ? Font.DemiBold : Font.Medium
        Behavior on opacity { NumberAnimation { duration: item.expanded ? Motion.fade : Motion.press } }
    }
    HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: tap; gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: item.activated() }
    Keys.onPressed: (e) => {
        if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { item.activated(); e.accepted = true }
        else if (e.key === Qt.Key_Down) { var n = item.nextItemInFocusChain(true); if (n) n.forceActiveFocus(); e.accepted = true }
        else if (e.key === Qt.Key_Up) { var q = item.nextItemInFocusChain(false); if (q) q.forceActiveFocus(); e.accepted = true }
    }
    FocusRing { baseRadius: Theme.rSm }
}
