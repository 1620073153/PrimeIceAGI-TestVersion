from typing import Callable

from engine.continuation_scheduler import select_continuation_sessions

from .context_builder import build_continuation_context
from .candidate_selector import select_continuation_candidates
from .prompt_builder import build_continuation_generation_payload
from .post_processor import normalize_continuation_prompts
from .continuation_guard import filter_continuation_prompts


def prepare_continuation_round(
    *,
    active_sessions: dict[str, dict],
    current_round: int,
    allow_continuation: bool,
    continuation_budget: int,
    continuation_fresh_ratio: float,
    continuation_cluster_cap: float,
    scheduler: Callable | None = None,
) -> tuple[list[dict], dict | None]:
    if not allow_continuation or not active_sessions:
        return [], None

    selected_sessions = select_continuation_candidates(
        active_sessions=active_sessions,
        current_round=current_round,
        continuation_budget=continuation_budget,
        continuation_fresh_ratio=continuation_fresh_ratio,
        continuation_cluster_cap=continuation_cluster_cap,
        scheduler=scheduler or select_continuation_sessions,
    )
    context = build_continuation_context(
        current_round=current_round,
        candidate_count=len(active_sessions),
        selected_sessions=selected_sessions,
    )
    selection_event = build_continuation_generation_payload(context)
    return selected_sessions, selection_event


def finalize_continuation_prompts(prompts: list[dict]) -> list[dict]:
    normalized = normalize_continuation_prompts(prompts)
    return filter_continuation_prompts(normalized)
