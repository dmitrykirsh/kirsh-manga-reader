import QtQuick 2.15
import KirshUi 1.0

// Плашка-метка. tone: neutral | accent | success | warning | danger | info
// interactive = true делает её кнопкой (стрелка вниз — раскрывает меню/список).
Item {
    id: root
    property string text: ""
    property string icon: ""
    property string tone: "neutral"
    property bool interactive: false
    property bool dropdown: false
    property alias hovered: hover.hovered
    signal clicked()

    readonly property color toneColor: tone === "accent" ? Theme.accent
        : tone === "success" ? Theme.success
        : tone === "warning" ? Theme.warning
        : tone === "danger" ? Theme.danger
        : tone === "info" ? Theme.info : Theme.text

    implicitHeight: interactive ? 32 : 28
    implicitWidth: row.implicitWidth + Theme.s3 * 2
    activeFocusOnTab: interactive
    scale: tap.pressed ? Motion.pressScale : 1
    Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
    Accessible.role: interactive ? Accessible.Button : Accessible.StaticText
    Accessible.name: text

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.tone === "neutral" ? (root.hovered && root.interactive ? Theme.elevated : Theme.card)
                                       : Theme.alpha(root.toneColor, root.hovered && root.interactive ? 0.24 : 0.16)
        border.width: 1
        border.color: root.tone === "neutral" ? (root.interactive ? Theme.controlBorder : Theme.hairline)
                                              : Theme.alpha(root.toneColor, 0.35)
        Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
    }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 6
        Icon {
            visible: root.icon !== ""
            anchors.verticalCenter: parent.verticalCenter
            name: root.icon; size: 14; stroke: 2
            color: root.tone === "neutral" ? Theme.textDim : root.toneColor
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.text
            color: root.tone === "neutral" ? Theme.text : root.toneColor
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsSmall
            font.weight: Font.DemiBold
        }
        Icon {
            visible: root.dropdown
            anchors.verticalCenter: parent.verticalCenter
            name: "chevron-down"; size: 14; stroke: 2
            color: root.tone === "neutral" ? Theme.textDim : root.toneColor
        }
    }
    HoverHandler { id: hover; enabled: root.interactive; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: tap; enabled: root.interactive; gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: root.clicked() }
    Keys.onPressed: (e) => { if (root.interactive && (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space)) { root.clicked(); e.accepted = true } }
    FocusRing { baseRadius: height / 2 }
}
