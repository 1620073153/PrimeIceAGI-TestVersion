def allocate_round_budget(
    *,
    total_slots: int,
    active_session_count: int,
    recent_success_rate: float,
    repeated_pattern_ratio: float,
    allow_continuation: bool = True,
) -> dict:
    """动态分配新攻/续攻配额。

    Args:
        total_slots: 本轮总 prompt 数（= target_concurrency）
        active_session_count: 当前活跃会话数
        recent_success_rate: 上一轮实际绕过率 (0.0~1.0)
        repeated_pattern_ratio: 重复模式比例 (0.0~1.0)
        allow_continuation: 是否允许续攻
    """
    if not allow_continuation or active_session_count == 0:
        return {
            "new_attack_slots": total_slots,
            "continuation_slots": 0,
            "token_budget_ratio": 0.0,
        }

    # 基线：续攻占 40%
    continuation_slots = int(total_slots * 0.4)

    # 活跃会话多 或 成功率高 → 续攻增加
    if active_session_count >= 4 or recent_success_rate >= 0.3:
        continuation_slots = int(total_slots * 0.5)

    # 重复率高 → 削减续攻，增加新攻探索
    if repeated_pattern_ratio >= 0.6:
        continuation_slots = int(total_slots * 0.3)

    # 首轮无历史 → 全量新攻
    if recent_success_rate == 0.0 and active_session_count == 0:
        continuation_slots = 0

    # 边界：续攻不超过活跃会话数（每会话最多1条），且至少留2条给新攻
    continuation_slots = min(continuation_slots, active_session_count)
    continuation_slots = min(continuation_slots, total_slots - 2)
    continuation_slots = max(0, continuation_slots)

    new_attack_slots = total_slots - continuation_slots

    return {
        "new_attack_slots": new_attack_slots,
        "continuation_slots": continuation_slots,
        "token_budget_ratio": round(continuation_slots / max(total_slots, 1), 2),
    }
