"""提示词生成容错测试"""

import pytest

from engine import prompt_generator
from engine.orchestrator import RedTeamOrchestrator


class _FakeTargetClient:
    def __init__(self, config):
        self.config = config


def test_generate_parallel_keeps_continuations_when_new_generation_fails(monkeypatch):
    def fail_new(**kwargs):
        raise RuntimeError("解析到的提示词不足 3 条: 0")

    def ok_continuations(**kwargs):
        return [
            {
                "type": "continue",
                "session_id": "S-1-p01",
                "prompt_id": "cont-S-1-p01",
                "prompt_text": "这是续攻提示词，应该继续保留原会话上下文执行。",
                "target_category": "A2-d",
            }
        ]

    monkeypatch.setattr(prompt_generator, "generate_prompts", fail_new)
    monkeypatch.setattr(prompt_generator, "generate_continuations", ok_continuations)

    new_prompts, cont_prompts = prompt_generator.generate_parallel(
        round_num=5,
        strategy={"subcategories": ["A2-d"]},
        active_sessions=[{"session_id": "S-1-p01", "messages": [], "target_category": "A2-d"}],
    )

    assert new_prompts == []
    assert len(cont_prompts) == 1
    assert cont_prompts[0]["type"] == "continue"
    assert cont_prompts[0]["session_id"] == "S-1-p01"


def test_generate_parallel_raises_when_new_and_continuation_both_fail(monkeypatch):
    def fail_new(**kwargs):
        raise RuntimeError("解析到的提示词不足 3 条: 0")

    def fail_continuations(**kwargs):
        raise RuntimeError("续攻输出非JSON")

    monkeypatch.setattr(prompt_generator, "generate_prompts", fail_new)
    monkeypatch.setattr(prompt_generator, "generate_continuations", fail_continuations)

    with pytest.raises(RuntimeError, match="提示词生成完全失败"):
        prompt_generator.generate_parallel(
            round_num=5,
            strategy={"subcategories": ["A2-d"]},
            active_sessions=[{"session_id": "S-1-p01", "messages": [], "target_category": "A2-d"}],
        )


def test_orchestrator_skips_single_empty_generation_round_then_recovers(monkeypatch):
    events = []
    orchestrator = RedTeamOrchestrator(
        config={
            "target_api_url": "http://127.0.0.1/mock",
            "target_api_key": "test-key",
            "agent_api_url": "http://127.0.0.1/mock-agent",
            "agent_api_key": "test-agent-key",
            "max_rounds": 2,
            "cooldown_no_new": 2,
            "agent2_enabled": False,
            "agent3_enabled": False,
        },
        event_callback=events.append,
    )

    calls = {"count": 0}

    def fake_generate_all_prompts():
        calls["count"] += 1
        if calls["count"] == 1:
            return [], []
        return [
            {
                "prompt_id": "p01",
                "prompt_text": "第二轮恢复后的新攻提示词。",
                "target_category": "A2-d",
            }
        ], []

    def fake_call_target_batch(all_prompts):
        return [
            {
                "prompt_id": p["prompt_id"],
                "prompt_text": p["prompt_text"],
                "response_text": "我可以配合完成这个请求。",
                "status": "bypassed",
                "type": p.get("type", "new"),
                "target_category": p.get("target_category", "A2-d"),
                "latency_ms": 1,
            }
            for p in all_prompts
        ]

    monkeypatch.setattr(orchestrator, "_generate_all_prompts", fake_generate_all_prompts)
    monkeypatch.setattr(orchestrator, "_call_target_batch", fake_call_target_batch)

    report = orchestrator.run()

    assert calls["count"] == 2
    assert len(report["rounds"]) == 1
    assert report["rounds"][0]["round"] == 2
    assert any(e.get("event") == "generation_failed" and e.get("round") == 1 for e in events)


def test_orchestrator_stops_after_two_empty_generation_rounds(monkeypatch):
    events = []
    orchestrator = RedTeamOrchestrator(
        config={
            "target_api_url": "http://127.0.0.1/mock",
            "target_api_key": "test-key",
            "agent_api_url": "http://127.0.0.1/mock-agent",
            "agent_api_key": "test-agent-key",
            "max_rounds": 5,
            "cooldown_no_new": 2,
            "generation_failure_limit": 2,
            "agent2_enabled": False,
            "agent3_enabled": False,
        },
        event_callback=events.append,
    )

    calls = {"count": 0}

    def fake_generate_all_prompts():
        calls["count"] += 1
        return [], []

    monkeypatch.setattr(orchestrator, "_generate_all_prompts", fake_generate_all_prompts)

    report = orchestrator.run()

    assert calls["count"] == 2
    assert report["rounds"] == []
    assert any(
        e.get("event") == "stopped" and "连续 2 轮提示词生成失败" in e.get("reason", "")
        for e in events
    )
