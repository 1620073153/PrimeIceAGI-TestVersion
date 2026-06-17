from engine.orchestrator import RedTeamOrchestrator


def test_orchestrator_builds_runtime_snapshot_before_prompt_generation(monkeypatch):
    orch = RedTeamOrchestrator({"target_api_url": "https://x", "target_api_key": "k", "target_model": "m"})
    orch.current_round = 3
    orch.strategy = {"primary_cluster": "B", "subcategories": ["B-1"]}
    orch.active_sessions = {
        "S-1": {
            "session_id": "S-1",
            "messages": [],
            "target_category": "B-1",
            "turn_num": 1,
            "last_success_round": 2,
            "continuation_count": 0,
            "success_score": 1.2,
        }
    }
    orch.all_successful_prompts = [{
        "prompt_id": "p01",
        "target_category": "B-1",
        "strategy_tags": ["role_play"],
        "concept": "role_play",
        "method": "authority_framing",
    }]

    captured = {}

    def fake_prepare_new_attack_payload(**kwargs):
        captured["new_attack"] = kwargs
        return {"strategy": kwargs["strategy"], "successful_prompts": []}

    def fake_prepare_continuation_round(**kwargs):
        captured["continuation"] = kwargs
        return [], None

    monkeypatch.setattr("engine.orchestrator.new_attack_pipeline.prepare_new_attack_payload", fake_prepare_new_attack_payload)
    monkeypatch.setattr("engine.orchestrator.continuation_pipeline.prepare_continuation_round", fake_prepare_continuation_round)
    monkeypatch.setattr("engine.orchestrator.claude_agent.generate_parallel", lambda **kwargs: ([], []))

    orch._generate_all_prompts()

    assert captured["new_attack"]["strategy"]["primary_cluster"] == "B"
    assert captured["continuation"]["current_round"] == 3
