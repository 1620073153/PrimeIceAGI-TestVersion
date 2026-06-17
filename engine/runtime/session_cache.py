from copy import deepcopy


class SessionCache:
    def __init__(self):
        self._items: dict[str, dict] = {}

    @classmethod
    def seed(cls, items: dict[str, dict] | None = None):
        cache = cls()
        cache._items = deepcopy(items or {})
        return cache

    def put(self, session_id: str, payload: dict, merge: bool = False) -> None:
        if merge and session_id in self._items:
            item = deepcopy(self._items[session_id])
            item.update(deepcopy(payload))
            self._items[session_id] = item
            return

        self._items[session_id] = deepcopy(payload)

    def get(self, session_id: str) -> dict | None:
        item = self._items.get(session_id)
        return deepcopy(item) if item is not None else None

    def snapshot(self) -> dict[str, dict]:
        return deepcopy(self._items)
