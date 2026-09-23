import QtQuick 2.15
import KirshUi 1.0

// Том: заголовок с прогрессом; если внутри главы — раскрывается. Клик по обычному тому читает его.
Column {
    id: vr
    property var vol
    property bool open: false
    signal toggled()
    signal readFile(string path)
    signal readChapter(string path, string name)

    readonly property bool hasChapters: vol && vol.chapters && vol.chapters.length > 0
    spacing: 0

    function activate() {
        if (hasChapters) toggled()
        else if (vol.path !== "") readFile(vol.path)
    }

    Item {
        width: parent.width
        height: 64
        activeFocusOnTab: true
        scale: vTap.pressed ? 0.995 : 1
        Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
        Accessible.role: Accessible.Button
        Accessible.name: vr.vol.name + ", " + vr.vol.detail
        Rectangle {
            anchors.fill: parent
            radius: Theme.rMd
            color: vHover.hovered ? Theme.elevated : (vr.vol.current ? Theme.soft(Theme.accent) : Theme.card)
            border.width: 1
            border.color: vr.vol.current ? Theme.alpha(Theme.accent, 0.5) : Theme.hairline
            Behavior on color { enabled: !Theme.switching; ColorAnimation { duration: Motion.color } }
        }
        Icon {
            visible: vr.hasChapters
            x: Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            name: "chevron-right"; size: 18; stroke: 2; color: Theme.textDim
            rotation: vr.open ? 90 : 0
            Behavior on rotation { NumberAnimation { duration: Motion.fast; easing.type: Motion.easeOut } }
        }
        Column {
            x: vr.hasChapters ? 46 : Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - 240
            spacing: 2
            Text {
                width: parent.width
                text: vr.vol.name
                elide: Text.ElideRight
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsBody
                font.weight: Font.DemiBold
            }
            Text {
                text: vr.vol.detail
                color: Theme.textDim
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsSmall
            }
        }
        Meter {
            anchors.right: parent.right
            anchors.rightMargin: Theme.s4 + 36
            anchors.verticalCenter: parent.verticalCenter
            width: 140
            value: vr.vol.progress
        }
        Icon {
            visible: !vr.hasChapters
            anchors.right: parent.right
            anchors.rightMargin: Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            name: "play"; size: 18; stroke: 2
            color: vHover.hovered ? Theme.accent : Theme.textDim
        }
        HoverHandler { id: vHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: vTap; gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: vr.activate() }
        Keys.onPressed: (e) => { if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { vr.activate(); e.accepted = true } }
        FocusRing { baseRadius: Theme.rMd }
    }

    Column {
        visible: vr.open
        width: parent.width
        leftPadding: 30
        topPadding: Theme.s1
        bottomPadding: Theme.s2
        Repeater {
            model: vr.vol.chapters
            delegate: ChapterRow {
                required property var modelData
                width: vr.width - 30
                name: modelData.name
                detail: modelData.detail
                current: modelData.current
                onClicked: vr.vol.kind === "internal" ? vr.readChapter(modelData.path, modelData.name)
                                                      : vr.readFile(modelData.path)
            }
        }
    }
}
