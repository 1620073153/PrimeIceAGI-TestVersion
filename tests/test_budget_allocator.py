from engine.scheduling.budget_allocator import allocate_round_budget
from engine.scheduling.exploration_balancer import build_new_attack_mix


def test_allocate_round_budget_shifts_toward_continuation_when_active_sessions_are_high():
    budget = allocate_round_budget(
        total_slots=10,
        active_session_count=5,
        recent_success_rate=0.4,
        repeated_pattern_ratio=0.2,
    )
    assert budget == {
        "new_attack_slots": 5,
        "continuation_slots": 5,
        "token_budget_ratio": 0.5,
    }


def test_build_new_attack_mix_forces_fresh_quota_when_repetition_is_high():
    mix = build_new_attack_mix(total_slots=6, repeated_pattern_ratio=0.7)
    assert mix["fresh_exploration_slots"] >= 2
    assert mix["total_slots"] == 6
