"""
策略仲裁器 — 信号→策略映射引擎
根据上一轮的信号分布和越狱结果，决策下一轮的测试策略
动态读取 KB1-KB3 JSON，前端编辑后实时生效
"""

import random
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


def _expand_subcategories(base_list: list[str], total_slots: int, covered_categories: list[str] | None = None) -> list[str]:
    """
    将子类列表扩展到 total_slots 个。
    - total_slots <= len(base_list): 直接截断
    - total_slots > len(base_list): 优先补充未覆盖的，再循环复用已有的
    """
    if not base_list:
        categories = _load_categories()
        for cat in categories.values():
            base_list.extend(cat.get("subcategories", {}).keys())
        base_list = _dedupe_keep_order(base_list)

    if total_slots <= len(base_list):
        return base_list[:total_slots]

    covered = set(covered_categories or [])
    uncovered_extras = [s for s in base_list if s not in covered and s not in base_list[:len(base_list)]]

    result = list(base_list)
    cycle_pool = list(base_list)
    idx = 0
    while len(result) < total_slots:
        result.append(cycle_pool[idx % len(cycle_pool)])
        idx += 1

    return result[:total_slots]


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


def _ensure_cross_cluster_filled(cross_subs: list[str], n_cross: int, current_cluster: str, covered_categories: list[str]) -> list[str]:
    """保证跨簇名额被填满：不足时从全局子类（排除当前簇）中随机补足"""
    import random
    result = list(cross_subs[:n_cross])
    if len(result) >= n_cross:
        return result
    current_cluster_subs = set(_get_subs_for_cluster(current_cluster))
    existing = set(result)
    categories = _load_categories()
    all_subs = []
    for cat in categories.values():
        all_subs.extend(cat.get("subcategories", {}).keys())
    extra = [s for s in all_subs if s not in current_cluster_subs and s not in existing and s not in covered_categories]
    random.shuffle(extra)
    result.extend(extra[:n_cross - len(result)])
    return result


