"""
策略仲裁器 — 信号→策略映射引擎
根据上一轮的信号分布和越狱结果，决策下一轮的测试策略
动态读取 KB1-KB3 JSON，前端编辑后实时生效
"""

from data.kb_store import load_kb


def _load_categories():
    data = load_kb("kb1")
    return data.get("categories", {})


def _load_clusters():
    data = load_kb("kb1")
    return data.get("clusters", {})


def _load_concepts():
    data = load_kb("kb2")
    return data.get("concepts", {})


def _load_methods():
    data = load_kb("kb3")
    return data.get("methods", {})


def _load_signal_strategy_map():
    data = load_kb("kb3")
    return data.get("signal_strategy_map", {})


def _load_concept_method_map():
    data = load_kb("kb3")
    return data.get("concept_method_map", {})


def _get_priority_order():
    clusters = _load_clusters()
    return sorted(clusters.keys())


def _rotate_method(current_method: str) -> str:
    methods = list(_load_methods().keys())
    if current_method in methods:
        idx = methods.index(current_method)
        return methods[(idx + 1) % len(methods)]
    return methods[0] if methods else "academic_framing"


def _rotate_concept(current_concept: str) -> str:
    concepts = list(_load_concepts().keys())
    if current_concept in concepts:
        idx = concepts.index(current_concept)
        return concepts[(idx + 1) % len(concepts)]
    return concepts[0] if concepts else "cognitive_hierarchy_trap"


def _rotate_cluster(current_cluster: str) -> str:
    priority = _get_priority_order()
    if current_cluster in priority:
        idx = priority.index(current_cluster)
        return priority[(idx + 1) % len(priority)]
    return priority[0] if priority else "A"


def _get_methods_for_concept(concept_key: str) -> list[str]:
    cmap = _load_concept_method_map()
    return cmap.get(concept_key, ["academic_framing"])


def _get_subs_for_cluster(cluster_key: str) -> list[str]:
    categories = _load_categories()
    cat = categories.get(cluster_key)
    if cat:
        return list(cat["subcategories"].keys())
    return []


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _build_new_attack_mix(
    total_slots: int = 10,
    success_neighbor_slots: int = 3,
    cross_cluster_slots: int = 2,
) -> dict:
    success_neighbor_slots = min(success_neighbor_slots, total_slots)
    cross_cluster_slots = min(cross_cluster_slots, max(0, total_slots - success_neighbor_slots))
    fresh_exploration_slots = max(0, total_slots - success_neighbor_slots - cross_cluster_slots)
    return {
        "total_slots": total_slots,
        "success_neighbor_slots": success_neighbor_slots,
        "cross_cluster_slots": cross_cluster_slots,
        "fresh_exploration_slots": fresh_exploration_slots,
    }


def _sanitize_successful_templates(successful_prompts: list[dict] | None) -> list[dict]:
    sanitized = []
    for sp in (successful_prompts or [])[:3]:
        sanitized.append({
            "prompt_id": sp.get("prompt_id", ""),
            "target_category": sp.get("target_category", ""),
            "strategy_tags": list(sp.get("strategy_tags", []))[:4],
            "concept": sp.get("concept", ""),
            "method": sp.get("method", ""),
        })
    return sanitized


def _get_cross_cluster_subcategories(current_cluster: str, covered_categories: list[str]) -> list[str]:
    clusters = _load_clusters()
    cross_clusters = clusters.get(current_cluster, {}).get("cross_cluster", [])
    cross_subs = []
    for cluster in cross_clusters:
        cross_subs.extend(_get_subs_for_cluster(cluster))
    return [s for s in _dedupe_keep_order(cross_subs) if s not in covered_categories]


