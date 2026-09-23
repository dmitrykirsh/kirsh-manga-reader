import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import KirshUi 1.0

Modal {
    id: root
    title: "Настройки"
    panelWidth: 640

    Item {
        width: parent.width
        height: Math.min(scroll.contentHeight, 560)
        implicitHeight: height

        Flickable {
            id: scroll
            anchors.fill: parent
            contentHeight: col.height + Theme.s5
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            C.ScrollBar.vertical: AppScrollBar {}
            DragScroll {}

            Column {
                id: col
                width: parent.width - Theme.s3
                spacing: Theme.s5

                // ---- библиотека
                Column {
                    width: parent.width
                    spacing: Theme.s2
                    SectionTitle { text: "Библиотека" }
                    Rectangle {
                        width: parent.width
                        height: 56
                        radius: Theme.rMd
                        color: Theme.card
                        border.width: 1
                        border.color: Theme.hairline
                        Icon { x: Theme.s4; anchors.verticalCenter: parent.verticalCenter; name: "folder"; size: 20; color: Theme.accent }
                        Text {
                            x: 52
                            width: parent.width - 52 - 160
                            anchors.verticalCenter: parent.verticalCenter
                            text: backend.rootDir !== "" ? backend.rootDir : "Папка не выбрана"
                            elide: Text.ElideMiddle
                            color: backend.rootDir !== "" ? Theme.text : Theme.textDim
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsBody
                        }
                        AppButton {
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.s3
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Выбрать папку"
                            compact: true
                            onClicked: backend.pickRoot()
                        }
                    }
                    Row {
                        spacing: Theme.s2
                        AppButton { text: "Пересканировать"; icon: "refresh"; variant: "ghost"; compact: true; onClicked: { backend.rescan() } }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Нужно, если вы добавили файлы вне программы."
                            color: Theme.textDim
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsSmall
                        }
                    }
                }

                // ---- тема
                Column {
                    width: parent.width
                    spacing: Theme.s3
                    SectionTitle { text: "Тема оформления" }
                    Flow {
                        width: parent.width
                        spacing: 10
                        Repeater {
                            model: backend.themes
                            delegate: Item {
                                id: sw
                                required property var modelData
                                readonly property bool current: modelData.name === backend.themeName
                                width: 112; height: 104
                                activeFocusOnTab: true
                                scale: swTap.pressed ? Motion.pressScale : 1
                                Behavior on scale { NumberAnimation { duration: Motion.press; easing.type: Motion.easeOut } }
                                Accessible.role: Accessible.RadioButton
                                Accessible.name: modelData.name
                                Accessible.checked: current
                                // Мини-палитра: холст → поверхность → возвышение, с акцентной точкой —
                                // наглядно показывает глубину слоёв темы, а не один плоский цвет.
                                Rectangle {
                                    id: face
                                    width: parent.width; height: 72
                                    radius: Theme.rMd
                                    color: sw.modelData.bg
                                    border.width: sw.current ? 2 : 1
                                    border.color: sw.current ? Theme.accent : Theme.hairline
                                    clip: true
                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        width: parent.width * 0.42
                                        color: sw.modelData.panel
                                    }
                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 10
                                        anchors.bottom: parent.bottom
                                        anchors.bottomMargin: 10
                                        width: parent.width * 0.42 - 20
                                        height: 16
                                        radius: 5
                                        color: sw.modelData.elevated
                                    }
                                    Rectangle {
                                        anchors.right: parent.right
                                        anchors.rightMargin: 10
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 30; height: 30; radius: 15
                                        color: sw.modelData.accent
                                    }
                                    Icon {
                                        visible: sw.current
                                        anchors.right: parent.right; anchors.top: parent.top
                                        anchors.margins: 6
                                        name: "check"; size: 16; stroke: 2.5; color: Theme.accent
                                    }
                                }
                                Text {
                                    y: 78
                                    width: parent.width
                                    horizontalAlignment: Text.AlignHCenter
                                    text: sw.modelData.name
                                    color: sw.current ? Theme.text : Theme.textDim
                                    font.family: Theme.uiFont
                                    font.pixelSize: Theme.fsSmall
                                    font.weight: sw.current ? Font.DemiBold : Font.Normal
                                    elide: Text.ElideRight
                                }
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                TapHandler { id: swTap; onTapped: backend.setTheme(sw.modelData.name) }
                                Keys.onPressed: (e) => { if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { backend.setTheme(sw.modelData.name); e.accepted = true } }
                                FocusRing { baseRadius: Theme.rMd; anchors.fill: face }
                            }
                        }
                    }
                }

                // ---- интеграции
                Column {
                    width: parent.width
                    spacing: Theme.s2
                    SectionTitle { text: "Интеграции" }
                    Rectangle {
                        width: parent.width
                        height: toggle.implicitHeight + Theme.s4 * 2
                        radius: Theme.rMd
                        color: Theme.card
                        border.width: 1
                        border.color: Theme.hairline
                        Toggle {
                            id: toggle
                            x: Theme.s4
                            width: parent.width - Theme.s4 * 2
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Интеграция с MangaDex"
                            description: "Автопоиск обложки, описания и глав на MangaDex при открытии страницы манги. При отключении данные можно указать вручную ссылкой на MyAnimeList."
                            checked: backend.mangadexEnabled
                            onToggled: (v) => backend.setMangadexEnabled(v)
                        }
                    }
                }

                // ---- прогресс
                Column {
                    width: parent.width
                    spacing: Theme.s2
                    SectionTitle { text: "Прогресс чтения" }
                    Text {
                        width: parent.width
                        text: "Перенесите прогресс на другое устройство: экспортируйте файл и импортируйте его там. Пути хранятся относительно папки с мангой."
                        wrapMode: Text.WordWrap
                        color: Theme.textDim
                        font.family: Theme.uiFont
                        font.pixelSize: Theme.fsSmall
                        lineHeight: 1.35
                    }
                    Flow {
                        width: parent.width
                        spacing: Theme.s2
                        AppButton { text: "Экспортировать"; icon: "upload"; onClicked: backend.exportProgress() }
                        AppButton { text: "Импортировать и дополнить"; icon: "download"; onClicked: backend.importProgress(false) }
                        AppButton { text: "Импортировать и заменить"; icon: "download"; variant: "danger"; onClicked: backend.importProgress(true) }
                    }
                }

                // ---- обновления
                Column {
                    width: parent.width
                    spacing: Theme.s2
                    SectionTitle { text: "Обновления" }
                    Rectangle {
                        visible: backend.update.available === true
                        width: parent.width
                        height: 64
                        radius: Theme.rMd
                        color: Theme.soft(Theme.accent)
                        border.width: 1
                        border.color: Theme.alpha(Theme.accent, 0.5)
                        Text {
                            x: Theme.s4
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Доступна версия " + backend.update.version
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsBody
                            font.weight: Font.DemiBold
                        }
                        AppButton {
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.s3
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Открыть страницу релиза"
                            icon: "external"
                            variant: "primary"
                            compact: true
                            onClicked: backend.openUpdate()
                        }
                    }
                    Row {
                        spacing: Theme.s3
                        AppButton { text: "Проверить обновления"; icon: "refresh"; onClicked: backend.checkUpdates(true) }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Установлена версия " + backend.appVersion
                            color: Theme.textDim
                            font.family: Theme.uiFont
                            font.pixelSize: Theme.fsSmall
                        }
                    }
                }

                // ---- справка
                Column {
                    width: parent.width
                    spacing: Theme.s2
                    SectionTitle { text: "Как читать" }
                    Repeater {
                        model: [
                            ["← →, колесо мыши", "Листать страницы"],
                            ["Ctrl + колесо", "Масштаб (и в режиме ленты)"],
                            ["Двойной щелчок", "Приблизить в точку; ещё раз — вернуть"],
                            ["Правая кнопка", "Сбросить масштаб"],
                            ["M", "Переключить страницы и ленту"],
                            ["F11", "Полный экран"],
                            ["Esc или боковая кнопка мыши", "Назад"]
                        ]
                        delegate: Row {
                            required property var modelData
                            width: col.width
                            spacing: Theme.s3
                            Rectangle {
                                width: 200; height: 28; radius: Theme.rXs
                                color: Theme.card; border.width: 1; border.color: Theme.hairline
                                Text { anchors.centerIn: parent; text: modelData[0]; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: Theme.fsSmall }
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData[1]
                                color: Theme.textDim
                                font.family: Theme.uiFont
                                font.pixelSize: Theme.fsSmall
                            }
                        }
                    }
                }
            }
        }
    }
    footer: [ AppButton { text: "Готово"; variant: "primary"; onClicked: root.close() } ]

    component SectionTitle: Text {
        color: Theme.text
        font.family: Theme.uiFont
        font.pixelSize: Theme.fsBody
        font.weight: Font.DemiBold
    }
}
