def allocate_round_budget(*, total_slots: int, active_session_count: int, recent_success_rate: float, repeated_pattern_ratio: float) -> dict:
    continuation_slots = total_slots // 2
    if active_session_count >= 4 or recent_success_rate >= 0.3:
        continuation_slots += 1
    if repeated_pattern_ratio >= 0.6:
        continuation_slots -= 1
    continuation_slots = max(2, min(total_slots - 2, continuation_slots))
    new_attack_slots = total_slots - continuation_slots
    return {
        "new_attack_slots": new_attack_slots,
        "continuation_slots": continuation_slots,
        "token_budget_ratio": round(continuation_slots / total_slots, 2),
    }
