"""
边界追踪器 — 结构化记录持久化
保留原始 (手法×内容→结果) 记录到 kb5.json 用于历史追溯。
防御情报分析由 defense_fingerprinter + intel_aggregator 处理。
"""

import time
from data.kb_store import save_kb5_boundary_records


def record_boundaries(results: list[dict], round_num: int) -> None:
    """从本轮全部结果中提取边界记录（成功+失败都记录）"""
    records = []
    for r in results:
        category = r.get("target_category", "")
        if not category:
            continue

        concept = r.get("concept", "")
        method = r.get("method", "")
        strategy_tags = r.get("strategy_tags", [])
        status = r.get("status", "blocked")

        if status in ("error", "guardrail_blocked"):
            continue

        records.append({
            "category": category,
            "concept": concept,
            "method": method,
            "strategy_tags": strategy_tags,
            "outcome": status,
            "round": round_num,
            "ts": int(time.time()),
        })

    if records:
        save_kb5_boundary_records(records)
