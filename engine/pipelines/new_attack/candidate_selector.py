from engine.scheduling.exploration_balancer import build_new_attack_mix


def select_new_attack_candidates(*, strategy: dict, repeated_pattern_ratio: float = 0.0) -> dict:
    mix = strategy.get("new_attack_mix") or build_new_attack_mix(
        total_slots=10,
        repeated_pattern_ratio=repeated_pattern_ratio,
    )
    return {
        "mix": mix,
        "neighbor_candidates": list(strategy.get("neighbor_subcategories", []))[: mix["success_neighbor_slots"]],
        "cross_cluster_candidates": list(strategy.get("cross_cluster_subcategories", []))[: mix["cross_cluster_slots"]],
        "fresh_candidates": list(strategy.get("fresh_subcategories", []))[: mix["fresh_exploration_slots"]],
    }
