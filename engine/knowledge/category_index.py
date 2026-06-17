class CategoryIndex:
    def __init__(self, kb1: dict):
        self._categories = kb1.get("categories", {})

    def get_cluster_subcategories(self, cluster_key: str) -> list[str]:
        cluster = self._categories.get(cluster_key, {})
        subcategories = cluster.get("subcategories", {})
        return list(subcategories.keys())
