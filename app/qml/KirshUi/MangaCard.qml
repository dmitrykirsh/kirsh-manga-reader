import QtQuick 2.15
import KirshUi 1.0

// Карточка манги/папки. Обложка 1:1.42, тонкая белая обводка; при наведении — акцентная рамка.
Item {
    id: root
    property string kind: "manga"
    property string name: ""
    property string cover: ""
    property real progress: 0
    property string status: "none"
    property string statusLabel: ""
    property int rating: 0
    property real dpr: 1

    signal opened()
    signal menuRequested(real x, real y)

    readonly property real coverH: Math.round(width * 1.42)
    implicitHeight: coverH + 76
    activeFocusOnTab: true
    scale: tap.pressed ? 0.985 : 1
    Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }

    Accessible.role: Accessible.Button
    Accessible.name: name + (kind === "folder" ? ", папка" : "") + (statusLabel ? ", " + statusLabel : "")
    Accessible.onPressAction: root.opened()

    RoundedImage {
        id: img
        width: parent.width
        height: root.coverH
        radius: Theme.rLg
        source: root.cover
        sourceSize: Qt.size(Math.round(width * root.dpr), Math.round(height * root.dpr))
        placeholderIcon: root.kind === "folder" ? "folder" : "image"
    }
    Rectangle {   // рамка наведения/фокуса поверх обводки
        anchors.fill: img
        radius: Theme.rLg
        color: "transparent"
        border.width: 2
        border.color: hover.hovered ? Theme.accent : "transparent"
        Behavior on border.color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
    }

    // статус — подложка непрозрачная, чтобы читалось на любой обложке
    Rectangle {
        visible: root.status !== "none" && root.statusLabel !== ""
        x: Theme.s2; y: Theme.s2
        height: 24
        width: stTxt.implicitWidth + Theme.s3 * 2
        radius: 12
        color: Theme.alpha(Theme.sunken, 0.86)
        border.width: 1
        border.color: Theme.alpha(tone, 0.6)
        readonly property color tone: root.status === "completed" ? Theme.success
            : root.status === "planned" ? Theme.info
            : root.status === "dropped" ? Theme.danger : Theme.accent
        Text {
            id: stTxt
            anchors.centerIn: parent
            text: root.statusLabel
            color: parent.tone
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsCaption
            font.weight: Font.DemiBold
        }
    }
    Rectangle {
        visible: root.kind === "folder"
        anchors.right: parent.right
        anchors.rightMargin: Theme.s2
        y: Theme.s2
        width: 28; height: 28; radius: 14
        color: Theme.alpha(Theme.sunken, 0.86)
        Icon { anchors.centerIn: parent; name: "folder"; size: 16; stroke: 2; color: Theme.text }
    }

    Meter {
        id: bar
        y: root.coverH + Theme.s2
        width: parent.width
        value: root.progress
        opacity: root.progress > 0 ? 1 : 0
    }
    Text {
        id: title
        y: root.coverH + Theme.s2 + 4 + Theme.s2
        width: parent.width
        text: root.name
        color: Theme.text
        font.family: Theme.uiFont
        font.pixelSize: Theme.fsSmall
        font.weight: Font.DemiBold
        lineHeight: 1.25
        wrapMode: Text.WordWrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }
    Row {
        visible: root.rating > 0
        y: title.y + title.height + 4
        spacing: 4
        Icon { name: "star"; size: 14; stroke: 1.75; filled: true; color: Theme.star }
        Text {
            text: root.rating + " из 5"
            color: Theme.textDim
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsCaption
        }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: tap; gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: root.opened() }
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: (p) => root.menuRequested(p.position.x, p.position.y)
    }
    Keys.onPressed: (e) => {
        if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { root.opened(); e.accepted = true }
        else if (e.key === Qt.Key_Menu) { root.menuRequested(width / 2, coverH / 2); e.accepted = true }
    }
    FocusRing { anchors.bottomMargin: -3 + (root.height - root.coverH); baseRadius: Theme.rLg }
}