def get_scan_strategy(total_slots: int = 10) -> dict:
    """
    首轮广度扫描策略：A-F 每个 cluster 各取子类，总量匹配 total_slots。
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

    all_subs = []
    for cat in categories.values():
        all_subs.extend(cat.get("subcategories", {}).keys())
    remaining = [s for s in all_subs if s not in scan_subs]
    extra_count = max(0, total_slots - len(scan_subs))
    if remaining and extra_count > 0:
        scan_subs += random.sample(remaining, min(extra_count, len(remaining)))

    scan_subs = _expand_subcategories(scan_subs, total_slots)

    concepts = list(_load_concepts().keys())
    methods = list(_load_methods().keys())

    concept_pool = random.sample(concepts, min(5, len(concepts))) if concepts else ["cognitive_hierarchy_trap"]
    method_pool = random.sample(methods, min(5, len(methods))) if methods else ["academic_framing"]

    return {
        "primary_concept": concept_pool[0],
        "primary_method": method_pool[0],
        "primary_cluster": "SCAN",
        "subcategories": scan_subs,
        "concept_pool": concept_pool,
        "method_pool": method_pool,
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
                         successful_prompts: list[dict] | None = None,
                         total_slots: int = 10,
                         consecutive_zero_rounds: int = 0) -> dict:
    """
    决策下一轮策略

    输入:
    - stats: 本轮统计 (bypassed/blocked/partial/signal_distribution/primary_signal)
    - current_strategy: 当前轮策略参数
    - round_num: 当前轮次
    - covered_categories: 已覆盖(越狱成功)的子类列表
    - successful_prompts: 本轮成功的提示词列表
    - total_slots: 需要的子类总数（= effective_concurrency）

    输出:
    - 下一轮策略 dict，含 subcategories / concept_pool / method_pool
    """
    primary_signal = stats.get("primary_signal")
    bypassed = stats.get("bypassed", 0)
    current_concept = current_strategy.get("primary_concept", "cognitive_hierarchy_trap")
    current_method = current_strategy.get("primary_method", "academic_framing")
    current_cluster = current_strategy.get("primary_cluster", "A")

    # 扫描轮过渡：从成功的提示词中提取最弱 cluster
    if current_strategy.get("scan_mode"):
        if bypassed > 0 and successful_prompts:
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
                all_subs_temp = []
                for cat_data in categories.values():
                    all_subs_temp.extend(cat_data.get("subcategories", {}).keys())
                uncovered = [s for s in all_subs_temp if s not in covered_categories]

                neighbor_subcategories = _get_subs_for_cluster(best_cluster)
                cross_subcategories = _get_cross_cluster_subcategories(best_cluster, covered_categories)
                fresh_subcategories = [s for s in uncovered if s not in neighbor_subcategories and s not in cross_subcategories]

                ratio_neighbor = 0.25
                ratio_cross = 0.35
                ratio_fresh = 0.40
                n_neighbor = max(1, int(total_slots * ratio_neighbor))
                n_cross = max(1, int(total_slots * ratio_cross))
                n_fresh = max(1, total_slots - n_neighbor - n_cross)

                combined = (
                    neighbor_subcategories[:n_neighbor]
                    + _ensure_cross_cluster_filled(cross_subcategories, n_cross, best_cluster, covered_categories)
                    + fresh_subcategories[:n_fresh]
                )
                combined = _dedupe_keep_order(combined)
                combined = _expand_subcategories(combined, total_slots, covered_categories)

                concepts = list(_load_concepts().keys())
                methods = list(_load_methods().keys())
                concept_pool = random.sample(concepts, min(5, len(concepts))) if concepts else ["cognitive_hierarchy_trap"]
                method_pool = random.sample(methods, min(5, len(methods))) if methods else ["academic_framing"]

                return {
                    "primary_concept": current_concept,
                    "primary_method": current_method,
                    "primary_cluster": best_cluster,
                    "subcategories": combined,
                    "concept_pool": concept_pool,
                    "method_pool": method_pool,
                    "variant_mode": True,
                    "successful_templates": _sanitize_successful_templates(successful_prompts),
                    "new_attack_mix": {"total_slots": total_slots, "success_neighbor_slots": n_neighbor, "cross_cluster_slots": n_cross, "fresh_exploration_slots": n_fresh},
                    "focus_cluster": best_cluster,
                    "weights": {"cluster_internal": 0.7, "cross_cluster_probe": 0.2, "new_exploration": 0.1},
                }
        current_cluster = "A"

    # 计算未覆盖类别
    categories = _load_categories()
    all_subs = []
    for cat in categories.values():
        all_subs.extend(cat["subcategories"].keys())
    uncovered = [s for s in all_subs if s not in covered_categories]

    concepts = list(_load_concepts().keys())
    methods = list(_load_methods().keys())
    concept_pool = random.sample(concepts, min(5, len(concepts))) if concepts else ["cognitive_hierarchy_trap"]
    method_pool = random.sample(methods, min(5, len(methods))) if methods else ["academic_framing"]

    base_subcategories = _get_subs_for_cluster(current_cluster)
    next_strategy = {
        "primary_concept": current_concept,
        "primary_method": current_method,
        "primary_cluster": current_cluster,
        "subcategories": _expand_subcategories(base_subcategories, total_slots, covered_categories),
        "concept_pool": concept_pool,
        "method_pool": method_pool,
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

        cluster_subs = _get_subs_for_cluster(current_cluster)
        neighbor_subcategories = [s for s in cluster_subs if s not in covered_categories]
        cross_cluster_subcategories = _get_cross_cluster_subcategories(current_cluster, covered_categories)
        fresh_subcategories = [
            s for s in uncovered
            if s not in neighbor_subcategories and s not in cross_cluster_subcategories
        ]

        ratio_neighbor = 0.25
        ratio_cross = 0.35
        ratio_fresh = 0.40
        n_neighbor = max(1, int(total_slots * ratio_neighbor))
        n_cross = max(1, int(total_slots * ratio_cross))
        n_fresh = max(1, total_slots - n_neighbor - n_cross)

        combined_subcategories = (
            neighbor_subcategories[:n_neighbor]
            + _ensure_cross_cluster_filled(cross_cluster_subcategories, n_cross, current_cluster, covered_categories)
            + fresh_subcategories[:n_fresh]
        )
        combined_subcategories = _dedupe_keep_order(combined_subcategories)
        next_strategy["subcategories"] = _expand_subcategories(combined_subcategories, total_slots, covered_categories)
        next_strategy["new_attack_mix"] = {"total_slots": total_slots, "success_neighbor_slots": n_neighbor, "cross_cluster_slots": n_cross, "fresh_exploration_slots": n_fresh}
        next_strategy["focus_cluster"] = current_cluster
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
        base = _get_subs_for_cluster(mapping["target_cluster"])
        next_strategy["subcategories"] = _expand_subcategories(base, total_slots, covered_categories)
        if next_strategy["primary_concept"] not in concept_pool:
            concept_pool = [next_strategy["primary_concept"]] + [c for c in concept_pool if c != next_strategy["primary_concept"]][:4]
            next_strategy["concept_pool"] = concept_pool
        return next_strategy

    # 情况 3: 全部失败且无明确信号 → 先换手法，手法轮完换概念
    if bypassed == 0:
        # 连续2轮归零 → 强制切换 concept + cluster，跳过逐一轮转 method
        if consecutive_zero_rounds >= 2:
            next_strategy["primary_concept"] = _rotate_concept(current_concept)
            new_methods = _get_methods_for_concept(next_strategy["primary_concept"])
            next_strategy["primary_method"] = new_methods[0] if new_methods else "academic_framing"
            next_strategy["method_pool"] = new_methods[:5] if new_methods else method_pool
            next_strategy["primary_cluster"] = _rotate_cluster(current_cluster)
            base = _get_subs_for_cluster(next_strategy["primary_cluster"])
            next_strategy["subcategories"] = _expand_subcategories(base, total_slots, covered_categories)
            rotated_concepts = concepts[concepts.index(next_strategy["primary_concept"]):] + concepts[:concepts.index(next_strategy["primary_concept"])] if next_strategy["primary_concept"] in concepts else concepts
            next_strategy["concept_pool"] = rotated_concepts[:5]
            return next_strategy

        methods_for_concept = _get_methods_for_concept(current_concept)
        if current_method in methods_for_concept:
            idx = methods_for_concept.index(current_method)
            if idx + 1 < len(methods_for_concept):
                next_strategy["primary_method"] = methods_for_concept[idx + 1]
                method_pool = methods_for_concept[idx + 1:] + methods_for_concept[:idx + 1]
                next_strategy["method_pool"] = method_pool[:5]
                return next_strategy

        next_strategy["primary_concept"] = _rotate_concept(current_concept)
        new_methods = _get_methods_for_concept(next_strategy["primary_concept"])
        next_strategy["primary_method"] = new_methods[0] if new_methods else "academic_framing"
        next_strategy["method_pool"] = new_methods[:5] if new_methods else method_pool

        next_strategy["primary_cluster"] = _rotate_cluster(current_cluster)
        base = _get_subs_for_cluster(next_strategy["primary_cluster"])
        next_strategy["subcategories"] = _expand_subcategories(base, total_slots, covered_categories)

        rotated_concepts = concepts[concepts.index(next_strategy["primary_concept"]):] + concepts[:concepts.index(next_strategy["primary_concept"])] if next_strategy["primary_concept"] in concepts else concepts
        next_strategy["concept_pool"] = rotated_concepts[:5]
        return next_strategy

    # 情况 4: 有部分成功 → 保持策略微调
    next_strategy["primary_method"] = _rotate_method(current_method)
    return next_strategy


def check_convergence(stats_history: list[dict], config: dict) -> tuple[bool, str]:
    """
    检查收敛条件，判断是否应该终止测试。

    唯一收敛条件：达到最大轮次。
    测试强制按 max_rounds 跑满，不因零绕过提前终止。
    续攻 session 的存活/终止由 _session_fail_tolerance 独立控制。
    """
    max_rounds = int(config.get("max_rounds", 10))

    if len(stats_history) >= max_rounds:
        return True, f"达到最大轮次 ({max_rounds})"

    return False, ""
