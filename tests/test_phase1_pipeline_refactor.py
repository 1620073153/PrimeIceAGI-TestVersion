from engine.orchestrator import RedTeamOrchestrator


def test_new_attack_pipeline_summarizes_successes_without_full_prompt_text():
    from engine.pipelines.new_attack.pipeline import summarize_successes_for_new_attack

    summarized = summarize_successes_for_new_attack([
        {
            "prompt_id": "p01",
            "prompt_text": "very long sensitive prompt text should not be forwarded",
            "target_category": "A2-b",
            "strategy_tags": ["角色扮演", "authority_framing", "extra", "ignored", "overflow"],
            "concept": "角色扮演",
            "method": "authority_framing",
            "type": "new",
        }
    ])

    assert summarized == [
        {
            "prompt_id": "p01",
            "target_category": "A2-b",
            "strategy_tags": ["角色扮演", "authority_framing", "extra", "ignored"],
            "concept": "角色扮演",
            "method": "authority_framing",
            "type": "new",
        }
    ]


def test_build_continuation_context_emits_state_summary_and_recent_fragments():
    from engine.pipelines.continuation.context_builder import build_continuation_context

    selected_sessions = [
        {
            "session_id": "N1",
            "target_category": "A2-a",
            "selection_reason": "fresh_success",
            "messages": [
                {"role": "user", "content": "setup"},
                {"role": "assistant", "content": "response"},
                {"role": "user", "content": "followup"},
            ],
        }
    ]

    context = build_continuation_context(
        current_round=3,
        candidate_count=2,
        selected_sessions=selected_sessions,
    )

    session = context["selected_sessions"][0]
    assert session["state_summary"] == {
        "session_id": "N1",
        "target_category": "A2-a",
        "selection_reason": "fresh_success",
    }
    assert session["recent_context_fragments"] == [
        {"role": "assistant", "content": "response"},
        {"role": "user", "content": "followup"},
    ]


def test_continuation_pipeline_prepares_selected_sessions_and_event(monkeypatch):
    from engine.pipelines.continuation.pipeline import prepare_continuation_round

    active_sessions = {
        "S1": {
            "session_id": "S1",
            "messages": [],
            "turn_num": 1,
            "target_category": "A2-d",
            "cluster": "A2",
            "created_round": 1,
            "last_success_round": 2,
            "continuation_count": 1,
            "success_score": 1.4,
        },
        "N1": {
            "session_id": "N1",
            "messages": [],
            "turn_num": 1,
            "target_category": "A2-a",
            "cluster": "A2",
            "created_round": 2,
            "last_success_round": 2,
            "continuation_count": 0,
            "success_score": 1.2,
        },
    }

    selected_session = {
        **active_sessions["N1"],
        "selection_reason": "fresh_success",
        "continuation_rank": 1,
        "continuation_score": 2.0,
    }

    monkeypatch.setattr(
        "engine.pipelines.continuation.pipeline.select_continuation_sessions",
        lambda *args, **kwargs: [selected_session],
    )

    selected_sessions, selection_event = prepare_continuation_round(
        active_sessions=active_sessions,
        current_round=3,
        allow_continuation=True,
        continuation_budget=5,
        continuation_fresh_ratio=0.4,
        continuation_cluster_cap=0.4,
    )

    assert [s["session_id"] for s in selected_sessions] == ["N1"]
    assert selection_event == {
        "event": "continuation_selection",
        "round": 3,
        "candidate_count": 2,
        "selected_count": 1,
        "selected_sessions": [
            {
                "id": "N1",
                "rank": 1,
                "reason": "fresh_success",
                "cluster": "A2",
            }
        ],
    }


