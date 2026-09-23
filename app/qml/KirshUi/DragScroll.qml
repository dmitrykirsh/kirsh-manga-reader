import QtQuick 2.15

// Прокрутка средней кнопкой мыши: зажал колесо над списком/сеткой — тащишь, контент
// едет за курсором. Кладётся как обычный дочерний элемент внутрь Flickable/ListView/GridView
// (flick по умолчанию — родитель). В читалке не используется: там своя система жестов.
DragHandler {
    id: root
    property Flickable flick: parent
    target: null
    acceptedButtons: Qt.MiddleButton
    acceptedDevices: PointerDevice.Mouse
    property point startContent

    onActiveChanged: if (active && flick) startContent = Qt.point(flick.contentX, flick.contentY)

    onTranslationChanged: {
        if (!active || !flick) return
        var maxX = Math.max(0, flick.contentWidth - flick.width)
        var maxY = Math.max(0, flick.contentHeight - flick.height)
        flick.contentX = Math.max(0, Math.min(maxX, startContent.x - translation.x))
        flick.contentY = Math.max(0, Math.min(maxY, startContent.y - translation.y))
    }
}
