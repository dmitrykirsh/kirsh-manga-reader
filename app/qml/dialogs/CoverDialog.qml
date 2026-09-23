import QtQuick 2.15
import KirshUi 1.0

// Выбор источника своей обложки.
Modal {
    id: root
    property string path: ""
    property var hub

    title: "Изменить обложку"
    subtitle: "Откуда взять изображение?"
    panelWidth: 480

    Column {
        width: parent.width
        spacing: Theme.s2
        bottomPadding: Theme.s5
        Repeater {
            model: [
                { icon: "image", text: "Файл на компьютере", detail: "PNG, JPG, WEBP или BMP", key: "file" },
                { icon: "link", text: "Ссылка на картинку", detail: "Адрес изображения в интернете", key: "url" },
                { icon: "download", text: "Обложка с MangaDex", detail: "Найдётся по названию", key: "mangadex" }
            ]
            delegate: Item {
                required property var modelData
                width: parent.width
                height: 64
                scale: tap.pressed ? Motion.pressScale : 1
                Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: modelData.text
                Rectangle {
                    anchors.fill: parent
                    radius: Theme.rMd
                    color: hov.hovered ? Theme.elevated : Theme.card
                    border.width: 1
                    border.color: hov.hovered ? Theme.controlBorder : Theme.hairline
                }
                Icon { x: Theme.s4; anchors.verticalCenter: parent.verticalCenter; name: modelData.icon; size: 22; stroke: 2; color: Theme.accent }
                Column {
                    x: 60
                    anchors.verticalCenter: parent.verticalCenter
                    Text { text: modelData.text; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
                    Text { text: modelData.detail; color: Theme.textDim; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall }
                }
                HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
                TapHandler { id: tap; onTapped: pick(modelData.key) }
                Keys.onPressed: (e) => { if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { pick(modelData.key); e.accepted = true } }
                FocusRing { baseRadius: Theme.rMd }
            }
        }
    }

    function pick(key) {
        var p = root.path
        root.close()
        if (key === "file") backend.coverFromFile(p)
        else if (key === "mangadex") backend.coverFromMangadex(p)
        else hub.prompt("Обложка по ссылке", "", "Адрес изображения", "https://…", "", "Загрузить", function (url) { backend.coverFromUrl(p, url) })
    }
}
