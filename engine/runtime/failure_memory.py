from copy import deepcopy


class FailureMemory:
    def __init__(self):
        self._items: list[dict] = []

    @classmethod
    def seed(cls, items: list[dict] | None = None):
        memory = cls()
        memory._items = deepcopy(items or [])
        return memory

    def add(self, payload: dict) -> None:
        self._items.append(deepcopy(payload))

    def latest(self, limit: int | None = None) -> list[dict]:
        items = self._items if limit is None else self._items[-limit:]
        return deepcopy(items)

    def snapshot(self) -> list[dict]:
        return deepcopy(self._items)
