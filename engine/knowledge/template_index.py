class TemplateIndex:
    def __init__(self, kb4: dict):
        self._templates = list(kb4.get("templates", {}).values())

    def all(self) -> list[dict]:
        return [dict(item) for item in self._templates]

    def find_by_category(self, category: str) -> list[dict]:
        """Backward compatible: returns templates matching category (may be empty after KB4 simplification)."""
        return [dict(item) for item in self._templates if item.get("category") == category]
