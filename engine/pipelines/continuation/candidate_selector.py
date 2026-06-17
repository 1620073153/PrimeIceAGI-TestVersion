from typing import Callable

from engine.scheduling.continuation_scheduler import select_continuation_sessions


def select_continuation_candidates(
    *,
    active_sessions: dict[str, dict],
    current_round: int,
    continuation_budget: int,
    continuation_fresh_ratio: float,
    continuation_cluster_cap: float,
    scheduler: Callable | None = None,
) -> list[dict]:
    scheduler = scheduler or select_continuation_sessions
    return scheduler(
        list(active_sessions.values()),
        current_round=current_round,
        continuation_budget=continuation_budget,
        fresh_success_round=current_round - 1,
        fresh_min_ratio=continuation_fresh_ratio,
        per_cluster_cap=continuation_cluster_cap,
    )
