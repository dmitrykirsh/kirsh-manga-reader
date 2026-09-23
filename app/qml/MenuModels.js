.pragma library

var STATUSES = [
    { key: "none", text: "Без статуса" },
    { key: "reading", text: "Читаю" },
    { key: "completed", text: "Прочитано" },
    { key: "planned", text: "В планах" },
    { key: "dropped", text: "Брошено" }
]

function statusText(key) {
    for (var i = 0; i < STATUSES.length; i++) if (STATUSES[i].key === key) return STATUSES[i].text
    return "Без статуса"
}

// Меню карточки: корень → «Статус» / «Оценка» открывают вложенные списки в том же окне.
function root(status, rating, isFolder) {
    return [
        { text: "Статус: " + statusText(status), icon: "bookmark", action: "level:status", keepOpen: true },
        { text: rating > 0 ? "Оценка: " + rating + " из 5" : "Оценка: не выбрана", icon: "star", action: "level:rating", keepOpen: true },
        { separator: true },
        { text: "Сбросить прогресс", icon: "refresh", action: "reset" },
        { text: "Отметить прочитанным", icon: "check", action: "mark_read" },
        { separator: true },
        { text: "Изменить обложку…", icon: "image", action: "cover" },
        { text: "Удалить свою обложку", icon: "close", action: "remove_cover" },
        { separator: true },
        { text: "Показать в проводнике", icon: "folder", action: "open_folder" },
        { text: isFolder ? "Переименовать папку…" : "Переименовать…", icon: "edit", action: "rename" },
        { separator: true },
        { text: "Удалить с устройства…", icon: "trash", action: "delete", danger: true }
    ]
}

function statusList(status) {
    var m = [{ text: "Назад", icon: "chevron-left", action: "level:root", keepOpen: true }, { separator: true }]
    for (var i = 0; i < STATUSES.length; i++)
        m.push({ text: STATUSES[i].text, action: "status:" + STATUSES[i].key, checked: STATUSES[i].key === status })
    return m
}

function ratingList(rating) {
    var m = [{ text: "Назад", icon: "chevron-left", action: "level:root", keepOpen: true }, { separator: true }]
    for (var i = 5; i >= 1; i--)
        m.push({ text: i + " из 5", action: "rating:" + i, checked: rating === i })
    m.push({ text: "Без оценки", action: "rating:none", checked: !rating })
    return m
}

// Меню страницы манги (⋯)
function info() {
    return [
        { text: "Сбросить прогресс", icon: "refresh", action: "reset" },
        { text: "Отметить прочитанным", icon: "check", action: "mark_read" },
        { separator: true },
        { text: "Показать в проводнике", icon: "folder", action: "open_folder" },
        { text: "Переименовать…", icon: "edit", action: "rename" },
        { separator: true },
        { text: "Удалить с устройства…", icon: "trash", action: "delete", danger: true }
    ]
}
