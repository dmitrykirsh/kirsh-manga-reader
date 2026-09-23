import QtQuick 2.15
import KirshUi 1.0

// Кнопка. variant: primary | secondary | ghost | danger | dangerFill
// Нажатие — масштаб 0.96 сразу на pointer-down; подпись начинается с глагола.
Item {
    id: root
    property string text: ""
    property string icon: ""
    property string variant: "secondary"
    property bool compact: false
    property bool busy: false
    property bool checked: false
    property alias hovered: hover.hovered
    readonly property bool pressed: tap.pressed || keyDown
    property bool keyDown: false
    signal clicked()

    readonly property bool isPrimary: variant === "primary"
    readonly property bool isFill: variant === "primary" || variant === "dangerFill"
    readonly property color fg: {
        if (variant === "primary") return Theme.ink
        if (variant === "dangerFill") return "#1a0505"
        if (variant === "danger") return Theme.danger
        if (checked) return Theme.accent
        return hovered || variant === "secondary" ? Theme.text : Theme.textDim
    }

    implicitHeight: compact ? 32 : Theme.hit
    implicitWidth: Math.max(implicitHeight, row.implicitWidth + (compact ? 24 : 32))
    opacity: enabled ? 1 : 0.45
    activeFocusOnTab: true
    scale: pressed ? Motion.pressScale : 1
    Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }

    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: root.clicked()

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: Theme.rSm
        visible: !root.isFill
        color: {
            if (root.checked) return Theme.soft(Theme.accent)
            if (root.variant === "ghost") return root.hovered ? Theme.alpha(Theme.elevated, 0.9) : "transparent"
            if (root.variant === "danger") return root.hovered ? Theme.alpha(Theme.danger, 0.14) : "transparent"
            return root.hovered ? Theme.elevated : Theme.card
        }
        border.width: root.variant === "secondary" || root.checked ? 1 : 0
        border.color: root.checked ? Theme.alpha(Theme.accent, 0.5) : (root.hovered ? Theme.controlBorder : Theme.hairline)
        Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
    }
    Rectangle {
        anchors.fill: parent
        radius: Theme.rSm
        visible: root.isFill
        color: root.variant === "dangerFill" ? Theme.danger : "transparent"
        gradient: root.variant === "primary" ? primaryGrad : null
        Gradient {
            id: primaryGrad
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: root.pressed ? Theme.accentPress : Theme.accent }
            GradientStop { position: 1; color: root.pressed ? Theme.accentPress : Theme.accentHi }
        }
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "white"
            opacity: root.hovered && !root.pressed ? 0.10 : 0
            Behavior on opacity { NumberAnimation { duration: Motion.color } }
        }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: Theme.s2
        Icon {
            visible: root.icon !== "" && !root.busy
            anchors.verticalCenter: parent.verticalCenter
            name: root.icon
            size: root.compact ? 16 : 18
            stroke: 2
            color: root.fg
        }
        Rectangle {   // индикатор занятости: вращающаяся дуга без анимации размеров
            visible: root.busy
            width: 16; height: 16; radius: 8
            anchors.verticalCenter: parent.verticalCenter
            color: "transparent"
            border.width: 2
            border.color: Theme.alpha(root.fg, 0.35)
            Rectangle { width: 4; height: 4; radius: 2; color: root.fg; x: 10; y: 1 }
            RotationAnimator on rotation { running: root.busy; from: 0; to: 360; duration: 900; loops: Animation.Infinite }
        }
        Text {
            visible: root.text !== ""
            anchors.verticalCenter: parent.verticalCenter
            text: root.text
            color: root.fg
            font.family: Theme.uiFont
            font.pixelSize: root.compact ? Theme.fsSmall : Theme.fsBody
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor; enabled: root.enabled }
    TapHandler {
        id: tap
        enabled: root.enabled && !root.busy
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: root.clicked()
    }
    Keys.onPressed: (e) => {
        if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) {
            root.keyDown = true
            e.accepted = true
        }
    }
    Keys.onReleased: (e) => {
        if (root.keyDown && (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space)) {
            root.keyDown = false
            if (root.enabled && !root.busy) root.clicked()
            e.accepted = true
        }
    }
    FocusRing { baseRadius: Theme.rSm }
}
