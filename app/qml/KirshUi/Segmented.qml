import QtQuick 2.15
import KirshUi 1.0

// Переключатель из нескольких вариантов. model: [{label, icon?}]. Индикатор — один
// прямоугольник, который переезжает между вариантами: движение одного объекта читается как
// «выбор переехал», а не как две независимые перекраски.
Item {
    id: root
    property var model: []
    property int currentIndex: 0
    property bool stretch: false     // делить ширину поровну
    signal activated(int index)

    implicitHeight: Theme.hit
    implicitWidth: row.implicitWidth + 8
    activeFocusOnTab: true
    Accessible.role: Accessible.PageTabList

    Rectangle {
        anchors.fill: parent
        radius: Theme.rSm + 4
        color: Theme.card
        border.width: 1
        border.color: Theme.hairline
    }
    Rectangle {
        id: indicator
        readonly property Item cur: row.children[root.currentIndex] || null
        x: cur ? cur.x + row.x : 0
        y: 4
        width: cur ? cur.width : 0
        height: parent.height - 8
        radius: Theme.rSm
        color: Theme.soft(Theme.accent)
        border.width: 1
        border.color: Theme.alpha(Theme.accent, 0.45)
        Behavior on x { NumberAnimation { duration: Motion.base; easing.type: Easing.BezierSpline; easing.bezierCurve: Motion.inOut } }
        Behavior on width { NumberAnimation { duration: Motion.base; easing.type: Easing.BezierSpline; easing.bezierCurve: Motion.inOut } }
    }
    Row {
        id: row
        x: 4
        y: 4
        height: parent.height - 8
        Repeater {
            model: root.model
            delegate: Item {
                required property var modelData
                required property int index
                width: root.stretch ? (root.width - 8) / root.model.length : seg.implicitWidth + Theme.s4 * 2
                height: row.height
                scale: segTap.pressed ? Motion.pressScale : 1
                Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.label
                Accessible.selectable: true
                Accessible.selected: index === root.currentIndex
                Row {
                    id: seg
                    anchors.centerIn: parent
                    spacing: 6
                    Icon {
                        visible: !!modelData.icon
                        anchors.verticalCenter: parent.verticalCenter
                        name: modelData.icon || ""
                        size: 16
                        stroke: index === root.currentIndex ? 2 : 1.5
                        color: index === root.currentIndex ? Theme.accent : Theme.textDim
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        font.family: Theme.uiFont
                        font.pixelSize: Theme.fsBody
                        font.weight: index === root.currentIndex ? Font.DemiBold : Font.Medium
                        color: index === root.currentIndex ? Theme.text : Theme.textDim
                    }
                }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    id: segTap
                    gesturePolicy: TapHandler.ReleaseWithinBounds
                    onTapped: { root.currentIndex = index; root.activated(index) }
                }
            }
        }
    }
    Keys.onLeftPressed: if (root.currentIndex > 0) { root.currentIndex--; root.activated(root.currentIndex) }
    Keys.onRightPressed: if (root.currentIndex < root.model.length - 1) { root.currentIndex++; root.activated(root.currentIndex) }
    FocusRing { baseRadius: Theme.rSm + 4 }
}
