from engine.adapters.claude_agent_adapter import build_new_attack_generation_request
from engine.orchestrator import RedTeamOrchestrator


def test_new_attack_generation_request_keeps_prompt_skill_but_only_passes_summary_refs():
    request = build_new_attack_generation_request(
        round_num=3,
        payload={
            "strategy": {"subcategories": ["B-1"]},
            "kb5_summary": "intel",
            "history_feedback": "feedback",
            "successful_prompts": [
                {
                    "prompt_id": "p01",
                    "target_category": "B-2",
                    "strategy_tags": ["role_play", "authority_framing"],
                    "concept": "role_play",
                    "method": "authority_framing",
                }
            ],
        },
    )

    assert request["round_num"] == 3
    assert request["successful_prompts"][0]["target_category"] == "B-2"
    assert "prompt_text" not in request["successful_prompts"][0]
    assert request["generator"] == "prompt_skill"


def test_feedback_to_new_attack_uses_success_summary_not_full_prompt_text(monkeypatch):
    orch = RedTeamOrchestrator({"target_api_url": "https://x", "target_api_key": "k", "target_model": "m"})
    orch.current_round = 3
    orch.strategy = {
        "primary_concept": "cognitive_hierarchy_trap",
        "primary_method": "academic_framing",
        "primary_cluster": "B",
        "subcategories": ["B-1"],
    }
    orch.kb5_summary = "intel"

    captured = {}

    def fake_generate_parallel(**kwargs):
        captured.update(kwargs)
        return ([{"prompt_id": "p01", "prompt_text": "new prompt", "target_category": "B-1"}], [])

    monkeypatch.setattr("engine.orchestrator.claude_agent.generate_parallel", fake_generate_parallel)
    monkeypatch.setattr("engine.orchestrator.select_continuation_sessions", lambda *args, **kwargs: [])

    orch.all_successful_prompts = [
        {
            "prompt_id": "p02",
            "prompt_text": "very long sensitive prompt text should not be directly forwarded to new attack generator",
            "target_category": "B-2",
            "strategy_tags": ["role_play", "authority_framing"],
            "concept": "role_play",
            "method": "authority_framing",
            "type": "new",
        }
    ]

    orch._generate_all_prompts()
    successful_prompts = captured["successful_prompts"]
    assert successful_prompts[0]["target_category"] == "B-2"
    assert successful_prompts[0]["strategy_tags"] == ["role_play", "authority_framing"]
    assert "prompt_text" not in successful_prompts[0]
