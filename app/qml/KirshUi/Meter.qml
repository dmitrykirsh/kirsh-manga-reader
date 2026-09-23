import QtQuick 2.15
import KirshUi 1.0

// Полоса прогресса. value 0..1. Высота 4 px; заливка — акцентный градиент.
Item {
    id: root
    property real value: 0
    property bool indeterminate: false
    property int thickness: 4
    implicitHeight: thickness
    implicitWidth: 120
    Accessible.role: Accessible.ProgressBar
    Accessible.name: Math.round(value * 100) + " процентов"

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.alpha(Theme.text, 0.14)
        clip: true
        Rectangle {
            visible: !root.indeterminate
            width: parent.width * Math.max(0, Math.min(1, root.value))
            height: parent.height
            radius: height / 2
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.accent }
                GradientStop { position: 1; color: Theme.accentHi }
            }
            Behavior on width { NumberAnimation { duration: Motion.base; easing.type: Motion.easeOut } }
        }
        Rectangle {
            id: runner
            visible: root.indeterminate
            width: parent.width * 0.35
            height: parent.height
            radius: height / 2
            color: Theme.accent
            SequentialAnimation on x {
                running: root.indeterminate
                loops: Animation.Infinite
                NumberAnimation { from: -runner.width; to: root.width; duration: 1100; easing.type: Easing.Linear }
            }
        }
    }
}
