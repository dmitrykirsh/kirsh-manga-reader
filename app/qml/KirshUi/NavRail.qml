import QtQuick 2.15
import KirshUi 1.0

// Левая рейка навигации. В покое — узкая (только иконки, занимает 72 px), при наведении или
// клавиатурном фокусе раскрывается поверх контента и показывает подписи. Раскрытие чуть
// откладывается (намерение, а не случайный проезд курсора), сворачивание — сразу.
// Активный пункт — один прямоугольник, который переезжает между пунктами.
Item {
    id: root
    property var items: []     // [{text, icon}]
    property var actions: []   // [{key, text, icon, badge}]
    property int currentIndex: 0
    property string version: ""
    property bool expanded: false
    signal itemActivated(int index)
    signal actionTriggered(string key)

    readonly property int collapsedW: 72
    readonly property int expandedW: 248
    readonly property int rowH: 44
    readonly property int rowGap: 4
    readonly property int listTop: 96

    width: collapsedW
    Accessible.role: Accessible.Pane
    Accessible.name: "Основная навигация"

    Timer { id: openTimer; interval: 110; onTriggered: root.expanded = true }
    HoverHandler {
        id: hover
        onHoveredChanged: {
            if (hovered) openTimer.restart()
            else { openTimer.stop(); root.expanded = false }
        }
    }
    // Клавиатурный фокус внутри рейки тоже раскрывает её (иначе подписи недоступны без мыши).
    property int focusedCount: 0
    function keyFocus(on) {
        focusedCount += on ? 1 : -1
        if (focusedCount > 0 && Theme.keyboardNav) expanded = true
        else if (focusedCount <= 0 && !hover.hovered) expanded = false
    }

    Rectangle {
        id: panel
        z: 30
        x: 0
        height: parent.height
        width: root.expanded ? root.expandedW : root.collapsedW
        color: Theme.panel
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.alpha(Theme.elevated, 0.96) }
            GradientStop { position: 0.35; color: Theme.panel }
            GradientStop { position: 1.0; color: Theme.bg }
        }
        Behavior on width {
            NumberAnimation {
                duration: root.expanded ? Motion.base : Motion.exit
                easing.type: Easing.BezierSpline
                easing.bezierCurve: Motion.outStrong
            }
        }
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.hairline }
        clip: true

        // ---- бренд
        Item {
            x: 16; y: 24; height: 40
            width: parent.width - 32
            Rectangle {
                width: 40; height: 40; radius: 12
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.accent }
                    GradientStop { position: 1; color: Theme.accentHi }
                }
                Icon {
                    anchors.centerIn: parent
                    name: "logo"
                    size: 22
                    stroke: 2.1
                    color: Theme.ink
                }
            }
            Column {
                x: 52
                anchors.verticalCenter: parent.verticalCenter
                opacity: root.expanded ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Motion.fade; easing.type: Motion.easeOut } }
                Text { text: "Kirsh"; color: Theme.text; font.family: Theme.displayFont; font.pixelSize: 15; font.weight: Font.DemiBold }
                Text { text: "Manga Reader"; color: Theme.textDim; font.family: Theme.uiFont; font.pixelSize: Theme.fsCaption }
            }
        }

        // ---- скользящий индикатор
        Rectangle {
            x: 12
            width: parent.width - 24
            height: root.rowH
            y: root.listTop + root.currentIndex * (root.rowH + root.rowGap)
            radius: Theme.rSm
            color: Theme.soft(Theme.accent)
            Rectangle { x: 0; y: 11; width: 3; height: parent.height - 22; radius: 1.5; color: Theme.accent }
            Behavior on y { NumberAnimation { duration: Motion.fast; easing.type: Easing.BezierSpline; easing.bezierCurve: Motion.inOut } }
        }

        // ---- пункты
        Repeater {
            model: root.items
            delegate: NavItem {
                required property var modelData
                required property int index
                y: root.listTop + index * (root.rowH + root.rowGap)
                expanded: root.expanded
                itemWidth: panel.width - 24
                rowHeight: root.rowH
                text: modelData.text
                icon: modelData.icon
                active: index === root.currentIndex
                onActivated: root.itemActivated(index)
                onKeyFocus: (on) => root.keyFocus(on)
            }
        }

        // ---- нижняя часть
        Rectangle {
            x: 24; width: parent.width - 48; height: 1; color: Theme.hairline
            y: parent.height - 24 - root.actions.length * (root.rowH + root.rowGap) - 44
        }
        Repeater {
            model: root.actions
            delegate: NavItem {
                required property var modelData
                required property int index
                y: panel.height - 24 - (root.actions.length - index) * (root.rowH + root.rowGap) - 20
                expanded: root.expanded
                itemWidth: panel.width - 24
                rowHeight: root.rowH
                text: modelData.text
                icon: modelData.icon
                badge: !!modelData.badge
                onActivated: root.actionTriggered(modelData.key)
                onKeyFocus: (on) => root.keyFocus(on)
            }
        }
        Text {
            x: 24
            y: parent.height - 32
            text: root.version !== "" ? "Версия " + root.version : ""
            color: Theme.textFaint
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsCaption
            opacity: root.expanded ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Motion.fade } }
        }
    }
}
