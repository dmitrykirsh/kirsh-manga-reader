from collections import OrderedDict


class BoundedCache(OrderedDict):
    """Словарь-кэш с ограничением количества элементов.
    Когда лимит превышен, самый старый добавленный элемент удаляется автоматически."""
    def __init__(self, max_size=200, *args, **kwargs):
        self.max_size = max_size
        super().__init__(*args, **kwargs)
        while len(self) > self.max_size:
            oldest_key = next(iter(self))
            del self[oldest_key]

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.max_size:
            oldest_key = next(iter(self))
            del self[oldest_key]


COVER_CACHE = BoundedCache(max_size=200)
