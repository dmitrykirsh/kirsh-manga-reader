"""Небольшая обвязка для QObject-контроллеров, которые читает QML."""

from PyQt6.QtCore import QObject, pyqtProperty


class Bag(QObject):
    """Хранилище значений + метод set(), который эмитит <name>Changed только при изменении."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._v = {}

    def get(self, name, default=None):
        return self._v.get(name, default)

    def set(self, name, value):
        if name in self._v and self._v[name] == value:
            return False
        self._v[name] = value
        sig = getattr(self, f"{name}Changed", None)
        if sig is not None:
            sig.emit()
        return True


def P(type_, name, notify, default=None):
    """pyqtProperty, читающий значение из Bag._v."""
    return pyqtProperty(type_, lambda self: self._v.get(name, default), notify=notify)