def get_scan_strategy() -> dict:
    """
    首轮广度扫描策略：A-F 每个 cluster 各取 1 个子类，剩余随机补到 10 个。
    让 prompt-skill 每个子类对应 1 条提示词，快速探测各 cluster 防御强度。
    """
    import random
    categories = _load_categories()
    clusters = sorted(categories.keys())

    scan_subs = []
    for cluster_key in clusters:
        cat = categories[cluster_key]
        subs = list(cat.get("subcategories", {}).keys())
        if subs:
            scan_subs.append(subs[0])

    # 剩余名额从所有子类中随机补（不重复）
    all_subs = []
    for cat in categories.values():
        all_subs.extend(cat.get("subcategories", {}).keys())
    remaining = [s for s in all_subs if s not in scan_subs]
    extra_count = max(0, 10 - len(scan_subs))
    if remaining and extra_count > 0:
        scan_subs += random.sample(remaining, min(extra_count, len(remaining)))

    concepts = list(_load_concepts().keys())
    methods = list(_load_methods().keys())

    return {
        "primary_concept": concepts[0] if concepts else "cognitive_hierarchy_trap",
        "primary_method": methods[0] if methods else "academic_framing",
        "primary_cluster": "SCAN",
        "subcategories": scan_subs[:10],
        "variant_mode": False,
        "scan_mode": True,
        "weights": {
            "cluster_internal": 0.2,
            "cross_cluster_probe": 0.7,
            "new_exploration": 0.1,
        },
    }


