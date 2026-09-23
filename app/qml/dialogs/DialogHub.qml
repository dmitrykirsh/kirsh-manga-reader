import QtQuick 2.15
import KirshUi 1.0

// Все диалоги приложения в одном месте; страницы вызывают их функциями и не хранят свои копии.
Item {
    id: hub
    property var _confirmCb: null
    property var _promptCb: null

    function confirm(title, message, confirmText, danger, cb) {
        confirmDlg.title = title
        confirmDlg.message = message
        confirmDlg.confirmText = confirmText
        confirmDlg.danger = !!danger
        _confirmCb = cb
        confirmDlg.open()
    }
    function prompt(title, message, label, placeholder, value, confirmText, cb) {
        promptDlg.title = title
        promptDlg.message = message
        promptDlg.label = label
        promptDlg.placeholder = placeholder
        promptDlg.value = value
        promptDlg.confirmText = confirmText
        _promptCb = cb
        promptDlg.open()
    }
    function openCover(path) { coverDlg.path = path; coverDlg.open() }
    function openSettings() { settingsDlg.open() }
    function openDownload() { downloadDlg.open() }
    function closeAll() { confirmDlg.close(); promptDlg.close(); coverDlg.close(); settingsDlg.close(); downloadDlg.close() }
    readonly property bool anyOpen: confirmDlg.opened || promptDlg.opened || coverDlg.opened
                                    || settingsDlg.opened || downloadDlg.opened || authDlg.opened

    ConfirmDialog { id: confirmDlg; onConfirmed: if (hub._confirmCb) hub._confirmCb() }
    PromptDialog { id: promptDlg; onSubmitted: (v) => { if (hub._promptCb) hub._promptCb(v) } }
    CoverDialog { id: coverDlg; hub: hub }
    SettingsDialog { id: settingsDlg }
    DownloadDialog { id: downloadDlg }
    AuthDialog { id: authDlg }
}
