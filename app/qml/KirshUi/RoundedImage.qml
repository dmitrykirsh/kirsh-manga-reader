import QtQuick 2.15
import QtQuick.Effects
import KirshUi 1.0

// Изображение со скруглением и тонкой белой обводкой (1 px, низкая непрозрачность):
// обводка отделяет обложку от фона, не тонируя её. Радиус ВНУТРИ на рамку меньше внешнего.
Item {
    id: root
    property url source
    property real radius: Theme.rLg
    property int fillMode: Image.PreserveAspectCrop
    property alias status: img.status
    property alias sourceSize: img.sourceSize
    property string placeholderIcon: "image"
    property bool loaded: img.status === Image.Ready

    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: Theme.card
        Icon {
            anchors.centerIn: parent
            visible: !root.loaded
            name: root.placeholderIcon; size: 32; color: Theme.textFaint
        }
    }
    Image {
        id: img
        anchors.fill: parent
        source: root.source
        asynchronous: true
        smooth: true
        mipmap: true
        fillMode: root.fillMode
        opacity: 0
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: mask
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }
        onStatusChanged: if (status === Image.Ready) opacity = 1
        Behavior on opacity { NumberAnimation { duration: Motion.fade; easing.type: Motion.easeOut } }
    }
    Item {
        id: mask
        anchors.fill: parent
        visible: false
        layer.enabled: true
        layer.smooth: true
        Rectangle { anchors.fill: parent; radius: root.radius; color: "black" }
    }
    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: "transparent"
        border.width: 1
        border.color: Theme.imageOutline
    }
}
