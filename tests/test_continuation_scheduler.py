import math

from engine.continuation_scheduler import select_continuation_sessions


def _session(
    session_id: str,
    *,
    cluster: str | None = None,
    target_category: str | None = None,
    turn_num: int = 1,
    continuation_count: int = 0,
    last_success_round: int = 4,
):
    data = {
        "session_id": session_id,
        "target_category": target_category or f"{cluster or 'A'}-1",
        "turn_num": turn_num,
        "continuation_count": continuation_count,
        "last_success_round": last_success_round,
    }
    if cluster is not None:
        data["cluster"] = cluster
    return data


def test_select_continuation_sessions_balances_fresh_and_old_samples():
    sessions = [
        _session("fresh-a", cluster="A1", turn_num=1, last_success_round=4),
        _session("fresh-b", cluster="A2", turn_num=1, last_success_round=4),
        _session("fresh-c", cluster="A3", turn_num=2, last_success_round=4),
        _session("old-a", cluster="A4", turn_num=2, continuation_count=0, last_success_round=3),
        _session("old-b", cluster="A5", turn_num=3, continuation_count=1, last_success_round=3),
        _session("stale-a", cluster="A1", turn_num=7, continuation_count=4, last_success_round=1),
    ]

    selected = select_continuation_sessions(
        sessions,
        current_round=5,
        continuation_budget=5,
        fresh_min_ratio=0.4,
        per_cluster_cap=1.0,
    )

    assert len(selected) == 5

    fresh_ids = {item["session_id"] for item in selected if item["last_success_round"] == 4}
    assert len(fresh_ids) >= math.ceil(5 * 0.4)

    assert [item["continuation_rank"] for item in selected] == [1, 2, 3, 4, 5]
    assert all("continuation_score" in item for item in selected)
    assert all("selection_reason" in item for item in selected)
    assert selected[0]["continuation_score"] >= selected[-1]["continuation_score"]


def test_select_continuation_sessions_enforces_cluster_cap_from_explicit_or_derived_cluster():
    sessions = [
        _session("a-fresh-1", cluster="A1", turn_num=1, last_success_round=4),
        _session("a-fresh-2", target_category="A1-2", turn_num=1, last_success_round=4),
        _session("a-fresh-3", target_category="A1-3", turn_num=2, last_success_round=4),
        _session("a-old-4", cluster="A1", turn_num=2, continuation_count=1, last_success_round=3),
        _session("b-fresh-1", cluster="A2", turn_num=1, last_success_round=4),
        _session("c-old-1", cluster="A3", turn_num=2, continuation_count=0, last_success_round=3),
        _session("d-old-1", cluster="A4", turn_num=2, continuation_count=0, last_success_round=3),
    ]

    selected = select_continuation_sessions(
        sessions,
        current_round=5,
        continuation_budget=5,
        fresh_min_ratio=0.4,
        per_cluster_cap=0.4,
    )

    assert len(selected) == 5
    selected_a = [item for item in selected if (item.get("cluster") or item["target_category"].split("-", 1)[0]) == "A1"]
    assert len(selected_a) == 2


def test_select_continuation_sessions_prefers_fresh_over_stale_low_value_samples():
    sessions = [
        _session("fresh-a", cluster="A1", turn_num=1, continuation_count=0, last_success_round=4),
        _session("fresh-b", cluster="A2", turn_num=1, continuation_count=0, last_success_round=4),
        _session("old-good", cluster="A3", turn_num=2, continuation_count=0, last_success_round=3),
        _session("stale-low-1", cluster="A4", turn_num=8, continuation_count=5, last_success_round=1),
        _session("stale-low-2", cluster="A5", turn_num=6, continuation_count=4, last_success_round=2),
    ]

    selected = select_continuation_sessions(
        sessions,
        current_round=5,
        continuation_budget=3,
        fresh_min_ratio=0.4,
        per_cluster_cap=1.0,
    )

    selected_ids = [item["session_id"] for item in selected]
    assert "fresh-a" in selected_ids
    assert "fresh-b" in selected_ids
    assert "old-good" in selected_ids
    assert "stale-low-1" not in selected_ids
    assert "stale-low-2" not in selected_ids
