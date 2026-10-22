import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import KirshUi 1.0

Modal {
    id: root
    readonly property var dl: backend.downloads
    readonly property var siteValues: ["MangaLib", "Com-X.life", "ReadManga/MintManga", "MangaHub.ru", "MangaBuff"]
    readonly property var siteLabels: ["MangaLib", "Com-X", "ReadManga", "MangaHub", "MangaBuff"]
    property int siteIndex: 0
    readonly property string site: siteValues[siteIndex]
    readonly property bool isGroup: site.indexOf("ReadManga") >= 0
    property string domain: ""
    property string formatValue: "CBZ (архив)"
    readonly property var formatValues: ["CBZ (архив)", "Папки с картинками", "EPUB", "PDF"]
    // Высота, сверх которой форма прокручивается (окно приложения бывает всего 620 px).
    readonly property real maxBodyHeight: parent ? Math.max(240, parent.height - Theme.s6 * 2 - 190) : 640
    property string detectedHint: ""

    // ---- выбор глав
    readonly property var chapterModes: ["all", "one", "range", "pick"]
    property string chapterMode: "all"
    property var picked: ({})            // ключ главы -> true
    readonly property int pickedCount: Object.keys(picked).length
    property int lastPicked: -1          // для выделения диапазона с Shift
    readonly property var chapters: dl.chapterList
    readonly property bool listFresh: dl.chapterListUrl !== "" && dl.chapterListUrl === urlField.text.trim()

    function loadChapters() {
        picked = ({})
        lastPicked = -1
        dl.loadChapters(site, urlField.text)
    }
    function setAll(on) {
        var p = {}
        if (on) for (var i = 0; i < chapters.length; i++) p[chapters[i].key] = true
        picked = p
        lastPicked = -1
    }
    // Клик — отметить/снять главу; Shift+клик — то же для всех глав от предыдущего клика.
    function toggleChapter(index, shift) {
        var p = Object.assign({}, picked)
        var on = !p[chapters[index].key]
        var from = (shift && lastPicked >= 0) ? Math.min(lastPicked, index) : index
        var to = (shift && lastPicked >= 0) ? Math.max(lastPicked, index) : index
        for (var i = from; i <= to; i++) {
            if (on) p[chapters[i].key] = true
            else delete p[chapters[i].key]
        }
        picked = p
        lastPicked = index
    }
    function selection() {
        var keys = []
        if (chapterMode === "pick")
            for (var i = 0; i < chapters.length; i++) if (picked[chapters[i].key]) keys.push(chapters[i].key)
        return { mode: chapterMode, one: oneField.text, from: fromField.text, to: toField.text, keys: keys }
    }

    title: dl.running ? "Скачивание" : "Скачать мангу"
    subtitle: dl.running ? "Не закрывайте программу до завершения загрузки." : "Найдите мангу по названию или вставьте ссылку — сайт определится сам."
    panelWidth: 760
    dismissible: !dl.running

    onOpened: {
        // Если в буфере обмена лежит ссылка на поддерживаемый сайт — подставляем её сразу.
        if (!dl.running && urlField.text.trim() === "") {
            var link = dl.clipboardLink()
            if (link !== "") {
                urlField.text = link
                detectedHint = "Ссылка вставлена из буфера обмена. " + detectedHint
            }
        }
        dl.checkAuth(site, domain)
        urlField.focusInput()
    }
    onSiteIndexChanged: dl.checkAuth(site, domain)

    function pick(item) {
        urlField.text = item.url
        detectedHint = "Выбрано: «" + item.title + "» на " + item.siteLabel
    }

    property bool wasRunning: false
    Connections {
        target: root.dl
        function onRunningChanged() {
            if (root.dl.running) root.wasRunning = true
            else if (root.wasRunning) { root.wasRunning = false; root.close() }
        }
    }

    // ------------------------------------------------ форма
    Flickable {
        visible: !root.dl.running
        width: parent.width
        height: Math.min(form.implicitHeight, root.maxBodyHeight)
        contentWidth: width
        contentHeight: form.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: form
            width: parent.width
            spacing: Theme.s4
            bottomPadding: Theme.s5

            // поиск по сайтам
            Column {
                width: parent.width
                spacing: Theme.s2
                Text { text: "Поиск по сайтам"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold }
                Row {
                    width: parent.width
                    spacing: Theme.s2
                    SearchField {
                        id: searchField
                        width: parent.width - findBtn.width - Theme.s2
                        placeholder: "Название манги — ищем на всех сайтах сразу"
                        onAccepted: root.dl.search(text)
                    }
                    AppButton {
                        id: findBtn
                        text: "Найти"
                        icon: "search"
                        busy: root.dl.searchBusy
                        enabled: searchField.text.trim().length >= 2
                        onClicked: root.dl.search(searchField.text)
                    }
                }
                Text {
                    visible: root.dl.searchNote !== ""
                    width: parent.width
                    text: root.dl.searchNote
                    wrapMode: Text.WordWrap
                    color: Theme.textDim
                    font.family: Theme.uiFont
                    font.pixelSize: Theme.fsCaption
                }
                ListView {
                    id: results
                    visible: count > 0
                    width: parent.width
                    height: 236
                    orientation: ListView.Horizontal
                    spacing: Theme.s3
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: root.dl.searchResults
                    delegate: Item {
                        id: card
                        required property var modelData
                        readonly property bool selected: urlField.text.trim() === modelData.url
                        width: 120
                        height: results.height
                        Accessible.role: Accessible.Button
                        Accessible.name: modelData.title + ", " + modelData.siteLabel

                        RoundedImage {
                            id: cover
                            width: parent.width
                            height: 170
                            radius: Theme.rMd
                            source: card.modelData.cover
                            sourceSize: Qt.size(240, 340)
                        }
                        Rectangle {   // рамка наведения/выбора
                            anchors.fill: cover
                            radius: Theme.rMd
                            color: "transparent"
                            border.width: 2
                            border.color: card.selected ? Theme.accent : (hover.hovered ? Theme.alpha(Theme.accent, 0.6) : "transparent")
                        }
                        Rectangle {   // сайт
                            x: Theme.s1 + 2; y: Theme.s1 + 2
                            height: 20
                            width: siteTxt.implicitWidth + Theme.s2 * 2
                            radius: 10
                            color: Theme.alpha(Theme.sunken, 0.86)
                            Text {
                                id: siteTxt
                                anchors.centerIn: parent
                                text: card.modelData.siteLabel
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                            }
                        }
                        Text {
                            id: titleTxt
                            y: cover.height + Theme.s2
                            width: parent.width
                            text: card.modelData.title
                            maximumLineCount: 2
                            wrapMode: Text.WordWrap
                            elide: Text.ElideRight
                            color: card.selected ? Theme.accent : Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                        }
                        Text {
                            anchors.top: titleTxt.bottom
                            anchors.topMargin: 2
                            width: parent.width
                            text: card.modelData.subtitle || ""
                            elide: Text.ElideRight
                            color: Theme.textDim
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsCaption
                        }
                        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: root.pick(card.modelData) }
                    }
                }
            }

            Field {
                id: urlField
                width: parent.width
                label: "Ссылка на мангу"
                placeholder: "https://mangalib.me/ru/manga/…"
                showPaste: true
                onTextChanged: {
                    var r = root.dl.detect(text)
                    if (r.site !== "") {
                        var i = root.siteValues.indexOf(r.site)
                        if (i >= 0 && i !== root.siteIndex) { root.siteIndex = i }
                        root.detectedHint = "Определён сайт: " + root.siteLabels[Math.max(0, i)]
                    } else root.detectedHint = ""
                    if (r.domain !== "" && root.isGroup) { root.domain = r.domain; root.dl.checkAuth(root.site, root.domain) }
                    // Список глав относится к прежней ссылке — сбрасываем его и отметки.
                    if (root.dl.chapterListUrl !== "" && text.trim() !== root.dl.chapterListUrl) {
                        root.dl.clearChapters()
                        root.picked = ({})
                        root.lastPicked = -1
                    }
                }
                help: root.detectedHint
            }

            Column {
                width: parent.width
                spacing: Theme.s2
                Text { text: "Сайт"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold }
                Segmented {
                    width: parent.width
                    stretch: true
                    model: root.siteLabels.map(function (l) { return { label: l } })
                    currentIndex: root.siteIndex
                    onActivated: (i) => root.siteIndex = i
                }
            }

            // статус входа
            Rectangle {
                width: parent.width
                height: authRow.implicitHeight + Theme.s4 * 2
                radius: Theme.rMd
                color: Theme.card
                border.width: 1
                border.color: Theme.hairline
                readonly property var st: root.dl.authStatus
                readonly property color tone: st.kind === "ok" ? Theme.success : st.kind === "error" ? Theme.danger
                                            : st.kind === "warn" ? Theme.warning : Theme.info
                Row {
                    id: authRow
                    x: Theme.s4
                    y: Theme.s4
                    width: parent.width - Theme.s4 * 2
                    spacing: Theme.s3
                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: parent.parent.st.kind === "ok" ? "check" : parent.parent.st.kind === "info" ? "info" : "warning"
                        size: 20; stroke: 2; color: parent.parent.tone
                    }
                    Text {
                        width: parent.width - 20 - authBtn.width - Theme.s3 * 2
                        anchors.verticalCenter: parent.verticalCenter
                        text: parent.parent.st.text || ""
                        wrapMode: Text.WordWrap
                        color: Theme.text
                        font.family: Theme.uiFont
                        font.pixelSize: Theme.fsSmall
                        lineHeight: 1.3
                    }
                    AppButton {
                        id: authBtn
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        text: parent.parent.st.button || "Войти в аккаунт"
                        busy: root.dl.authBusy
                        onClicked: root.dl.startAuth(root.site, root.domain)
                    }
                }
            }

            Row {
                visible: root.isGroup
                spacing: Theme.s2
                AppButton {
                    text: "Импортировать куки из файла"
                    icon: "upload"
                    variant: "ghost"
                    compact: true
                    onClicked: root.dl.importCookies(root.domain)
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.domain !== "" ? "для " + root.domain : "сначала вставьте ссылку"
                    color: Theme.textDim
                    font.family: Theme.uiFont
                    font.pixelSize: Theme.fsSmall
                }
            }

            // выбор глав
            Column {
                width: parent.width
                spacing: Theme.s2
                Text { text: "Главы"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold }
                Segmented {
                    width: parent.width
                    stretch: true
                    model: [{ label: "Все" }, { label: "Одна глава" }, { label: "Диапазон" }, { label: "Выбрать", icon: "list" }]
                    currentIndex: Math.max(0, root.chapterModes.indexOf(root.chapterMode))
                    onActivated: (i) => {
                        root.chapterMode = root.chapterModes[i]
                        if (root.chapterMode === "pick" && !root.listFresh && !root.dl.chapterListBusy
                                && urlField.text.trim() !== "")
                            root.loadChapters()
                    }
                }

                Field {
                    id: oneField
                    visible: root.chapterMode === "one"
                    width: Math.min(parent.width, 260)
                    label: "Номер главы"
                    placeholder: "например, 12 или 7.5"
                }

                Row {
                    visible: root.chapterMode === "range"
                    width: parent.width
                    spacing: Theme.s3
                    Field {
                        id: fromField
                        width: (parent.width - Theme.s3) / 2
                        label: "С главы"
                        placeholder: "с первой"
                    }
                    Field {
                        id: toField
                        width: (parent.width - Theme.s3) / 2
                        label: "По главу"
                        placeholder: "до последней"
                    }
                }

                Column {
                    visible: root.chapterMode === "pick"
                    width: parent.width
                    spacing: Theme.s2

                    Row {
                        width: parent.width
                        spacing: Theme.s2
                        AppButton {
                            compact: true
                            icon: "refresh"
                            text: root.listFresh ? "Обновить список" : "Загрузить список глав"
                            busy: root.dl.chapterListBusy
                            enabled: urlField.text.trim() !== "" && !root.dl.chapterListBusy
                            onClicked: root.loadChapters()
                        }
                        AppButton {
                            visible: root.listFresh && root.chapters.length > 0
                            compact: true
                            variant: "ghost"
                            text: "Отметить все"
                            onClicked: root.setAll(true)
                        }
                        AppButton {
                            visible: root.listFresh && root.pickedCount > 0
                            compact: true
                            variant: "ghost"
                            text: "Снять все"
                            onClicked: root.setAll(false)
                        }
                    }

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        color: Theme.textDim
                        font.family: Theme.uiFont
                        font.pixelSize: Theme.fsCaption
                        text: urlField.text.trim() === "" ? "Сначала выберите мангу в поиске или вставьте ссылку."
                            : root.listFresh && root.chapters.length > 0 && !root.dl.chapterListBusy
                              ? "Отмечено: " + root.pickedCount + " из " + root.chapters.length
                                + ". Shift+клик отмечает все главы между двумя кликами."
                            : root.dl.chapterListNote
                    }

                    Rectangle {
                        visible: root.listFresh && root.chapters.length > 0
                        width: parent.width
                        height: Math.min(264, chapterView.contentHeight + 8)
                        radius: Theme.rMd
                        color: Theme.card
                        border.width: 1
                        border.color: Theme.hairline

                        ListView {
                            id: chapterView
                            anchors.fill: parent
                            anchors.margins: 4
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            model: root.listFresh ? root.chapters : []
                            C.ScrollBar.vertical: AppScrollBar {}
                            delegate: Rectangle {
                                id: chRow
                                required property var modelData
                                required property int index
                                readonly property bool on: root.picked[modelData.key] === true
                                width: ListView.view.width
                                height: 32
                                radius: Theme.rSm
                                color: area.containsMouse ? Theme.alpha(Theme.accent, 0.08) : "transparent"
                                Accessible.role: Accessible.CheckBox
                                Accessible.name: modelData.label
                                Accessible.checked: on

                                Rectangle {
                                    id: box
                                    x: Theme.s2
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 18; height: 18
                                    radius: 4
                                    color: chRow.on ? Theme.accent : "transparent"
                                    border.width: chRow.on ? 0 : 1.5
                                    border.color: Theme.controlBorder
                                    Icon {
                                        anchors.centerIn: parent
                                        visible: chRow.on
                                        name: "check"
                                        size: 14; stroke: 2.5
                                        color: Theme.ink
                                    }
                                }
                                Text {
                                    x: box.x + box.width + Theme.s3
                                    width: parent.width - x - Theme.s3
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: chRow.modelData.label
                                    elide: Text.ElideRight
                                    color: chRow.on ? Theme.text : Theme.textDim
                                    font.family: Theme.uiFont
                                    font.pixelSize: Theme.fsSmall
                                }
                                MouseArea {
                                    id: area
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: (mouse) => root.toggleChapter(chRow.index, (mouse.modifiers & Qt.ShiftModifier) !== 0)
                                }
                            }
                        }
                    }
                }

                Text {
                    visible: root.chapterMode !== "pick"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    color: Theme.textDim
                    font.family: Theme.uiFont
                    font.pixelSize: Theme.fsCaption
                    text: root.chapterMode === "one" ? "Скачается только глава с этим номером (если она есть в нескольких томах — из каждого)."
                        : root.chapterMode === "range" ? "Обе границы включаются. Пустое поле — без ограничения с этой стороны."
                        : "Скачиваются все главы манги."
                }
            }

            Column {
                width: parent.width
                spacing: Theme.s2
                Text { text: "Формат сохранения"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold }
                Segmented {
                    width: parent.width
                    stretch: true
                    model: [{ label: "CBZ", icon: "library" }, { label: "Папки", icon: "folder" },
                            { label: "EPUB", icon: "book" }, { label: "PDF", icon: "file" }]
                    currentIndex: Math.max(0, root.formatValues.indexOf(root.formatValue))
                    onActivated: (i) => root.formatValue = root.formatValues[i]
                }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    color: Theme.textDim
                    font.family: Theme.uiFont
                    font.pixelSize: Theme.fsCaption
                    text: root.formatValue === "EPUB" ? "EPUB собирается после скачивания: одна книга с оглавлением по главам. Подходит для читалок и телефонов."
                        : root.formatValue === "PDF" ? "PDF собирается после скачивания: одна страница файла — одна страница манги."
                        : root.formatValue === "CBZ (архив)" ? "Архив комикса — открывается в этой программе и большинстве читалок."
                        : "Каждая глава — отдельная папка с картинками."
                }
            }
        }
    }

    // ------------------------------------------------ прогресс
    Column {
        visible: root.dl.running
        width: parent.width
        spacing: Theme.s3
        bottomPadding: Theme.s5
        Text {
            width: parent.width
            text: root.dl.statusText
            color: Theme.text
            font.family: Theme.uiFont
            font.pixelSize: Theme.fsBody
            wrapMode: Text.WordWrap
        }
        Meter { width: parent.width; value: root.dl.percent / 100; thickness: 6 }
        Row {
            width: parent.width
            Text {
                width: parent.width - 60
                text: root.dl.chapterText
                elide: Text.ElideRight
                color: Theme.textDim
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsSmall
            }
            Text {
                width: 60
                horizontalAlignment: Text.AlignRight
                text: root.dl.percent + "%"
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsSmall
                font.weight: Font.DemiBold
            }
        }
    }

    footer: [
        AppButton { visible: !root.dl.running; text: "Отмена"; variant: "ghost"; onClicked: root.close() },
        AppButton {
            visible: !root.dl.running
            text: "Скачать"
            icon: "download"
            variant: "primary"
            enabled: urlField.text.trim() !== "" && (root.chapterMode !== "pick" || (root.listFresh && root.pickedCount > 0))
            onClicked: root.dl.start(root.site, urlField.text, root.formatValue, root.selection())
        },
        AppButton { visible: root.dl.running; text: "Остановить"; variant: "danger"; onClicked: root.dl.cancel() }
    ]
}
