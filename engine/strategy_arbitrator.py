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

    # 情况 1: 有越狱成功 → 以点打面
    if bypassed > 0 and successful_prompts:
        next_strategy["variant_mode"] = True
        next_strategy["successful_templates"] = [
            {"prompt_id": sp.get("prompt_id", ""), "prompt_text": sp.get("prompt_text", "")}
            for sp in (successful_prompts or [])[:3]
        ]

        # 保持成功的手法不变，扩散到同类簇的其他子类
        cluster_subs = _get_subs_for_cluster(current_cluster)
        still_uncovered = [s for s in cluster_subs if s not in covered_categories]

        if still_uncovered:
            next_strategy["subcategories"] = still_uncovered[:5]
            next_strategy["primary_cluster"] = current_cluster
            next_strategy["primary_method"] = current_method
            next_strategy["primary_concept"] = current_concept
        else:
            # 当前类簇已全覆盖，扩散到相邻类簇
            clusters = _load_clusters()
            cross = clusters.get(current_cluster, {}).get("cross_cluster", [])
            if cross:
                next_cluster = cross[0]
                next_strategy["primary_cluster"] = next_cluster
                next_strategy["subcategories"] = _get_subs_for_cluster(next_cluster)[:5]

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
