import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import KirshUi 1.0

// Кнопка-иконка 40×40 (цель нажатия для десктопа). Обязательная подсказка — она же имя для скринридера.
Item {
    id: root
    property string icon: ""
    property string tip: ""
    property bool checked: false
    property bool danger: false
    property int iconSize: 20
    property alias hovered: hover.hovered
    readonly property bool pressed: tap.pressed || keyDown
    property bool keyDown: false
    signal clicked()

    implicitWidth: Theme.hit
    implicitHeight: Theme.hit
    activeFocusOnTab: true
    opacity: enabled ? 1 : 0.45
    scale: pressed ? Motion.pressScale : 1
    Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }

    Accessible.role: Accessible.Button
    Accessible.name: tip
    Accessible.onPressAction: root.clicked()

    Rectangle {
        anchors.fill: parent
        radius: Theme.rSm
        color: root.checked ? Theme.soft(Theme.accent)
             : root.hovered ? Theme.alpha(Theme.elevated, 0.95) : "transparent"
        Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
    }
    Icon {
        anchors.centerIn: parent
        name: root.icon
        size: root.iconSize
        stroke: root.checked ? 2 : 1.5
        filled: false
        color: root.danger ? Theme.danger : (root.checked ? Theme.accent : (root.hovered ? Theme.text : Theme.textDim))
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor; enabled: root.enabled }
    TapHandler { id: tap; enabled: root.enabled; gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: root.clicked() }
    Keys.onPressed: (e) => {
        if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { root.keyDown = true; e.accepted = true }
    }
    Keys.onReleased: (e) => {
        if (root.keyDown && (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space)) {
            root.keyDown = false; root.clicked(); e.accepted = true
        }
    }
    FocusRing { baseRadius: Theme.rSm }

    C.ToolTip {
        visible: root.tip !== "" && hover.hovered && !tap.pressed
        delay: 550
        text: root.tip
        contentItem: Text {
            text: root.tip
            color: Theme.text
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsCaption
        }
        background: Rectangle { color: Theme.elevated; radius: Theme.rXs; border.color: Theme.hairline }
    }
}
