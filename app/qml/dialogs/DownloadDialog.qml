import QtQuick 2.15
import KirshUi 1.0

Modal {
    id: root
    readonly property var dl: backend.downloads
    readonly property var siteValues: ["MangaLib", "Com-X.life", "ReadManga/MintManga", "MangaHub.ru"]
    readonly property var siteLabels: ["MangaLib", "Com-X", "ReadManga", "MangaHub"]
    property int siteIndex: 0
    readonly property string site: siteValues[siteIndex]
    readonly property bool isGroup: site.indexOf("ReadManga") >= 0
    property string domain: ""
    property string formatValue: "CBZ (архив)"
    property string detectedHint: ""

    title: dl.running ? "Скачивание" : "Скачать мангу"
    subtitle: dl.running ? "Не закрывайте программу до завершения загрузки." : "Вставьте ссылку на страницу манги — сайт определится сам."
    panelWidth: 620
    dismissible: !dl.running

    onOpened: { dl.checkAuth(site, domain); urlField.focusInput() }
    onSiteIndexChanged: dl.checkAuth(site, domain)

    property bool wasRunning: false
    Connections {
        target: root.dl
        function onRunningChanged() {
            if (root.dl.running) root.wasRunning = true
            else if (root.wasRunning) { root.wasRunning = false; root.close() }
        }
    }

    // ------------------------------------------------ форма
    Column {
        visible: !root.dl.running
        width: parent.width
        spacing: Theme.s4
        bottomPadding: Theme.s5

        Field {
            id: urlField
            width: parent.width
            label: "Ссылка на мангу"
            placeholder: "https://mangalib.me/ru/manga/…"
            onTextChanged: {
                var r = root.dl.detect(text)
                if (r.site !== "") {
                    var i = root.siteValues.indexOf(r.site)
                    if (i >= 0 && i !== root.siteIndex) { root.siteIndex = i }
                    root.detectedHint = "Определён сайт: " + root.siteLabels[Math.max(0, i)]
                } else root.detectedHint = ""
                if (r.domain !== "" && root.isGroup) { root.domain = r.domain; root.dl.checkAuth(root.site, root.domain) }
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

        Column {
            width: parent.width
            spacing: Theme.s2
            Text { text: "Формат сохранения"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold }
            Segmented {
                model: [{ label: "CBZ-архив", icon: "library" }, { label: "Папка с картинками", icon: "folder" }]
                currentIndex: root.formatValue === "CBZ (архив)" ? 0 : 1
                onActivated: (i) => root.formatValue = i === 0 ? "CBZ (архив)" : "Папки с картинками"
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
            enabled: urlField.text.trim() !== ""
            onClicked: root.dl.start(root.site, urlField.text, root.formatValue)
        },
        AppButton { visible: root.dl.running; text: "Остановить"; variant: "danger"; onClicked: root.dl.cancel() }
    ]
}
