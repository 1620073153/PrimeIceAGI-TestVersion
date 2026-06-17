class ClusterIndex:
    def __init__(self, kb1: dict, category_index):
        self._clusters = kb1.get("clusters", {})
        self._category_index = category_index

    def get_cross_cluster_subcategories(self, cluster_key: str) -> list[str]:
        cluster = self._clusters.get(cluster_key, {})
        results: list[str] = []
        for cross_cluster in cluster.get("cross_cluster", []):
            results.extend(self._category_index.get_cluster_subcategories(cross_cluster))
        return results
