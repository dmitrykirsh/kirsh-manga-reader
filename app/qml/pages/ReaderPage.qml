import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import QtQuick.Window 2.15
import KirshUi 1.0

// Читалка. Страница занимает всё окно; панели появляются при движении мыши и уходят сами.
// Клавиатурные действия (листание, прокрутка) не анимируются: они повторяются сотни раз.
Item {
    id: page
    property var hub
    property bool active: false
    readonly property var rd: backend.reader
    readonly property bool webtoon: rd.webtoon

    property real zoom: 1
    property bool barsVisible: true
    property bool overlayOpen: chaptersDlg.opened || (hub ? hub.anyOpen : false)
    property real wheelAccum: 0

    // Резерв под верхнюю/нижнюю панель: страница вписывается между ними, а не под них —
    // панели больше не перекрывают саму мангу, когда они видимы.
    property real topInset: barsVisible ? topBar.height : 0
    property real botInset: barsVisible ? bottomBar.height : 0
    Behavior on topInset { NumberAnimation { duration: page.barsVisible ? Motion.base : Motion.exit; easing.type: Motion.easeOut } }
    Behavior on botInset { NumberAnimation { duration: page.barsVisible ? Motion.base : Motion.exit; easing.type: Motion.easeOut } }

    focus: active
    clip: true

    Rectangle { anchors.fill: parent; color: Theme.sunken }

    // ------------------------------------------------------------------ сервис
    function pokeBars() {
        barsVisible = true
        idleTimer.restart()
    }
    Timer {
        id: idleTimer
        interval: 2600
        onTriggered: if (!topBar.hovered && !bottomBar.hovered && !page.overlayOpen && !Theme.keyboardNav) page.barsVisible = false
    }
    function clampZoom(z) { return Math.max(1, Math.min(webtoon ? 3 : 5, z)) }
    function resetZoom() { zoom = 1; paged.contentX = 0; paged.contentY = 0 }
    function zoomAt(px, py, target) {
        target = clampZoom(target)
        if (target === zoom) return
        if (webtoon) { zoom = target; return }
        var cx = paged.contentX + px, cy = paged.contentY + py
        var ratio = target / zoom
        zoom = target
        paged.contentX = Math.max(0, Math.min(paged.contentWidth - paged.width, cx * ratio - px))
        paged.contentY = Math.max(0, Math.min(paged.contentHeight - paged.height, cy * ratio - py))
    }
    function scrollBy(dy) {
        var v = webtoon ? wt : paged
        v.contentY = Math.max(0, Math.min(v.contentHeight - v.height, v.contentY + dy))
    }
    function flip(d) {
        if (d > 0 && rd.page >= rd.pageCount - 1) return
        rd.jumpTo(rd.page + d)
    }

    Connections {
        target: page.rd
        function onGenChanged() { page.zoom = 1; paged.contentX = 0; paged.contentY = 0; page.pokeBars() }
        function onPageChanged() { if (!page.webtoon) { paged.contentX = 0; paged.contentY = 0 } }
        function onPageJump(p) { if (page.webtoon) { wtGuard.restart(); wt.positionViewAtIndex(p, ListView.Beginning) } }
        function onWebtoonChanged() { page.zoom = 1; if (page.rd.webtoon) Qt.callLater(function () { wt.positionViewAtIndex(page.rd.page, ListView.Beginning) }) }
        function onSizesChanged() { if (page.webtoon) Qt.callLater(function () { wt.positionViewAtIndex(page.rd.page, ListView.Beginning) }) }
    }
    onActiveChanged: if (active) { zoom = 1; barsVisible = true; idleTimer.restart(); forceActiveFocus() }
    // Клавиши листания живут на page: после закрытия любого попапа/модалки (не только
    // оглавления) возвращаем фокус сюда, иначе ←/→ перестают долистывать до следующего клика.
    onOverlayOpenChanged: if (!overlayOpen) forceActiveFocus()

    // ------------------------------------------------------------ постраничный режим
    Flickable {
        id: paged
        anchors.fill: parent
        visible: !page.webtoon
        contentWidth: Math.max(width, cur.width)
        contentHeight: Math.max(height, cur.height)
        interactive: page.zoom > 1.001
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        readonly property real fit: cur.implicitWidth > 0 ? Math.min(width / cur.implicitWidth, (height - page.topInset - page.botInset) / cur.implicitHeight) : 1

        // Ctrl+колесо = масштаб. Обработчик — прямой потомок Flickable, а не соседний с ним
        // элемент: иначе Flickable иногда перехватывает wheel-событие себе первым.
        WheelHandler {
            acceptedModifiers: Qt.ControlModifier
            onWheel: (e) => page.zoomAt(point.position.x, point.position.y, page.zoom * (e.angleDelta.y > 0 ? 1.12 : 1 / 1.12))
        }

        // Предыдущая страница остаётся на экране, пока загружается новая — без мигания.
        Image {
            id: ghost
            property url shown
            source: shown
            x: cur.x; y: cur.y; width: cur.width; height: cur.height
            visible: cur.status !== Image.Ready
            fillMode: Image.PreserveAspectFit
            smooth: true
        }
        Image {
            id: cur
            source: page.active && !page.webtoon && page.rd.pageCount > 0 ? "image://page/" + page.rd.gen + "/" + page.rd.page : ""
            asynchronous: true
            cache: true
            smooth: true
            mipmap: true
            fillMode: Image.PreserveAspectFit
            width: implicitWidth * paged.fit * page.zoom
            height: implicitHeight * paged.fit * page.zoom
            x: Math.max(0, (paged.contentWidth - width) / 2)
            y: Math.max(page.topInset, page.topInset + (paged.contentHeight - page.topInset - page.botInset - height) / 2)
            onStatusChanged: if (status === Image.Ready) ghost.shown = source
        }
        // прогрев соседних страниц (кэш QML): листание без задержки
        Image { source: page.active && !page.webtoon && page.rd.page + 1 < page.rd.pageCount ? "image://page/" + page.rd.gen + "/" + (page.rd.page + 1) : ""; asynchronous: true; cache: true; visible: false }
        Image { source: page.active && !page.webtoon && page.rd.page + 2 < page.rd.pageCount ? "image://page/" + page.rd.gen + "/" + (page.rd.page + 2) : ""; asynchronous: true; cache: true; visible: false }
        Image { source: page.active && !page.webtoon && page.rd.page > 0 ? "image://page/" + page.rd.gen + "/" + (page.rd.page - 1) : ""; asynchronous: true; cache: true; visible: false }

        Meter {
            visible: cur.status === Image.Loading && ghost.shown == ""
            anchors.centerIn: parent
            width: 96
            indeterminate: true
        }
    }

    // ------------------------------------------------------------ режим ленты
    ListView {
        id: wt
        // Вьюпорт, а не content-margin: topMargin/bottomMargin у ListView резервируют место
        // только у самого начала/конца всего списка, а не на текущей позиции прокрутки — в
        // середине главы панели всё равно перекрывали бы картинку. Сужаем сам видимый прямоугольник.
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: page.topInset
        anchors.bottom: parent.bottom
        anchors.bottomMargin: page.botInset
        visible: page.webtoon
        model: page.webtoon ? page.rd.pageCount : 0
        cacheBuffer: height * 2
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        // Колонка ≤ 960 px считается внутри delegate (см. imgW); тут только ширина вьюпорта.
        contentWidth: width
        flickableDirection: Flickable.AutoFlickDirection
        reuseItems: true
        property bool guard: false
        Timer { id: wtGuard; interval: 250 }

        // Ctrl+колесо = масштаб (см. пояснение в paged выше — тот же приём для этого Flickable).
        WheelHandler {
            acceptedModifiers: Qt.ControlModifier
            onWheel: (e) => page.zoomAt(point.position.x, point.position.y, page.zoom * (e.angleDelta.y > 0 ? 1.12 : 1 / 1.12))
        }

        onContentYChanged: {
            if (!page.webtoon || wtGuard.running || count === 0) return
            var i = indexAt(contentX + width / 2, contentY + height * 0.35)
            if (i >= 0) page.rd.setPage(i)
        }

        delegate: Item {
            id: wtItem
            required property int index
            readonly property var sz: page.rd.sizes.length > index ? page.rd.sizes[index] : [800, 1136]
            // Делегат = вся ширина вьюпорта (без капа и без участия в горизонтальном скролле);
            // колонка ≤ 960 px и центрирование — чисто внутри него, обычным anchor'ом
            // parent↔child, без обращений к contentWidth/wt через границу Flickable.
            readonly property real imgW: Math.min(wt.width, 960) * page.zoom
            width: wt.width
            height: Math.round(imgW * sz[1] / sz[0])
            Image {
                width: wtItem.imgW
                height: parent.height
                anchors.horizontalCenter: parent.horizontalCenter
                source: page.active && page.webtoon ? "image://page/" + page.rd.gen + "/" + wtItem.index : ""
                sourceSize.width: Math.round(wtItem.imgW * Screen.devicePixelRatio)
                asynchronous: true
                cache: false
                smooth: true
                fillMode: Image.Stretch
            }
            Rectangle { anchors.fill: parent; color: Theme.card; visible: false }
        }
        C.ScrollBar.vertical: AppScrollBar {}
    }

    // ------------------------------------------------------------ ввод
    HoverHandler { onPointChanged: page.pokeBars() }
    WheelHandler {
        acceptedModifiers: Qt.NoModifier
        enabled: !page.webtoon && page.zoom <= 1.001
        onWheel: (e) => {
            page.wheelAccum += e.angleDelta.y
            if (Math.abs(page.wheelAccum) >= 120) {
                page.flip(page.wheelAccum > 0 ? -1 : 1)
                page.wheelAccum = 0
            }
        }
    }
    // зоны нажатия: левая треть — назад, правая — вперёд, середина — показать/скрыть панели
    TapHandler {
        acceptedButtons: Qt.LeftButton
        enabled: !page.webtoon
        onSingleTapped: (p) => {
            page.forceActiveFocus()
            if (page.zoom > 1.001) { page.barsVisible = !page.barsVisible; return }
            var x = p.position.x / page.width
            if (x < 0.3) page.flip(-1)
            else if (x > 0.7) page.flip(1)
            else page.barsVisible = !page.barsVisible
        }
        onDoubleTapped: (p) => page.zoomAt(p.position.x, p.position.y, page.zoom > 1.001 ? 1 : 2.4)
    }
    TapHandler {
        acceptedButtons: Qt.LeftButton
        enabled: page.webtoon
        onSingleTapped: { page.forceActiveFocus(); page.barsVisible = !page.barsVisible }
    }
    TapHandler { acceptedButtons: Qt.RightButton; onTapped: page.resetZoom() }
    TapHandler { acceptedButtons: Qt.BackButton; onTapped: backend.closeReader() }

    Keys.onPressed: (e) => {
        var step = Math.round(page.height * 0.8)
        switch (e.key) {
        case Qt.Key_Escape:
            if (!page.overlayOpen) backend.closeReader()
            break
        case Qt.Key_Left: case Qt.Key_A: case Qt.Key_PageUp:
            if (page.webtoon) page.scrollBy(-step); else page.flip(-1)
            break
        case Qt.Key_Right: case Qt.Key_D: case Qt.Key_PageDown: case Qt.Key_Space:
            if (page.webtoon) page.scrollBy(step); else page.flip(1)
            break
        case Qt.Key_Up: page.scrollBy(-Math.round(step / 3)); break
        case Qt.Key_Down: page.scrollBy(Math.round(step / 3)); break
        case Qt.Key_Home: page.rd.jumpTo(0); break
        case Qt.Key_End: page.rd.jumpTo(page.rd.pageCount - 1); break
        case Qt.Key_M: page.rd.toggleWebtoon(); break
        case Qt.Key_C: if (page.rd.chapters.length > 0) chaptersDlg.open(); break
        case Qt.Key_Plus: case Qt.Key_Equal: page.zoomAt(page.width / 2, page.height / 2, page.zoom * 1.2); break
        case Qt.Key_Minus: page.zoomAt(page.width / 2, page.height / 2, page.zoom / 1.2); break
        case Qt.Key_0: page.resetZoom(); break
        default: return
        }
        e.accepted = true
    }

    // ------------------------------------------------------------ верхняя панель
    Rectangle {
        id: topBar
        readonly property bool hovered: topHover.hovered
        width: parent.width
        height: 64
        y: page.barsVisible ? 0 : -height
        opacity: page.barsVisible ? 1 : 0
        color: Theme.alpha(Theme.panel, 0.94)
        Behavior on y { NumberAnimation { duration: page.barsVisible ? Motion.base : Motion.exit; easing.type: Motion.easeOut } }
        Behavior on opacity { NumberAnimation { duration: page.barsVisible ? Motion.base : Motion.exit } }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hairline }
        HoverHandler { id: topHover }

        AppButton {
            x: Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            text: "Назад"
            icon: "back"
            variant: "ghost"
            onClicked: backend.closeReader()
        }
        Column {
            x: 132
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(80, parent.width - 132 - tools.width - Theme.s6)
            spacing: 1
            Text {
                width: parent.width
                text: page.rd.title
                elide: Text.ElideRight
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsLead
                font.weight: Font.DemiBold
                Accessible.role: Accessible.Heading
            }
            Text {
                visible: text !== ""
                width: parent.width
                text: page.rd.chapterName !== "" ? page.rd.chapterName : page.rd.volumeName
                elide: Text.ElideRight
                color: Theme.textDim
                font.family: Theme.uiFont
                font.pixelSize: Theme.fsSmall
            }
        }
        Row {
            id: tools
            anchors.right: parent.right
            anchors.rightMargin: Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.s2
            AppButton {
                visible: page.zoom > 1.001
                anchors.verticalCenter: parent.verticalCenter
                compact: true
                text: Math.round(page.zoom * 100) + "%"
                icon: "zoom"
                variant: "secondary"
                onClicked: page.resetZoom()
            }
            IconButton { icon: "list"; tip: "Оглавление (C)"; visible: page.rd.chapters.length > 0; onClicked: chaptersDlg.open() }
            Segmented {
                anchors.verticalCenter: parent.verticalCenter
                // Не встаёт в фокус по табу/клику — иначе перехватывает ←/→ у читалки (см. AppSlider выше).
                activeFocusOnTab: false
                model: [{ label: "Страницы", icon: "page" }, { label: "Лента", icon: "rows" }]
                currentIndex: page.webtoon ? 1 : 0
                onActivated: (i) => page.rd.setWebtoonMode(i === 1)
            }
            IconButton { icon: "info"; tip: "Страница манги"; onClicked: page.rd.goInfo() }
            IconButton { icon: "keyboard"; tip: "Сочетания клавиш"; checked: page.rd.hintVisible; onClicked: page.rd.toggleHint() }
            IconButton {
                icon: "maximize"
                tip: "Полный экран (F11)"
                onClicked: { var w = Window.window; w.visibility = w.visibility === Window.FullScreen ? Window.Windowed : Window.FullScreen }
            }
        }
    }

    // ------------------------------------------------------------ нижняя панель
    Rectangle {
        id: bottomBar
        readonly property bool hovered: bottomHover.hovered
        width: parent.width
        height: 64
        y: page.barsVisible ? parent.height - height : parent.height
        opacity: page.barsVisible ? 1 : 0
        color: Theme.alpha(Theme.panel, 0.94)
        Behavior on y { NumberAnimation { duration: page.barsVisible ? Motion.base : Motion.exit; easing.type: Motion.easeOut } }
        Behavior on opacity { NumberAnimation { duration: page.barsVisible ? Motion.base : Motion.exit } }
        Rectangle { width: parent.width; height: 1; color: Theme.hairline }
        HoverHandler { id: bottomHover }

        IconButton {
            id: prevBtn
            x: Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            icon: "chevron-left"; tip: "Предыдущая страница"
            enabled: page.rd.page > 0
            onClicked: page.flip(-1)
        }
        AppSlider {
            x: prevBtn.x + prevBtn.width + Theme.s3
            width: parent.width - x - nextBtn.width - pageChip.width - Theme.s3 * 2 - Theme.s4 * 2
            anchors.verticalCenter: parent.verticalCenter
            // Не встаёт в фокус по табу/клику: иначе она перехватывает ←/→/↑/↓ и листание
            // страниц клавиатурой перестаёт работать, пока фокус не вернётся на читалку.
            activeFocusOnTab: false
            label: "Страница"
            from: 1
            to: Math.max(2, page.rd.pageCount)
            value: page.rd.page + 1
            onMoved: (v) => page.rd.jumpTo(Math.round(v) - 1)
        }
        IconButton {
            id: nextBtn
            anchors.right: pageChip.left
            anchors.rightMargin: Theme.s3
            anchors.verticalCenter: parent.verticalCenter
            icon: "chevron-right"; tip: "Следующая страница"
            enabled: page.rd.page < page.rd.pageCount - 1
            onClicked: page.flip(1)
        }
        AppButton {
            id: pageChip
            anchors.right: parent.right
            anchors.rightMargin: Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            compact: true
            text: (page.rd.page + 1) + " / " + page.rd.pageCount
            onClicked: page.hub.prompt("Перейти к странице", "Введите номер от 1 до " + page.rd.pageCount + ".", "Номер страницы", "", String(page.rd.page + 1), "Перейти",
                                       function (v) { var n = parseInt(v); if (!isNaN(n)) page.rd.jumpTo(Math.max(1, Math.min(page.rd.pageCount, n)) - 1) })
        }
    }

    // ------------------------------------------------------------ следующая глава
    AppButton {
        visible: page.rd.chapterEnd && page.rd.hasNext
        anchors.right: parent.right
        anchors.rightMargin: Theme.s5
        anchors.bottom: parent.bottom
        anchors.bottomMargin: (page.barsVisible ? 64 : 0) + Theme.s5
        implicitHeight: 48
        text: "Следующая глава"
        icon: "arrow-right"
        variant: "primary"
        onClicked: page.rd.nextChapter()
    }

    // ------------------------------------------------------------ подсказка при первом чтении
    Rectangle {
        id: hint
        visible: page.rd.hintVisible
        anchors.right: parent.right
        anchors.rightMargin: Theme.s5
        y: (page.barsVisible ? topBar.height : 0) + Theme.s4
        width: 340
        height: hintCol.height + Theme.s5 * 2
        radius: Theme.rLg
        color: Theme.elevated
        border.width: 1
        border.color: Theme.controlBorder
        Column {
            id: hintCol
            x: Theme.s5; y: Theme.s5
            width: parent.width - Theme.s5 * 2
            spacing: Theme.s3
            Text { text: "Как листать"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
            Repeater {
                model: [
                    ["← →, колесо", "листать"],
                    ["Ctrl + колесо", "масштаб"],
                    ["Двойной щелчок", "приблизить"],
                    ["M", "страницы / лента"],
                    ["Esc", "назад"]
                ]
                delegate: Row {
                    required property var modelData
                    spacing: Theme.s3
                    Text { width: 130; text: modelData[0]; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold }
                    Text { text: modelData[1]; color: Theme.textDim; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall }
                }
            }
            Row {
                spacing: Theme.s2
                AppButton { compact: true; text: "Понятно"; variant: "primary"; onClicked: page.rd.dismissHint() }
                AppButton { compact: true; text: "Скрыть"; variant: "ghost"; onClicked: page.rd.hideHintOnce() }
            }
        }
    }

    // ------------------------------------------------------------ оглавление
    Modal {
        id: chaptersDlg
        title: "Оглавление"
        subtitle: page.rd.title
        panelWidth: 480
        onClosed: page.forceActiveFocus()
        Column {
          width: parent.width
          ListView {
            id: chList
            width: parent.width
            height: Math.min(contentHeight, 420)
            clip: true
            model: page.rd.chapters
            boundsBehavior: Flickable.StopAtBounds
            C.ScrollBar.vertical: AppScrollBar {}
            onVisibleChanged: if (visible) {
                for (var i = 0; i < page.rd.chapters.length; i++) {
                    var m = page.rd.chapters[i]
                    // Оглавление серии (главы — отдельные файлы) несёт свой признак current;
                    // внутренняя разбивка одного файла — как раньше, по совпадению имени.
                    var isCur = m.path !== undefined ? m.current === true : m.name === page.rd.chapterName
                    if (isCur) { positionViewAtIndex(i, ListView.Center); break }
                }
            }
            delegate: ChapterRow {
                required property var modelData
                width: chList.width - 8
                name: modelData.name
                detail: modelData.path !== undefined ? modelData.detail : ("стр. " + (modelData.page + 1))
                current: modelData.path !== undefined ? modelData.current === true : modelData.name === page.rd.chapterName
                onClicked: {
                    chaptersDlg.close()
                    if (modelData.path !== undefined) page.rd.openChapter(modelData.path)
                    else page.rd.jumpTo(modelData.page)
                }
            }
          }
          Item { width: 1; height: Theme.s5 }
        }
    }
}
