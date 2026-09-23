"""Фоновые задачи с возвратом результата в главный поток (через сигнал QThread)."""

import logging

from PyQt6.QtCore import QThread, pyqtSignal

_alive = set()


class Task(QThread):
    done = pyqtSignal(object, object)  # (result, error)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn(), None)
        except Exception as e:  # noqa: BLE001 — любую ошибку отдаём вызывающему
            logging.exception("Фоновая задача завершилась ошибкой")
            self.done.emit(None, e)


def run_async(fn, callback, parent=None):
    """Выполняет fn() в потоке, затем в главном потоке вызывает callback(result, error)."""
    t = Task(fn, parent)
    _alive.add(t)

    def finish(result, error):
        _alive.discard(t)
        callback(result, error)
        t.deleteLater()

    t.done.connect(finish)
    t.start()
    return t
