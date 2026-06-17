from copy import deepcopy


class SessionStore:
    def __init__(self):
        self._items: dict[str, dict] = {}

    @classmethod
    def seed(cls, items: dict[str, dict] | None = None):
        store = cls()
        store._items = deepcopy(items or {})
        return store

    def upsert(self, session_id: str, payload: dict, merge: bool = False) -> None:
        if merge and session_id in self._items:
            item = deepcopy(self._items[session_id])
            item.update(deepcopy(payload))
            self._items[session_id] = item
            return

        current = deepcopy(payload)
        current.setdefault("session_id", session_id)
        self._items[session_id] = current

    def get(self, session_id: str) -> dict | None:
        item = self._items.get(session_id)
        return deepcopy(item) if item is not None else None

    def all(self) -> list[dict]:
        return [deepcopy(item) for item in self._items.values()]

    def snapshot(self) -> dict[str, dict]:
        return deepcopy(self._items)
