def build_new_attack_mix(*, total_slots: int, repeated_pattern_ratio: float) -> dict:
    fresh_slots = 2 if repeated_pattern_ratio >= 0.6 else 1
    neighbor_slots = max(0, total_slots - fresh_slots)
    return {
        "total_slots": total_slots,
        "success_neighbor_slots": neighbor_slots,
        "fresh_exploration_slots": fresh_slots,
    }
