import QtQuick 2.15
import KirshUi 1.0

// Ползунок. Зона нажатия 40 px по высоте, сама дорожка — 4 px.
Item {
    id: root
    property real from: 0
    property real to: 100
    property real value: 0
    property real stepSize: 1
    property string label: ""
    signal moved(real value)

    implicitHeight: Theme.hit
    implicitWidth: 200
    activeFocusOnTab: true
    Accessible.role: Accessible.Slider
    Accessible.name: label
    readonly property real ratio: to > from ? Math.max(0, Math.min(1, (value - from) / (to - from))) : 0

    function setFromX(x) {
        var r = Math.max(0, Math.min(1, x / width))
        var v = from + r * (to - from)
        v = Math.round(v / stepSize) * stepSize
        v = Math.max(from, Math.min(to, v))
        if (v !== value) { value = v; moved(v) }
    }

    Rectangle {
        id: track
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: 4
        radius: 2
        color: Theme.alpha(Theme.text, 0.18)
        Rectangle {
            width: parent.width * root.ratio
            height: parent.height
            radius: 2
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.accent }
                GradientStop { position: 1; color: Theme.accentHi }
            }
        }
    }
    Rectangle {
        id: handle
        x: root.width * root.ratio - width / 2
        anchors.verticalCenter: parent.verticalCenter
        width: drag.active || hover.hovered ? 18 : 16
        height: width
        radius: width / 2
        color: Theme.text
        border.width: root.activeFocus && Theme.keyboardNav ? 3 : 0
        border.color: Theme.accent
        Behavior on width { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    DragHandler {
        id: drag
        target: null
        xAxis.enabled: true
        yAxis.enabled: false
        onCentroidChanged: if (active) root.setFromX(centroid.position.x)
    }
    TapHandler { onTapped: (p) => root.setFromX(p.position.x) }
    function step(d) {
        var v = Math.max(from, Math.min(to, value + d * stepSize))
        if (v !== value) { value = v; moved(v) }
    }
    Keys.onLeftPressed: step(-1)
    Keys.onDownPressed: step(-1)
    Keys.onRightPressed: step(1)
    Keys.onUpPressed: step(1)
}
