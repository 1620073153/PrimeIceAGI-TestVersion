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


def _load_concepts():
    data = load_kb("kb2")
    return data.get("concepts", {})


def _load_methods():
    data = load_kb("kb3")
    return data.get("methods", {})


def _load_signal_strategy_map():
    data = load_kb("kb3")
    return data.get("signal_strategy_map", {})


def _get_priority_order():
    return sorted(_load_categories().keys())


def _rotate_method(current_method: str) -> str:
    methods = list(_load_methods().keys())
    if current_method in methods:
        idx = methods.index(current_method)
        return methods[(idx + 1) % len(methods)]
    return methods[0] if methods else "学术讨论包装"


def _rotate_concept(current_concept: str) -> str:
    concepts = list(_load_concepts().keys())
    if current_concept in concepts:
        idx = concepts.index(current_concept)
        return concepts[(idx + 1) % len(concepts)]
    return concepts[0] if concepts else "认知层次陷阱"


def _rotate_cluster(current_cluster: str) -> str:
    priority = _get_priority_order()
    if current_cluster in priority:
        idx = priority.index(current_cluster)
        return priority[(idx + 1) % len(priority)]
    return priority[0] if priority else _get_priority_order()[0]


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
    - total_slots > len(base_list): 优先从全局子类中补充未覆盖的，不足时再循环复用 base_list
    """
    base_list = list(base_list)  # 防御性拷贝，避免副作用污染调用方
    if not base_list:
        categories = _load_categories()
        for cat in categories.values():
            base_list.extend(cat.get("subcategories", {}).keys())
        base_list = _dedupe_keep_order(base_list)

    if total_slots <= len(base_list):
        return base_list[:total_slots]

    covered = set(covered_categories or [])
    base_set = set(base_list)

    # Fix #5: 优先从全局子类中补充未覆盖且不在 base_list 中的
    categories = _load_categories()
    all_global_subs = []
    for cat in categories.values():
        all_global_subs.extend(cat.get("subcategories", {}).keys())
    all_global_subs = _dedupe_keep_order(all_global_subs)

    uncovered_extras = [s for s in all_global_subs if s not in base_set and s not in covered]

    result = list(base_list)
    # 先用未覆盖的全局子类补充
    for s in uncovered_extras:
        if len(result) >= total_slots:
            break
        result.append(s)

    # 仍不足时循环复用 base_list
    cycle_pool = list(base_list)
    if not cycle_pool:
        return result[:total_slots]
    idx = 0
    while len(result) < total_slots:
        result.append(cycle_pool[idx % len(cycle_pool)])
        idx += 1

    return result[:total_slots]


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


def _coverage_weighted_sample(fresh_pool: list[str], n: int, covered_categories: list[str]) -> list[str]:
    """
    覆盖率加权采样：按每个簇的未覆盖子类数量分配 fresh slots。
    每个有候选的簇保底1个slot，剩余按比例分配，消除字典序偏向。
    """
    if not fresh_pool or n <= 0:
        return []

    categories = _load_categories()
    fresh_set = set(fresh_pool)

    cluster_fresh_subs: dict[str, list[str]] = {}
    for cluster_key, cat_data in categories.items():
        subs_in_fresh = [s for s in cat_data.get("subcategories", {}).keys() if s in fresh_set]
        if subs_in_fresh:
            cluster_fresh_subs[cluster_key] = subs_in_fresh

    if not cluster_fresh_subs:
        pool_copy = list(fresh_pool)
        random.shuffle(pool_copy)
        return pool_copy[:n]

    # 每个非空簇保底1个slot
    cluster_quotas: dict[str, int] = {}
    remaining_slots = n
    for cluster_key in cluster_fresh_subs:
        if remaining_slots > 0:
            cluster_quotas[cluster_key] = 1
            remaining_slots -= 1
        else:
            cluster_quotas[cluster_key] = 0

    # 剩余按权重比例分配
    if remaining_slots > 0:
        total_weight = sum(len(v) for v in cluster_fresh_subs.values())
        if total_weight > 0:
            for cluster_key, subs in cluster_fresh_subs.items():
                extra = int(remaining_slots * (len(subs) / total_weight))
                cluster_quotas[cluster_key] += extra
            # 舍入误差补给权重最大的簇
            allocated = sum(cluster_quotas.values())
            leftover = n - allocated
            if leftover > 0:
                sorted_clusters = sorted(cluster_fresh_subs.keys(), key=lambda k: len(cluster_fresh_subs[k]), reverse=True)
                for i in range(min(leftover, len(sorted_clusters))):
                    cluster_quotas[sorted_clusters[i]] += 1

    # 每个簇内随机采样
    result = []
    for cluster_key, quota in cluster_quotas.items():
        pool = cluster_fresh_subs[cluster_key]
        actual_take = min(quota, len(pool))
        if actual_take > 0:
            result.extend(random.sample(pool, actual_take))

    # 总数不够时从剩余全局pool补
    if len(result) < n:
        used = set(result)
        leftover_pool = [s for s in fresh_pool if s not in used]
        random.shuffle(leftover_pool)
        result.extend(leftover_pool[:n - len(result)])

    return result[:n]


def get_scan_strategy(total_slots: int = 10, disabled_categories: set = None) -> dict:
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
        if disabled_categories:
            subs = [s for s in subs if s not in disabled_categories]
        if subs:
            scan_subs.append(subs[0])

    all_subs = []
    for cat in categories.values():
        all_subs.extend(cat.get("subcategories", {}).keys())
    if disabled_categories:
        all_subs = [s for s in all_subs if s not in disabled_categories]
    remaining = [s for s in all_subs if s not in scan_subs]
    extra_count = max(0, total_slots - len(scan_subs))
    if remaining and extra_count > 0:
        scan_subs += random.sample(remaining, min(extra_count, len(remaining)))

    scan_subs = _expand_subcategories(scan_subs, total_slots)

    concepts = list(_load_concepts().keys())
    methods = list(_load_methods().keys())

    concept_pool = random.sample(concepts, min(5, len(concepts))) if concepts else ["认知层次陷阱"]
    method_pool = random.sample(methods, min(5, len(methods))) if methods else ["学术讨论包装"]

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
            "cluster_internal": 0.7,
            "new_exploration": 0.3,
        },
    }


def decide_next_strategy(stats: dict, current_strategy: dict,
                         round_num: int, covered_categories: list[str],
                         successful_prompts: list[dict] | None = None,
                         total_slots: int = 10,
                         consecutive_zero_rounds: int = 0,
                         disabled_categories: set = None) -> dict:
    """
    决策下一轮策略

    输入:
    - stats: 本轮统计 (bypassed/blocked/partial/signal_distribution/primary_signal)
    - current_strategy: 当前轮策略参数
    - round_num: 当前轮次
    - covered_categories: 已覆盖(越狱成功)的子类列表
    - successful_prompts: 本轮成功的提示词列表
    - total_slots: 需要的子类总数（= effective_concurrency）
    - disabled_categories: 用户禁用的子类集合

    输出:
    - 下一轮策略 dict，含 subcategories / concept_pool / method_pool
    """
    primary_signal = stats.get("primary_signal")
    bypassed = stats.get("bypassed", 0)
    current_concept = current_strategy.get("primary_concept", "认知层次陷阱")
    current_method = current_strategy.get("primary_method", "学术讨论包装")
    current_cluster = current_strategy.get("primary_cluster", _get_priority_order()[0])

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
                if disabled_categories:
                    all_subs_temp = [s for s in all_subs_temp if s not in disabled_categories]
                uncovered = [s for s in all_subs_temp if s not in covered_categories]

                neighbor_subcategories = _get_subs_for_cluster(best_cluster)
                if disabled_categories:
                    neighbor_subcategories = [s for s in neighbor_subcategories if s not in disabled_categories]
                fresh_subcategories = [s for s in uncovered if s not in neighbor_subcategories]

                n_neighbor = max(1, int(total_slots * 0.25))
                n_fresh = total_slots - n_neighbor

                combined = (
                    neighbor_subcategories[:n_neighbor]
                    + fresh_subcategories[:n_fresh]
                )
                combined = _dedupe_keep_order(combined)
                combined = _expand_subcategories(combined, total_slots, covered_categories)

                concepts = list(_load_concepts().keys())
                methods = list(_load_methods().keys())
                concept_pool = random.sample(concepts, min(5, len(concepts))) if concepts else ["认知层次陷阱"]
                method_pool = random.sample(methods, min(5, len(methods))) if methods else ["学术讨论包装"]

                return {
                    "primary_concept": current_concept,
                    "primary_method": current_method,
                    "primary_cluster": best_cluster,
                    "subcategories": combined,
                    "concept_pool": concept_pool,
                    "method_pool": method_pool,
                    "variant_mode": True,
                    "successful_templates": _sanitize_successful_templates(successful_prompts),
                    "new_attack_mix": {"total_slots": total_slots, "success_neighbor_slots": n_neighbor, "fresh_exploration_slots": n_fresh},
                    "focus_cluster": best_cluster,
                    "weights": {"cluster_internal": 0.7, "new_exploration": 0.3},
                }
        current_cluster = _get_priority_order()[0]
        # scan全败：选未覆盖率最高的簇而非硬编码
        categories_temp = _load_categories()
        cluster_uncov = {ck: len([s for s in cat.get("subcategories", {}).keys() if s not in covered_categories]) for ck, cat in categories_temp.items()}
        if cluster_uncov:
            current_cluster = max(cluster_uncov, key=cluster_uncov.get)

    # 计算未覆盖类别
    categories = _load_categories()
    all_subs = []
    for cat in categories.values():
        all_subs.extend(cat["subcategories"].keys())
    # 过滤用户禁用的子类
    if disabled_categories:
        all_subs = [s for s in all_subs if s not in disabled_categories]
    uncovered = [s for s in all_subs if s not in covered_categories]

    concepts = list(_load_concepts().keys())
    methods = list(_load_methods().keys())
    concept_pool = random.sample(concepts, min(5, len(concepts))) if concepts else ["认知层次陷阱"]
    method_pool = random.sample(methods, min(5, len(methods))) if methods else ["学术讨论包装"]

    base_subcategories = _get_subs_for_cluster(current_cluster)
    if disabled_categories:
        base_subcategories = [s for s in base_subcategories if s not in disabled_categories]
    next_strategy = {
        "primary_concept": current_concept,
        "primary_method": current_method,
        "primary_cluster": current_cluster,
        "subcategories": _expand_subcategories(base_subcategories, total_slots, covered_categories),
        "concept_pool": concept_pool,
        "method_pool": method_pool,
        "variant_mode": False,
        "weights": {
            "cluster_internal": 0.7,
            "new_exploration": 0.3,
        },
    }

    # 情况 1: 有越狱成功 → 弱偏置扩散 + 覆盖率驱动 + 锚点推进
    if bypassed > 0 and successful_prompts:
        next_strategy["variant_mode"] = True
        next_strategy["successful_templates"] = _sanitize_successful_templates(successful_prompts)

        cluster_subs = _get_subs_for_cluster(current_cluster)
        if disabled_categories:
            cluster_subs = [s for s in cluster_subs if s not in disabled_categories]
        neighbor_subcategories = [s for s in cluster_subs if s not in covered_categories]

        # 锚点自动推进：当前cluster未覆盖子类<=1时，切到未覆盖率最高的簇
        effective_cluster = current_cluster
        if len(neighbor_subcategories) <= 1:
            cluster_uncovered_counts = {}
            for ck in categories:
                ck_subs = _get_subs_for_cluster(ck)
                if disabled_categories:
                    ck_subs = [s for s in ck_subs if s not in disabled_categories]
                uncov = sum(1 for s in ck_subs if s not in covered_categories)
                if uncov > 0:
                    cluster_uncovered_counts[ck] = uncov
            if cluster_uncovered_counts:
                effective_cluster = max(cluster_uncovered_counts, key=cluster_uncovered_counts.get)
                cluster_subs = _get_subs_for_cluster(effective_cluster)
                if disabled_categories:
                    cluster_subs = [s for s in cluster_subs if s not in disabled_categories]
                neighbor_subcategories = [s for s in cluster_subs if s not in covered_categories]

        n_neighbor = max(1, int(total_slots * 0.25))
        n_fresh = total_slots - n_neighbor

        # fresh用覆盖率加权采样，消除字典序偏向
        fresh_excluded = set(neighbor_subcategories)
        fresh_subcategories = [s for s in uncovered if s not in fresh_excluded]
        fresh_selected = _coverage_weighted_sample(fresh_subcategories, n_fresh, covered_categories)

        random.shuffle(neighbor_subcategories)
        combined_subcategories = (
            neighbor_subcategories[:n_neighbor]
            + fresh_selected
        )
        combined_subcategories = _dedupe_keep_order(combined_subcategories)
        next_strategy["subcategories"] = _expand_subcategories(combined_subcategories, total_slots, covered_categories)
        next_strategy["new_attack_mix"] = {"total_slots": total_slots, "success_neighbor_slots": n_neighbor, "fresh_exploration_slots": n_fresh}
        next_strategy["neighbor_subcategories"] = neighbor_subcategories[:n_neighbor]
        next_strategy["fresh_subcategories"] = fresh_selected
        next_strategy["focus_cluster"] = effective_cluster
        next_strategy["primary_cluster"] = effective_cluster
        next_strategy["primary_method"] = current_method
        next_strategy["primary_concept"] = current_concept
        return next_strategy

    # 情况 2: 有明确信号 → 根据信号映射策略（50% 随机因子）
    signal_map = _load_signal_strategy_map()
    if primary_signal and primary_signal in signal_map:
        mapping = signal_map[primary_signal]
        if random.random() < 0.5:
            # 50% 概率使用 signal_map 推荐方向
            next_strategy["primary_concept"] = mapping["primary_concept"]
            next_strategy["primary_method"] = mapping["primary_method"]
        else:
            # 50% 概率从 concept_pool/method_pool 随机选
            next_strategy["primary_concept"] = random.choice(concept_pool)
            next_strategy["primary_method"] = random.choice(method_pool)
        next_strategy["primary_cluster"] = mapping["target_cluster"]
        base = _get_subs_for_cluster(mapping["target_cluster"])
        if disabled_categories:
            base = [s for s in base if s not in disabled_categories]
        next_strategy["subcategories"] = _expand_subcategories(base, total_slots, covered_categories)
        if next_strategy["primary_concept"] not in concept_pool:
            concept_pool = [next_strategy["primary_concept"]] + [c for c in concept_pool if c != next_strategy["primary_concept"]][:4]
            next_strategy["concept_pool"] = concept_pool
        # Fix #6: method_pool 同步 — 确保 primary_method 在 pool 中
        if next_strategy["primary_method"] not in method_pool:
            next_strategy["method_pool"] = [next_strategy["primary_method"]] + method_pool[:4]
        return next_strategy

    # 情况 3: 全部失败且无明确信号 → 全局轮转
    if bypassed == 0:
        # 单轮失败 → 全局轮转手法，直接 return
        if consecutive_zero_rounds < 2:
            next_strategy["primary_method"] = _rotate_method(current_method)
            # Fix #6: method_pool 同步
            if next_strategy["primary_method"] not in next_strategy["method_pool"]:
                next_strategy["method_pool"] = [next_strategy["primary_method"]] + next_strategy["method_pool"][:4]
            return next_strategy

        # 连续2轮归零 → 三换：concept + method + cluster
        next_strategy["primary_concept"] = _rotate_concept(current_concept)
        next_strategy["primary_method"] = _rotate_method(current_method)
        next_strategy["primary_cluster"] = _rotate_cluster(current_cluster)
        base = _get_subs_for_cluster(next_strategy["primary_cluster"])
        if disabled_categories:
            base = [s for s in base if s not in disabled_categories]
        next_strategy["subcategories"] = _expand_subcategories(base, total_slots, covered_categories)
        rotated_concepts = concepts[concepts.index(next_strategy["primary_concept"]):] + concepts[:concepts.index(next_strategy["primary_concept"])] if next_strategy["primary_concept"] in concepts else concepts
        next_strategy["concept_pool"] = rotated_concepts[:5] or ["认知层次陷阱"]
        # Fix #6: method_pool 同步
        if next_strategy["primary_method"] not in next_strategy["method_pool"]:
            next_strategy["method_pool"] = [next_strategy["primary_method"]] + next_strategy["method_pool"][:4]
        return next_strategy

    # 情况 4: 有部分成功 → 保持策略微调
    next_strategy["primary_method"] = _rotate_method(current_method)
    # Fix #6: method_pool 同步
    if next_strategy["primary_method"] not in next_strategy["method_pool"]:
        next_strategy["method_pool"] = [next_strategy["primary_method"]] + next_strategy["method_pool"][:4]
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
