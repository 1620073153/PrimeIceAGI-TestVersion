class SuccessPatternIndex:
    def __init__(self, derived: dict):
        self._patterns = derived

    def get_neighbor_subcategories(self, strategy_tags: list[str]) -> list[str]:
        results: list[str] = []
        for tag in strategy_tags:
            results.extend(self._patterns.get(tag, []))
        deduped: list[str] = []
        seen: set[str] = set()
        for item in results:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped
