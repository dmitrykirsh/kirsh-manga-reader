import QtQuick 2.15
import KirshUi 1.0

// Оценка 1–5. Повторное нажатие на выбранную звезду снимает оценку.
Item {
    id: root
    property int value: 0
    property int size: 20
    property bool interactive: true
    signal rated(int value)

    implicitWidth: row.implicitWidth
    implicitHeight: interactive ? Theme.hit : size
    activeFocusOnTab: interactive
    Accessible.role: Accessible.Slider
    Accessible.name: value > 0 ? "Оценка " + value + " из 5" : "Без оценки"

    Row {
        id: row
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Repeater {
            model: 5
            delegate: Item {
                required property int index
                width: root.interactive ? 32 : root.size
                height: root.interactive ? Theme.hit : root.size
                scale: starTap.pressed ? Motion.pressScale : 1
                Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
                Icon {
                    anchors.centerIn: parent
                    name: "star"
                    size: root.size
                    stroke: 1.75
                    filled: index < (starHover.hovered && root.interactive ? hoverIndex + 1 : root.value)
                    color: index < (starHover.hovered && root.interactive ? hoverIndex + 1 : root.value) ? Theme.star : Theme.textDim
                }
                property int hoverIndex: index
                HoverHandler { id: starHover; enabled: root.interactive; cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    id: starTap
                    enabled: root.interactive
                    onTapped: root.rated(root.value === index + 1 ? 0 : index + 1)
                }
            }
        }
    }
    Keys.onLeftPressed: if (interactive && value > 0) rated(value - 1)
    Keys.onRightPressed: if (interactive && value < 5) rated(value + 1)
    FocusRing { baseRadius: Theme.rSm }
}
