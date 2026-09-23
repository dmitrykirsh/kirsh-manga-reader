import QtQuick 2.15
import QtQuick.Controls.Basic 2.15 as C
import QtQuick.Window 2.15
import KirshUi 1.0
import "dialogs"
import "pages"

C.ApplicationWindow {
    id: win
    visible: true
    width: 1350
    height: 850
    minimumWidth: 960
    minimumHeight: 620
    title: "Kirsh Manga Reader"
    color: Theme.bg

    // палитра, клавиатурный режим и «смена темы» приходят из Python
    Binding { target: Theme; property: "p"; value: backend.palette }
    Binding { target: Theme; property: "keyboardNav"; value: backend.keyboardNav }
    Binding { target: Theme; property: "switching"; value: backend.themeSwitching }
    Binding { target: Motion; property: "enabled"; value: backend.motionEnabled }

    readonly property bool inReader: backend.page === "reader"

    Item {
        id: shell
        anchors.fill: parent
        // Пока открыт любой Modal/ContextMenu (см. PopupTracker), фон полностью отключён для
        // ввода — enabled:false проверяется движком Qt Quick до того, как событие вообще
        // дойдёт до какого-либо обработчика (TapHandler/MouseArea), поэтому клик по пункту
        // меню/настроек больше не может «провалиться» на карточку или кнопку рейки под ним.
        // Сами попапы физически не являются потомками shell (Qt Quick Controls всегда рисует
        // Popup через оверлей окна), так что это их не касается.
        enabled: !PopupTracker.anyOpen

        // ---- контент; слева резервируем место под свёрнутую рейку
        Item {
            id: content
            x: win.inReader ? 0 : rail.collapsedW
            width: parent.width - x
            height: parent.height

            PageSlot {
                anchors.fill: parent
                shown: backend.page === "library"
                LibraryPage { id: libraryPage; anchors.fill: parent; hub: dialogHub }
            }
            PageSlot {
                anchors.fill: parent
                shown: backend.page === "info"
                InfoPage { id: infoPage; anchors.fill: parent; hub: dialogHub; active: backend.page === "info" }
            }
            PageSlot {
                anchors.fill: parent
                shown: backend.page === "reader"
                slide: false
                ReaderPage { id: readerPage; anchors.fill: parent; hub: dialogHub; active: backend.page === "reader" }
            }
        }

        // ---- левая рейка поверх контента (раскрывается наведением)
        NavRail {
            id: rail
            objectName: "rail"
            z: 20
            visible: !win.inReader
            height: parent.height
            version: backend.appVersion
            currentIndex: backend.tab
            items: [
                { text: "Библиотека", icon: "library" },
                { text: "Продолжить чтение", icon: "continue" },
                { text: "Завершено", icon: "done" },
                { text: "В планах", icon: "planned" }
            ]
            actions: [
                { key: "download", text: "Скачать мангу", icon: "download" },
                { key: "settings", text: "Настройки", icon: "settings", badge: backend.update.available === true }
            ]
            onItemActivated: (i) => backend.setTab(i)
            onActionTriggered: (key) => key === "download" ? dialogHub.openDownload() : dialogHub.openSettings()
        }
    }

    DialogHub { id: dialogHub; objectName: "hub"; anchors.fill: parent }
    ToastHost { id: toasts; z: 50 }
    Connections {
        target: backend
        function onToastRequested(kind, text) { toasts.show(kind, text) }
    }

    // ---- глобальные сочетания клавиш
    Shortcut { sequence: "F11"; onActivated: win.visibility = win.visibility === Window.FullScreen ? Window.Windowed : Window.FullScreen }
    Shortcut {
        sequences: ["Ctrl+F", "/"]
        enabled: backend.page === "library" && !dialogHub.anyOpen && !libraryPage.search.inputFocus
        onActivated: libraryPage.focusSearch()
    }
    Shortcut { sequence: "Ctrl+,"; onActivated: dialogHub.openSettings() }
}
