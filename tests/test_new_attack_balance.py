from engine.adapters.prompt_generator_adapter import build_new_attack_generation_request
from engine.orchestrator import RedTeamOrchestrator


def test_new_attack_generation_request_keeps_prompt_skill_but_only_passes_summary_refs():
    request = build_new_attack_generation_request(
        round_num=3,
        payload={
            "strategy": {"subcategories": ["A2-a"]},
            "kb5_summary": "intel",
            "history_feedback": "feedback",
            "successful_prompts": [
                {
                    "prompt_id": "p01",
                    "target_category": "A2-b",
                    "strategy_tags": ["角色扮演", "authority_framing"],
                    "concept": "角色扮演",
                    "method": "authority_framing",
                }
            ],
        },
    )

    assert request["round_num"] == 3
    assert request["successful_prompts"][0]["target_category"] == "A2-b"
    assert "prompt_text" not in request["successful_prompts"][0]
    assert request["generator"] == "prompt_skill"


def test_feedback_to_new_attack_uses_success_summary_not_full_prompt_text(monkeypatch):
    orch = RedTeamOrchestrator({"target_api_url": "https://x", "target_api_key": "k", "target_model": "m"})
    orch.current_round = 3
    orch.strategy = {
        "primary_concept": "认知层次陷阱",
        "primary_method": "学术讨论包装",
        "primary_cluster": "A2",
        "subcategories": ["A2-a"],
    }
    orch.kb5_summary = "intel"

    captured = {}

    def fake_generate_parallel(**kwargs):
        captured.update(kwargs)
        return ([{"prompt_id": "p01", "prompt_text": "new prompt", "target_category": "A2-a"}], [])

    monkeypatch.setattr("engine.orchestrator.prompt_generator.generate_parallel", fake_generate_parallel)
    monkeypatch.setattr("engine.orchestrator.select_continuation_sessions", lambda *args, **kwargs: [])

    orch.all_successful_prompts = [
        {
            "prompt_id": "p02",
            "prompt_text": "very long sensitive prompt text should not be directly forwarded to new attack generator",
            "target_category": "A2-b",
            "strategy_tags": ["角色扮演", "authority_framing"],
            "concept": "角色扮演",
            "method": "authority_framing",
            "type": "new",
        }
    ]

    orch._generate_all_prompts()
    successful_prompts = captured["successful_prompts"]
    assert successful_prompts[0]["target_category"] == "A2-b"
    assert successful_prompts[0]["strategy_tags"] == ["角色扮演", "authority_framing"]
    assert "prompt_text" not in successful_prompts[0]
