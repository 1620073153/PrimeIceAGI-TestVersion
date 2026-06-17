from engine.orchestrator import RedTeamOrchestrator


def test_add_session_tracks_metadata_for_scheduler():
    orch = RedTeamOrchestrator(
        {"target_api_url": "https://x", "target_api_key": "k", "target_model": "m"}
    )
    orch.current_round = 2

    orch._add_session(
        {
            "prompt_id": "p02",
            "prompt_text": "prompt text",
            "response_text": "response text",
            "target_category": "B-2",
            "concept": "role_play",
            "method": "chain_of_thought_masking",
        },
        "new",
    )

    sess = next(iter(orch.active_sessions.values()))
    assert sess["cluster"] == "B"
    assert sess["concept"] == "role_play"
    assert sess["method"] == "chain_of_thought_masking"
    assert sess["continuation_count"] == 0
    assert sess["success_score"] == 1.0
    assert sess["last_success_round"] == 2



def test_generate_all_prompts_only_sends_selected_sessions(monkeypatch):
    events = []
    orch = RedTeamOrchestrator(
        {"target_api_url": "https://x", "target_api_key": "k", "target_model": "m"},
        event_callback=events.append,
    )
    orch.current_round = 3
    orch.strategy = {"variant_mode": False, "subcategories": ["A-1"]}
    orch.kb5_summary = "intel"
    orch.active_sessions = {
        "S1": {
            "session_id": "S1",
            "messages": [],
            "turn_num": 1,
            "target_category": "A-1",
            "cluster": "A",
            "created_round": 1,
            "last_success_round": 2,
            "continuation_count": 1,
            "success_score": 1.4,
        },
        "N1": {
            "session_id": "N1",
            "messages": [],
            "turn_num": 1,
            "target_category": "B-1",
            "cluster": "B",
            "created_round": 2,
            "last_success_round": 2,
            "continuation_count": 0,
            "success_score": 1.2,
        },
    }

    selected_session = {
        **orch.active_sessions["N1"],
        "selection_reason": "fresh_success",
        "continuation_rank": 1,
        "continuation_score": 2.0,
    }

    monkeypatch.setattr(
        "engine.orchestrator.select_continuation_sessions",
        lambda *args, **kwargs: [selected_session],
    )

    captured = {}

    def fake_generate_parallel(**kwargs):
        captured["active_sessions"] = kwargs.get("active_sessions")
        return (
            [{"prompt_id": "p01", "prompt_text": "new prompt", "target_category": "A-1"}],
            [
                {
                    "type": "continue",
                    "session_id": "N1",
                    "prompt_id": "cont-N1",
                    "prompt_text": "follow up prompt text long enough",
                    "target_category": "B-1",
                }
            ],
        )

    monkeypatch.setattr("engine.orchestrator.claude_agent.generate_parallel", fake_generate_parallel)

    _, cont_prompts = orch._generate_all_prompts()

    assert [p["session_id"] for p in cont_prompts] == ["N1"]
    assert [s["session_id"] for s in captured["active_sessions"]] == ["N1"]

    selection_events = [e for e in events if e.get("event") == "continuation_selection"]
    assert len(selection_events) == 1
    assert selection_events[0]["selected_count"] == 1
    assert selection_events[0]["selected_sessions"][0]["reason"] == "fresh_success"