def test_runtime_phase1_skeleton_modules_are_importable():
    from engine.runtime.round_context import RoundContext
    from engine.runtime.session_store import SessionStore
    from engine.runtime.session_cache import SessionCache
    from engine.runtime.success_memory import SuccessMemory
    from engine.runtime.failure_memory import FailureMemory

    ctx = RoundContext(current_round=3, strategy={"primary_cluster": "A2"})
    session_store = SessionStore()
    session_cache = SessionCache()
    success_memory = SuccessMemory()
    failure_memory = FailureMemory()

    session_store.upsert("S-1", {"session_id": "S-1", "target_category": "A2-a"})
    session_cache.put("S-1", {"recent_summary": "summary"})
    success_memory.add({"prompt_id": "p01", "target_category": "A2-a"})
    failure_memory.add({"prompt_id": "p02", "refusal_guess": "policy_refusal"})

    assert ctx.current_round == 3
    assert session_store.get("S-1")["target_category"] == "A2-a"
    assert session_cache.get("S-1")["recent_summary"] == "summary"
    assert success_memory.latest()[0]["prompt_id"] == "p01"
    assert failure_memory.latest()[0]["prompt_id"] == "p02"


def test_orchestrator_generate_all_prompts_uses_phase1_pipeline_hooks(monkeypatch):
    import engine.pipelines.new_attack.pipeline as new_attack_pipeline
    import engine.pipelines.continuation.pipeline as continuation_pipeline

    events = []
    orch = RedTeamOrchestrator(
        {"target_api_url": "https://x", "target_api_key": "k", "target_model": "m"},
        event_callback=events.append,
    )
    orch.current_round = 3
    orch.strategy = {"variant_mode": False, "subcategories": ["A2-d"]}
    orch.kb5_summary = "intel"
    orch.active_sessions = {
        "N1": {
            "session_id": "N1",
            "messages": [],
            "turn_num": 1,
            "target_category": "A2-a",
            "cluster": "A2",
            "created_round": 2,
            "last_success_round": 2,
            "continuation_count": 0,
            "success_score": 1.2,
        }
    }
    orch.all_successful_prompts = [
        {
            "prompt_id": "p02",
            "prompt_text": "very long sensitive prompt text should not be directly forwarded",
            "target_category": "A2-b",
            "strategy_tags": ["角色扮演", "authority_framing"],
            "concept": "角色扮演",
            "method": "authority_framing",
            "type": "new",
        }
    ]

    called = {"new": False, "cont": False}

    selected_session = {
        **orch.active_sessions["N1"],
        "selection_reason": "fresh_success",
        "continuation_rank": 1,
        "continuation_score": 2.0,
    }

    def fake_prepare_continuation_round(**kwargs):
        called["cont"] = True
        return [selected_session], {
            "event": "continuation_selection",
            "round": 3,
            "candidate_count": 1,
            "selected_count": 1,
            "selected_sessions": [{"id": "N1", "rank": 1, "reason": "fresh_success", "cluster": "A2"}],
        }

    def fake_summarize_successes(successful):
        called["new"] = True
        return [{
            "prompt_id": "p02",
            "target_category": "A2-b",
            "strategy_tags": ["角色扮演", "authority_framing"],
            "concept": "角色扮演",
            "method": "authority_framing",
            "type": "new",
        }]

    captured = {}

    def fake_generate_parallel(**kwargs):
        captured.update(kwargs)
        return ([{"prompt_id": "p01", "prompt_text": "new prompt", "target_category": "A2-d"}], [])

    monkeypatch.setattr(continuation_pipeline, "prepare_continuation_round", fake_prepare_continuation_round)
    monkeypatch.setattr(new_attack_pipeline, "summarize_successes_for_new_attack", fake_summarize_successes)
    monkeypatch.setattr("engine.orchestrator.prompt_generator.generate_parallel", fake_generate_parallel)

    orch._generate_all_prompts()

    assert called == {"new": True, "cont": True}
    assert [s["session_id"] for s in captured["active_sessions"]] == ["N1"]
    assert captured["successful_prompts"][0]["target_category"] == "A2-b"
