"""
Intel Aggregator — Layers 2 and 3 of the KB5 boundary intelligence pipeline.
Clusters fingerprints, deduplicates, and produces condensed tactical text.
"""

from collections import defaultdict


def aggregate_fingerprints(fingerprints: list[dict]) -> list[dict]:
    """
    Layer 2: 按 defense_type 聚类，去重 trigger/weak_signal，计算命中率。
    返回按 hit_rate 降序排列的 pattern 列表。
    """
    if not fingerprints:
        return []

    groups: dict[str, list[dict]] = defaultdict(list)
    for fp in fingerprints:
        groups[fp["defense_type"]].append(fp)

    total = len(fingerprints)
    patterns = []

    for defense_type, items in groups.items():
        categories = list(set(
            item.get("category", "") for item in items if item.get("category")
        ))

        trigger_by_cat: dict[str, str] = {}
        for item in items:
            cat = item.get("category", "_")
            existing = trigger_by_cat.get(cat, "")
            if len(item.get("trigger_summary", "")) > len(existing):
                trigger_by_cat[cat] = item["trigger_summary"]

        best_trigger = max(trigger_by_cat.values(), key=len) if trigger_by_cat else ""

        signals = list(set(
            item["weak_signal"] for item in items if item.get("weak_signal")
        ))[:3]

        patterns.append({
            "defense_type": defense_type,
            "hit_count": len(items),
            "hit_rate": len(items) / max(total, 1),
            "categories_affected": categories,
            "trigger_summary": best_trigger,
            "weak_signals": signals,
        })

    patterns.sort(key=lambda p: p["hit_rate"], reverse=True)
    return patterns

def merge_with_history(
    new_patterns: list[dict],
    existing_profile: list[dict],
    current_round: int,
    stale_threshold: int = 3,
) -> list[dict]:
    """
    将新 patterns 合并到滚动防御画像中。
    - 相同 defense_type：更新 hit_rate/trigger/signals，刷新 last_seen
    - 新 type：加入
    - 超过 stale_threshold 轮未见：剔除
    """
    profile_by_type = {p["defense_type"]: dict(p) for p in existing_profile}

    for new_p in new_patterns:
        dt = new_p["defense_type"]
        if dt in profile_by_type:
            existing = profile_by_type[dt]
            existing["hit_rate"] = max(existing.get("hit_rate", 0), new_p["hit_rate"])
            existing["hit_count"] = existing.get("hit_count", 0) + new_p["hit_count"]
            existing["categories_affected"] = list(set(
                existing.get("categories_affected", []) + new_p.get("categories_affected", [])
            ))
            if len(new_p.get("trigger_summary", "")) > len(existing.get("trigger_summary", "")):
                existing["trigger_summary"] = new_p["trigger_summary"]
            existing["weak_signals"] = list(set(
                existing.get("weak_signals", []) + new_p.get("weak_signals", [])
            ))[:4]
            existing["last_seen_round"] = current_round
        else:
            entry = dict(new_p)
            entry["last_seen_round"] = current_round
            profile_by_type[dt] = entry

    merged = [
        p for p in profile_by_type.values()
        if current_round - p.get("last_seen_round", current_round) <= stale_threshold
    ]
    merged.sort(key=lambda p: p.get("hit_rate", 0), reverse=True)
    return merged


def format_defense_intel(patterns: list[dict], max_patterns: int = 4) -> str:
    """
    Layer 3: 将防御画像浓缩为注入文本（≤500 token）。
    """
    if not patterns:
        return ""

    top = patterns[:max_patterns]
    lines = [f"目标防御画像 ({len(patterns)} patterns):"]

    for i, p in enumerate(top, 1):
        dt = p["defense_type"].upper()
        rate_pct = round(p.get("hit_rate", 0) * 100)
        cat_count = len(p.get("categories_affected", []))
        trigger = p.get("trigger_summary", "unknown")
        weakness = p.get("weak_signals", ["未识别"])[0] if p.get("weak_signals") else "未识别"

        lines.append(f"[{i}] {dt} (命中率{rate_pct}%, 影响{cat_count}类)")
        lines.append(f"    触发机制: {trigger}")
        lines.append(f"    可利用弱点: {weakness}")

    return "\n".join(lines)