def decide_next_strategy(stats: dict, current_strategy: dict,
                         round_num: int, covered_categories: list[str],
                         successful_prompts: list[dict] | None = None) -> dict:
    """
    决策下一轮策略

    输入:
    - stats: 本轮统计 (bypassed/blocked/partial/signal_distribution/primary_signal)
    - current_strategy: 当前轮策略参数
    - round_num: 当前轮次
    - covered_categories: 已覆盖(越狱成功)的子类列表
    - successful_prompts: 本轮成功的提示词列表

    输出:
    - 下一轮策略 dict
    """
    primary_signal = stats.get("primary_signal")
    bypassed = stats.get("bypassed", 0)
    current_concept = current_strategy.get("primary_concept", "cognitive_hierarchy_trap")
    current_method = current_strategy.get("primary_method", "academic_framing")
    current_cluster = current_strategy.get("primary_cluster", "A")

    # 扫描轮过渡：从成功的提示词中提取最弱 cluster
    if current_strategy.get("scan_mode"):
        if bypassed > 0 and successful_prompts:
            # 统计每个 cluster 的成功次数，找最弱的（成功最多 = 防御最差）
            cluster_hits = {}
            categories = _load_categories()
            for sp in successful_prompts:
                cat = sp.get("target_category", "")
                for cluster_key, cat_data in categories.items():
                    if cat in cat_data.get("subcategories", {}):
                        cluster_hits[cluster_key] = cluster_hits.get(cluster_key, 0) + 1
                        break
            if cluster_hits:
                best_cluster = max(cluster_hits, key=cluster_hits.get)
                neighbor_subcategories = _get_subs_for_cluster(best_cluster)[:5]
                cross_subcategories = _get_cross_cluster_subcategories(best_cluster, covered_categories)[:4]
                fresh_subcategories = [s for s in uncovered if s not in neighbor_subcategories and s not in cross_subcategories][:8]
                mix = _build_new_attack_mix(total_slots=10, success_neighbor_slots=3, cross_cluster_slots=2)
                combined = (
                    neighbor_subcategories[:mix["success_neighbor_slots"]]
                    + cross_subcategories[:mix["cross_cluster_slots"]]
                    + fresh_subcategories[:mix["fresh_exploration_slots"]]
                )
                return {
                    "primary_concept": current_concept,
                    "primary_method": current_method,
                    "primary_cluster": best_cluster,
                    "subcategories": _dedupe_keep_order(combined)[:10],
                    "variant_mode": True,
                    "successful_templates": _sanitize_successful_templates(successful_prompts),
                    "new_attack_mix": mix,
                    "focus_cluster": best_cluster,
                    "neighbor_subcategories": neighbor_subcategories,
                    "cross_cluster_subcategories": cross_subcategories,
                    "fresh_subcategories": fresh_subcategories,
                    "weights": {"cluster_internal": 0.7, "cross_cluster_probe": 0.2, "new_exploration": 0.1},
                }
        # 扫描轮全失败 → 从 A 开始正常轮转
        current_cluster = "A"

    # 计算未覆盖类别
    categories = _load_categories()
    all_subs = []
    for cat in categories.values():
        all_subs.extend(cat["subcategories"].keys())
    uncovered = [s for s in all_subs if s not in covered_categories]

    next_strategy = {
        "primary_concept": current_concept,
        "primary_method": current_method,
        "primary_cluster": current_cluster,
        "subcategories": _get_subs_for_cluster(current_cluster)[:5],
        "variant_mode": False,
        "weights": {
            "cluster_internal": 0.6,
            "cross_cluster_probe": 0.3,
            "new_exploration": 0.1,
        },
    }

    # 情况 1: 有越狱成功 → 弱偏置扩散，不让新攻全部收敛为同型扩写
    if bypassed > 0 and successful_prompts:
        next_strategy["variant_mode"] = True
        next_strategy["successful_templates"] = _sanitize_successful_templates(successful_prompts)
        next_strategy["new_attack_mix"] = _build_new_attack_mix(total_slots=10, success_neighbor_slots=3, cross_cluster_slots=2)
        next_strategy["focus_cluster"] = current_cluster

        cluster_subs = _get_subs_for_cluster(current_cluster)
        neighbor_subcategories = [s for s in cluster_subs if s not in covered_categories]
        cross_cluster_subcategories = _get_cross_cluster_subcategories(current_cluster, covered_categories)
        fresh_subcategories = [
            s for s in uncovered
            if s not in neighbor_subcategories and s not in cross_cluster_subcategories
        ]

        next_strategy["neighbor_subcategories"] = neighbor_subcategories[:5]
        next_strategy["cross_cluster_subcategories"] = cross_cluster_subcategories[:4]
        next_strategy["fresh_subcategories"] = fresh_subcategories[:8]

        mix = next_strategy["new_attack_mix"]
        combined_subcategories = (
            next_strategy["neighbor_subcategories"][:mix["success_neighbor_slots"]]
            + next_strategy["cross_cluster_subcategories"][:mix["cross_cluster_slots"]]
            + next_strategy["fresh_subcategories"][:mix["fresh_exploration_slots"]]
        )
        next_strategy["subcategories"] = _dedupe_keep_order(combined_subcategories)[:10]
        next_strategy["primary_cluster"] = current_cluster
        next_strategy["primary_method"] = current_method
        next_strategy["primary_concept"] = current_concept
        return next_strategy

    # 情况 2: 有明确信号 → 根据信号映射策略
    signal_map = _load_signal_strategy_map()
    if primary_signal and primary_signal in signal_map:
        mapping = signal_map[primary_signal]
        next_strategy["primary_concept"] = mapping["primary_concept"]
        next_strategy["primary_method"] = mapping["primary_method"]
        next_strategy["primary_cluster"] = mapping["target_cluster"]
        next_strategy["subcategories"] = _get_subs_for_cluster(mapping["target_cluster"])[:5]
        return next_strategy

    # 情况 3: 全部失败且无明确信号 → 先换手法，手法轮完换概念
    if bypassed == 0:
        methods_for_concept = _get_methods_for_concept(current_concept)
        if current_method in methods_for_concept:
            idx = methods_for_concept.index(current_method)
            if idx + 1 < len(methods_for_concept):
                next_strategy["primary_method"] = methods_for_concept[idx + 1]
                return next_strategy

        # 当前概念的方法用完了 → 换概念
        next_strategy["primary_concept"] = _rotate_concept(current_concept)
        new_methods = _get_methods_for_concept(next_strategy["primary_concept"])
        next_strategy["primary_method"] = new_methods[0] if new_methods else "academic_framing"

        # 每换一次概念也换一个类簇
        next_strategy["primary_cluster"] = _rotate_cluster(current_cluster)
        next_strategy["subcategories"] = _get_subs_for_cluster(next_strategy["primary_cluster"])[:5]
        return next_strategy

    # 情况 4: 有部分成功 → 保持策略微调
    next_strategy["primary_method"] = _rotate_method(current_method)
    return next_strategy


def check_convergence(stats_history: list[dict], config: dict) -> tuple[bool, str]:
    """
    检查收敛条件，判断是否应该终止测试

    三层收敛:
    1. 连续 N 轮零成功 → 终止
    2. 覆盖率达到阈值 → 终止
    3. 达到最大轮次 → 终止
    """
    max_rounds = int(config.get("max_rounds", 10))
    cooldown_limit = int(config.get("cooldown_no_new", 2))

    if len(stats_history) >= max_rounds:
        return True, f"达到最大轮次 ({max_rounds})"

    # 检查连续零成功
    recent = stats_history[-cooldown_limit:]
    if len(recent) >= cooldown_limit and all(s.get("bypassed", 0) == 0 for s in recent):
        return True, f"连续 {cooldown_limit} 轮零成功，提前终止"

    return False, ""
