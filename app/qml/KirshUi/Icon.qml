import QtQuick 2.15
import KirshUi 1.0

// Контурная иконка (image://icon). Толщина штриха согласована с весом текста рядом:
// 1.5 — для обычного (400), 2 — для полужирного (600). Заливка = «активно».
Item {
    id: root
    property string name: ""
    property color color: Theme.text
    property int size: 20
    property real stroke: 1.5
    property bool filled: false

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    Image {
        anchors.fill: parent
        smooth: true
        mipmap: true
        cache: true
        source: root.name === "" ? "" : "image://icon/" + root.name + "/" + Theme.hex(root.color) + "/"
                                       + root.size + "/" + root.stroke + "/" + (root.filled ? 1 : 0)
    }
}
