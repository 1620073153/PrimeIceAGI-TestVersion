import math
from typing import Any


def _derive_cluster(session: dict[str, Any]) -> str:
    cluster = session.get("cluster")
    if cluster:
        return str(cluster)
    category = str(session.get("target_category", ""))
    return category.split("-", 1)[0] if category else ""


def _score_session(session: dict[str, Any], current_round: int, fresh_success_round: int) -> float:
    score = float(session.get("success_score", 1.0))

    if session.get("last_success_round") == fresh_success_round:
        score += 1.0

    turn_num = int(session.get("turn_num", 1) or 1)
    continuation_count = int(session.get("continuation_count", 0) or 0)
    last_success_round = int(session.get("last_success_round", current_round) or current_round)

    score -= max(turn_num - 1, 0) * 0.2
    score -= continuation_count * 0.35
    score -= max(current_round - last_success_round - 1, 0) * 0.45
    return round(score, 4)


def _take_candidates(
    candidates: list[dict[str, Any]],
    slots: int,
    cluster_cap_count: int,
    taken_ids: set[str],
    cluster_counts: dict[str, int],
) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    for item in candidates:
        if len(picked) >= slots:
            break
        sid = str(item["session_id"])
        cluster = item["cluster"]
        if sid in taken_ids:
            continue
        if cluster and cluster_counts.get(cluster, 0) >= cluster_cap_count:
            continue
        picked.append(item)
        taken_ids.add(sid)
        if cluster:
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
    return picked


def select_continuation_sessions(
    active_sessions: list[dict[str, Any]],
    current_round: int,
    continuation_budget: int = 5,
    fresh_success_round: int | None = None,
    fresh_min_ratio: float = 0.4,
    per_cluster_cap: float = 0.4,
) -> list[dict[str, Any]]:
    if not active_sessions or continuation_budget <= 0:
        return []

    fresh_success_round = fresh_success_round or (current_round - 1)
    cluster_cap_count = max(1, math.ceil(continuation_budget * max(per_cluster_cap, 0.0)))
    fresh_slots = min(
        len(active_sessions),
        math.ceil(continuation_budget * max(fresh_min_ratio, 0.0)),
    )

    annotated: list[dict[str, Any]] = []
    for sess in active_sessions:
        item = dict(sess)
        item["cluster"] = _derive_cluster(item)
        item["continuation_score"] = _score_session(item, current_round, fresh_success_round)
        annotated.append(item)

    annotated.sort(
        key=lambda s: (
            s["continuation_score"],
            -int(s.get("continuation_count", 0) or 0),
            -int(s.get("turn_num", 1) or 1),
            str(s.get("session_id", "")),
        ),
        reverse=True,
    )

    fresh = [s for s in annotated if s.get("last_success_round") == fresh_success_round]
    mature = [s for s in annotated if s.get("last_success_round") != fresh_success_round]

    taken_ids: set[str] = set()
    cluster_counts: dict[str, int] = {}
    selected: list[dict[str, Any]] = []

    selected.extend(_take_candidates(fresh, fresh_slots, cluster_cap_count, taken_ids, cluster_counts))

    remaining_budget = continuation_budget - len(selected)
    if remaining_budget > 0:
        selected.extend(_take_candidates(mature, remaining_budget, cluster_cap_count, taken_ids, cluster_counts))

    remaining_budget = continuation_budget - len(selected)
    if remaining_budget > 0:
        selected.extend(_take_candidates(annotated, remaining_budget, cluster_cap_count, taken_ids, cluster_counts))

    selected = selected[:continuation_budget]
    selected.sort(key=lambda s: s["continuation_score"], reverse=True)

    for index, sess in enumerate(selected, start=1):
        sess["selection_reason"] = (
            "fresh_success"
            if sess.get("last_success_round") == fresh_success_round
            else "mature_depth"
        )
        sess["continuation_rank"] = index

    return selected
