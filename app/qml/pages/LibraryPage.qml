import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import KirshUi 1.0
import "../"
import "../MenuModels.js" as Menus

// Экран «Библиотека» и три производных вкладки. Заголовок — единственное место с Unbounded.
Item {
    id: page
    property var hub
    property alias search: searchField

    function focusSearch() { searchField.focusInput() }
    focus: true
    Component.onCompleted: forceActiveFocus()

    // ---------------------------------------------------------------- шапка
    Item {
        id: header
        x: Theme.s6
        y: Theme.s5
        width: parent.width - Theme.s6 * 2
        height: 56

        IconButton {
            id: upBtn
            visible: backend.canGoUp
            anchors.verticalCenter: parent.verticalCenter
            icon: "back"
            tip: "На уровень вверх"
            onClicked: backend.goUp()
        }
        Column {
            x: upBtn.visible ? upBtn.width + Theme.s3 : 0
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(80, parent.width - x - controls.width - Theme.s5)
            spacing: 2
            Text {
                width: parent.width
                text: backend.title
                elide: Text.ElideRight
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: 24
                font.weight: Font.DemiBold
                lineHeight: 1.1
                Accessible.role: Accessible.Heading
            }
            Text {
                text: grid.count > 0 ? grid.count + " " + plural(grid.count) : ""
                color: Theme.textDim
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsSmall
                function plural(n) {
                    var m = n % 10, h = n % 100
                    if (m === 1 && h !== 11) return "тайтл"
                    if (m >= 2 && m <= 4 && (h < 12 || h > 14)) return "тайтла"
                    return "тайтлов"
                }
            }
        }
        Row {
            id: controls
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.s4
            Row {
                spacing: Theme.s2
                anchors.verticalCenter: parent.verticalCenter
                visible: page.width > 900
                Icon { anchors.verticalCenter: parent.verticalCenter; name: "image"; size: 18; color: Theme.textDim }
                AppSlider {
                    width: 120
                    label: "Размер обложек"
                    from: 150; to: 350; stepSize: 10
                    value: backend.cardWidth
                    onMoved: (v) => backend.setCardWidth(v)
                }
            }
            SearchField {
                id: searchField
                width: page.width > 900 ? 300 : 220
                onTextChanged: backend.setSearch(text)
                onEscaped: grid.forceActiveFocus()
            }
        }
    }

    // ------------------------------------------------------------- сетка
    GridView {
        id: grid
        x: Theme.s6 - 12
        y: header.y + header.height + Theme.s4
        width: parent.width - Theme.s6 * 2 + 24
        height: parent.height - y
        clip: true
        model: backend.library
        visible: backend.emptyKind === ""
        boundsBehavior: Flickable.StopAtBounds
        readonly property int cols: Math.max(1, Math.floor((width - 24) / (backend.cardWidth + 24)))
        cellWidth: Math.floor((width - 12) / cols)
        cellHeight: Math.round((cellWidth - 24) * 1.42) + 76 + 4
        cacheBuffer: 600
        activeFocusOnTab: true
        C.ScrollBar.vertical: AppScrollBar {}
        DragScroll {}

        opacity: backend.loading ? 0.5 : 1
        Behavior on opacity { NumberAnimation { duration: Motion.fade } }

        delegate: Item {
            id: cell
            required property int index
            required property string kind
            required property string path
            required property string name
            required property string cover
            required property real progress
            required property string status
            required property string statusLabel
            required property int rating
            width: grid.cellWidth
            height: grid.cellHeight
            MangaCard {
                x: 12
                width: parent.width - 24
                kind: cell.kind
                name: cell.name
                cover: cell.cover
                progress: cell.progress
                status: cell.status
                statusLabel: cell.statusLabel
                rating: cell.rating
                dpr: Screen.devicePixelRatio
                onOpened: backend.openEntry(cell.index)
                onMenuRequested: (mx, my) => page.openMenu(this, cell, mx, my)
            }
        }
    }

    // ------------------------------------------------- пустые состояния
    EmptyState {
        anchors.centerIn: parent
        visible: backend.emptyKind === "noRoot"
        icon: "folder"
        title: "Выберите папку с мангой"
        description: "Kirsh Manga Reader читает архивы CBZ, CBR, ZIP, RAR и папки с картинками. Укажите папку, где они лежат."
        actionText: "Выбрать папку"
        actionIcon: "folder"
        onAction: backend.pickRoot()
    }
    EmptyState {
        anchors.centerIn: parent
        visible: backend.emptyKind === "emptyFolder"
        icon: "folder"
        title: "В этой папке пока пусто"
        description: "Добавьте сюда архивы или папки с картинками либо скачайте мангу по ссылке."
        actionText: "Скачать мангу"
        actionIcon: "download"
        onAction: page.hub.openDownload()
    }
    EmptyState {
        anchors.centerIn: parent
        visible: backend.emptyKind === "emptyTab"
        icon: backend.tab === 1 ? "continue" : backend.tab === 2 ? "done" : "planned"
        title: backend.tab === 1 ? "Нет начатых манг" : backend.tab === 2 ? "Пока ничего не прочитано" : "Список планов пуст"
        description: backend.tab === 1 ? "Начните читать любую мангу — она появится здесь, чтобы вернуться к ней одним щелчком."
            : backend.tab === 2 ? "Дочитанные до конца манги собираются здесь."
            : "Откройте мангу и выберите статус «В планах» — она появится в этом списке."
        actionText: "Открыть библиотеку"
        actionIcon: "library"
        onAction: backend.setTab(0)
    }
    EmptyState {
        anchors.centerIn: parent
        visible: backend.emptyKind === "noResults"
        icon: "search"
        title: "Ничего не найдено"
        description: "Проверьте написание или поищите по части названия."
        actionText: "Сбросить поиск"
        onAction: { searchField.text = ""; searchField.focusInput() }
    }

    // --------------------------------------------------- контекстное меню
    property var menuEntry: null
    property string menuLevel: "root"
    ContextMenu {
        id: cardMenu
        model: {
            var e = page.menuEntry
            if (!e) return []
            if (page.menuLevel === "status") return Menus.statusList(e.status)
            if (page.menuLevel === "rating") return Menus.ratingList(e.rating)
            return Menus.root(e.status, e.rating, e.kind === "folder")
        }
        onClosed: page.menuLevel = "root"
        onTriggered: (item) => {
            var a = item.action
            if (a.indexOf("level:") === 0) { page.menuLevel = a.substring(6); return }
            var e = page.menuEntry
            if (a === "cover") page.hub.openCover(e.path)
            else if (a === "rename") page.hub.prompt("Переименовать", "Введите новое имя. Расширение файла сохранится.",
                                                     "Название", "", nameOf(e), "Переименовать", function (v) { backend.renameItem(e.path, v) })
            else if (a === "delete") page.hub.confirm("Удалить с устройства?",
                                                     "«" + e.name + "» будет удалено без возможности восстановления.\n" + e.path,
                                                     "Удалить", true, function () { backend.deleteItem(e.path) })
            else backend.itemAction(a, e.path)
        }
    }
    function nameOf(e) {
        var n = e.name
        return n
    }
    function openMenu(card, cell, mx, my) {
        page.menuEntry = { path: cell.path, name: cell.name, kind: cell.kind, status: cell.status, rating: cell.rating }
        page.menuLevel = "root"
        cardMenu.openAt(card, mx, my)
    }
}
