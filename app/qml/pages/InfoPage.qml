import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import KirshUi 1.0
import "../"
import "../MenuModels.js" as Menus

// Страница манги. Слева обложка, справа заголовок, сведения, описание и главное действие;
// ниже — тома и главы с прогрессом. Всё, что связано с чтением, на виду сразу.
Item {
    id: page
    property var hub
    property bool active: false
    readonly property var info: backend.info
    property int tabIndex: 0
    property bool descExpanded: false
    property bool chaptersAll: false
    property var expanded: ({})

    focus: active
    Keys.onEscapePressed: if (!page.hub.anyOpen) backend.showLibrary()
    onActiveChanged: if (active) { tabIndex = 0; descExpanded = false; chaptersAll = false; expanded = ({}); scroll.contentY = 0; forceActiveFocus() }

    readonly property bool hasLocal: info.volumes.length > 0 || info.localChapters.length > 0
    readonly property var tabs: {
        var t = []
        if (info.volumes.length > 0) t.push({ label: "Тома и главы · " + info.volumes.length, key: "vol" })
        else if (info.localChapters.length > 0) t.push({ label: "Главы · " + info.localChapters.length, key: "loc" })
        if (info.chapters.length > 0) t.push({ label: "На " + info.chaptersSource + " · " + info.chapters.length, key: "web" })
        return t
    }
    readonly property string tabKey: tabs.length > tabIndex ? tabs[tabIndex].key : ""

    // ------------------------------------------------------- верхняя панель
    Item {
        id: bar
        width: parent.width
        height: 64
        z: 5
        Rectangle { anchors.fill: parent; color: Theme.alpha(Theme.bg, 0.92) }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hairline }
        AppButton {
            x: Theme.s6
            anchors.verticalCenter: parent.verticalCenter
            text: "Библиотека"
            icon: "back"
            variant: "ghost"
            onClicked: backend.showLibrary()
        }
        Row {
            anchors.right: parent.right
            anchors.rightMargin: Theme.s6
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.s2
            AppButton {
                text: "Указать ссылку"
                icon: "link"
                variant: "ghost"
                onClicked: page.hub.prompt("Ссылка на MyAnimeList",
                    "Если автоматический поиск ошибся, вставьте адрес страницы манги на myanimelist.net — данные подтянутся сами.",
                    "Ссылка", "https://myanimelist.net/manga/…", "", "Загрузить", function (v) { page.info.changeLink(v) })
            }
            IconButton { icon: "refresh"; tip: "Обновить данные"; onClicked: page.info.refresh() }
            IconButton { id: moreBtn; icon: "more"; tip: "Ещё"; onClicked: moreMenu.openAt(moreBtn, moreBtn.width - moreMenu.width, moreBtn.height + 4) }
        }
    }

    // --------------------------------------------------------------- тело
    Flickable {
        id: scroll
        y: bar.height
        width: parent.width
        height: parent.height - bar.height
        contentWidth: width
        contentHeight: body.height + Theme.s7
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        C.ScrollBar.vertical: AppScrollBar {}
        DragScroll {}

        Column {
            id: body
            x: Math.max(Theme.s6, (scroll.width - width) / 2)
            y: Theme.s5
            width: Math.min(1120, scroll.width - Theme.s6 * 2)
            spacing: Theme.s6

            // ---------------- шапка: обложка + сведения
            Row {
                id: hero
                width: parent.width
                spacing: Theme.s6
                readonly property bool narrow: parent.width < 760

                RoundedImage {
                    id: cover
                    width: hero.narrow ? 180 : 264
                    height: Math.round(width * 1.42)
                    radius: Theme.rLg
                    source: page.info.cover
                    sourceSize: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)
                }

                Column {
                    width: hero.width - cover.width - hero.spacing
                    spacing: Theme.s4

                    Column {
                        width: parent.width
                        spacing: Theme.s2
                        Text {
                            width: parent.width
                            text: page.info.title
                            wrapMode: Text.WordWrap
                            color: Theme.text
                            font.family: Theme.displayFont
                            font.pixelSize: hero.narrow ? 22 : Theme.fsDisplay
                            font.weight: Font.DemiBold
                            lineHeight: 1.1
                            Accessible.role: Accessible.Heading
                        }
                        Text {
                            visible: page.info.original !== ""
                            width: parent.width
                            text: page.info.original
                            wrapMode: Text.WordWrap
                            color: Theme.textDim
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsLead
                        }
                    }

                    // жанры
                    Flow {
                        visible: page.info.genres.length > 0
                        width: parent.width
                        spacing: Theme.s2
                        Repeater {
                            model: page.info.genres
                            delegate: Chip { required property string modelData; text: modelData; tone: "accent" }
                        }
                    }

                    // сведения одной строкой: подпись тусклая, значение обычное
                    Flow {
                        visible: page.info.meta.length > 0
                        width: parent.width
                        spacing: Theme.s5
                        Repeater {
                            model: page.info.meta
                            delegate: Row {
                                required property var modelData
                                spacing: 6
                                Text { text: modelData.label; color: Theme.textDim; font.family: Theme.uiFont; font.pixelSize: Theme.fsBody }
                                Text { text: modelData.value; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
                            }
                        }
                    }

                    // сообщение об ошибке — инструкция и действие рядом
                    Rectangle {
                        visible: page.info.banner !== ""
                        width: parent.width
                        height: bannerCol.height + Theme.s4 * 2
                        radius: Theme.rMd
                        color: Theme.alpha(Theme.warning, 0.12)
                        border.width: 1
                        border.color: Theme.alpha(Theme.warning, 0.5)
                        Column {
                            id: bannerCol
                            x: Theme.s4; y: Theme.s4
                            width: parent.width - Theme.s4 * 2
                            spacing: Theme.s3
                            Row {
                                spacing: Theme.s3
                                width: parent.width
                                Icon { name: "warning"; size: 20; stroke: 2; color: Theme.warning }
                                Text {
                                    width: parent.width - 20 - Theme.s3
                                    text: page.info.banner
                                    wrapMode: Text.WordWrap
                                    color: Theme.text
                                    font.family: Theme.uiFont
                                    font.pixelSize: Theme.fsBody
                                    lineHeight: 1.35
                                }
                            }
                            Row {
                                spacing: Theme.s2
                                AppButton { compact: true; text: "Повторить поиск"; icon: "refresh"; onClicked: page.info.refresh() }
                                AppButton {
                                    compact: true; text: "Указать ссылку"; icon: "link"; variant: "ghost"
                                    onClicked: page.hub.prompt("Ссылка на MyAnimeList", "Вставьте адрес страницы манги на myanimelist.net.",
                                        "Ссылка", "https://myanimelist.net/manga/…", "", "Загрузить", function (v) { page.info.changeLink(v) })
                                }
                            }
                        }
                    }

                    // описание
                    Column {
                        visible: page.info.description !== "" || page.info.loading
                        width: parent.width
                        spacing: Theme.s2
                        Meter { visible: page.info.loading; width: 160; indeterminate: true }
                        Text {
                            visible: page.info.loading
                            text: "Загружаю данные с MangaDex…"
                            color: Theme.textDim
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsSmall
                        }
                        Text {
                            id: desc
                            visible: page.info.description !== ""
                            width: Math.min(parent.width, 760)
                            text: page.info.description
                            textFormat: Text.RichText
                            wrapMode: Text.WordWrap
                            maximumLineCount: page.descExpanded ? 1000 : 5
                            elide: Text.ElideRight
                            color: Theme.text
                            linkColor: Theme.accent
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsBody
                            lineHeight: 1.5
                            onLinkActivated: (l) => backend.openUrl(l)
                            HoverHandler { cursorShape: desc.hoveredLink !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        }
                        AppButton {
                            visible: desc.visible && (desc.truncated || page.descExpanded)
                            compact: true
                            variant: "ghost"
                            text: page.descExpanded ? "Свернуть" : "Показать полностью"
                            icon: page.descExpanded ? "up" : "chevron-down"
                            onClicked: page.descExpanded = !page.descExpanded
                        }
                    }

                    // главное действие
                    Row {
                        spacing: Theme.s4
                        AppButton {
                            id: readBtn
                            text: page.info.readLabel
                            icon: "play"
                            variant: "primary"
                            implicitHeight: 48
                            onClicked: page.info.read()
                        }
                        Text {
                            visible: page.info.readSub !== ""
                            anchors.verticalCenter: parent.verticalCenter
                            text: page.info.readSub
                            color: Theme.textDim
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsBody
                        }
                    }

                    // статус и оценка — одна группа (8 px), отдельно от главного действия
                    Row {
                        spacing: Theme.s4
                        Chip {
                            id: statusChip
                            anchors.verticalCenter: parent.verticalCenter
                            interactive: true
                            dropdown: true
                            icon: "bookmark"
                            tone: page.info.status === "none" ? "neutral" : (page.info.status === "completed" ? "success" : page.info.status === "planned" ? "info" : page.info.status === "dropped" ? "danger" : "accent")
                            text: Menus.statusText(page.info.status)
                            onClicked: statusMenu.openAt(statusChip, 0, statusChip.height + 4)
                        }
                        Stars {
                            anchors.verticalCenter: parent.verticalCenter
                            value: page.info.rating
                            onRated: (v) => page.info.setRating(v)
                        }
                    }
                }
            }

            // ---------------- вкладки: тома / главы
            Column {
                visible: page.tabs.length > 0
                width: parent.width
                spacing: Theme.s4

                Segmented {
                    visible: page.tabs.length > 1
                    model: page.tabs
                    currentIndex: page.tabIndex
                    onActivated: (i) => page.tabIndex = i
                }
                Text {
                    visible: page.tabs.length === 1
                    text: page.tabs.length ? page.tabs[0].label : ""
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: Theme.fsTitle
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                }

                // тома
                Column {
                    visible: page.tabKey === "vol"
                    width: parent.width
                    spacing: Theme.s2
                    Repeater {
                        model: page.info.volumes
                        delegate: VolumeRow {
                            required property var modelData
                            required property int index
                            width: parent.width
                            vol: modelData
                            open: modelData.chapters.length > 0 && (page.expanded[index] !== undefined ? page.expanded[index] : modelData.current)
                            onToggled: { var m = page.expanded; m[index] = !open; page.expanded = Object.assign({}, m) }
                            onReadFile: (p) => page.info.openFile(p)
                            onReadChapter: (p, n) => page.info.openChapter(p, n)
                        }
                    }
                }
                // главы единственного файла
                Column {
                    visible: page.tabKey === "loc"
                    width: parent.width
                    spacing: Theme.s2
                    Repeater {
                        model: page.info.localChapters
                        delegate: ChapterRow {
                            required property var modelData
                            width: parent.width
                            name: modelData.name
                            onClicked: page.info.openChapter("", modelData.name)
                        }
                    }
                }
                // главы на MangaDex
                Column {
                    visible: page.tabKey === "web"
                    width: parent.width
                    spacing: 1
                    Repeater {
                        model: page.chaptersAll ? page.info.chapters : page.info.chapters.slice(0, 40)
                        delegate: Text {
                            required property var modelData
                            width: parent.width
                            text: modelData.label
                            elide: Text.ElideRight
                            color: Theme.textDim
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsBody
                            topPadding: 6; bottomPadding: 6
                        }
                    }
                    AppButton {
                        visible: !page.chaptersAll && page.info.chapters.length > 40
                        variant: "ghost"
                        text: "Показать все " + page.info.chapters.length
                        icon: "chevron-down"
                        onClicked: page.chaptersAll = true
                    }
                }
            }
        }
    }

    // -------------------------------------------------------------- меню
    ContextMenu {
        id: statusMenu
        model: {
            var m = []
            for (var i = 0; i < Menus.STATUSES.length; i++)
                m.push({ text: Menus.STATUSES[i].text, action: Menus.STATUSES[i].key, checked: Menus.STATUSES[i].key === page.info.status })
            return m
        }
        onTriggered: (item) => page.info.setStatus(item.action)
    }
    ContextMenu {
        id: moreMenu
        model: Menus.info()
        onTriggered: (item) => {
            var a = item.action, path = page.info.keyPath
            if (a === "rename") page.hub.prompt("Переименовать", "Введите новое имя. Расширение файла сохранится.", "Название", "",
                                                page.info.title, "Переименовать", function (v) { backend.renameItem(path, v) })
            else if (a === "delete") page.hub.confirm("Удалить с устройства?",
                                                     "Файлы будут удалены без возможности восстановления.\n" + path,
                                                     "Удалить", true, function () { backend.deleteItem(path) })
            else backend.itemAction(a, path)
        }
    }
}
