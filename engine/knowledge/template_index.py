class TemplateIndex:
    def __init__(self, kb4: dict):
        self._templates = list(kb4.get("templates", {}).values())

    def find_by_category(self, category: str) -> list[dict]:
        return [dict(item) for item in self._templates if item.get("category") == category]
