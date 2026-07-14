from engine.runtime import (
    FailureMemory,
    RoundContext,
    SessionCache,
    SessionStore,
    SuccessMemory,
)


def test_round_context_snapshot_returns_serializable_copy():
    strategy = {"primary_cluster": "A2"}
    ctx = RoundContext(current_round=3, strategy=strategy, token_budget_ratio=0.6)

    snapshot = ctx.snapshot()

    assert snapshot == {
        "current_round": 3,
        "strategy": {"primary_cluster": "A2"},
        "token_budget_ratio": 0.6,
    }

    strategy["primary_cluster"] = "A1"
    snapshot["strategy"]["primary_cluster"] = "A3"

    assert ctx.strategy == {"primary_cluster": "A2"}


def test_session_store_seed_merge_and_snapshot_use_copy_semantics():
    seeded = {
        "S-1": {
            "session_id": "S-1",
            "messages": ["hello"],
            "meta": {"cluster": "A2"},
        }
    }
    store = SessionStore.seed(seeded)
    assert isinstance(store, SessionStore)

    seeded["S-1"]["messages"].append("mutated")
    seeded["S-1"]["meta"]["cluster"] = "A1"

    store.upsert(
        "S-1",
        {
            "messages": ["override"],
            "meta": {"score": 2},
        },
        merge=True,
    )

    item = store.get("S-1")
    assert item == {
        "session_id": "S-1",
        "messages": ["override"],
        "meta": {"score": 2},
    }

    item["messages"].append("outside")
    item["meta"]["score"] = 99

    snapshot = store.snapshot()
    assert snapshot == {
        "S-1": {
            "session_id": "S-1",
            "messages": ["override"],
            "meta": {"score": 2},
        }
    }

    snapshot["S-1"]["messages"].append("snapshot")
    snapshot["S-1"]["meta"]["score"] = 0

    assert store.get("S-1") == {
        "session_id": "S-1",
        "messages": ["override"],
        "meta": {"score": 2},
    }


def test_runtime_memory_and_cache_stores_preserve_copy_semantics():
    cache_seed = {
        "S-1": {
            "recent_summary": ["summary-1"],
            "flags": {"fresh": True},
        }
    }
    cache = SessionCache.seed(cache_seed)
    assert isinstance(cache, SessionCache)
    cache_seed["S-1"]["recent_summary"].append("mutated")
    cache_seed["S-1"]["flags"]["fresh"] = False

    cache.put(
        "S-1",
        {
            "recent_summary": ["summary-2"],
            "flags": {"ttl": 30},
        },
        merge=True,
    )
    cache_item = cache.get("S-1")
    assert cache_item == {
        "recent_summary": ["summary-2"],
        "flags": {"ttl": 30},
    }
    cache_item["recent_summary"].append("outside")
    cache_item["flags"]["ttl"] = 0
    assert cache.snapshot() == {
        "S-1": {
            "recent_summary": ["summary-2"],
            "flags": {"ttl": 30},
        }
    }

    success_seed = [{"prompt_id": "p01", "tags": ["seed"]}]
    success_memory = SuccessMemory.seed(success_seed)
    assert isinstance(success_memory, SuccessMemory)
    success_seed[0]["tags"].append("mutated")
    success_memory.add({"prompt_id": "p02", "tags": ["added"]})
    latest_success = success_memory.latest()
    assert latest_success == [
        {"prompt_id": "p01", "tags": ["seed"]},
        {"prompt_id": "p02", "tags": ["added"]},
    ]
    latest_success[0]["tags"].append("outside")
    assert success_memory.snapshot() == [
        {"prompt_id": "p01", "tags": ["seed"]},
        {"prompt_id": "p02", "tags": ["added"]},
    ]

    failure_seed = [{"prompt_id": "p03", "errors": ["seed"]}]
    failure_memory = FailureMemory.seed(failure_seed)
    assert isinstance(failure_memory, FailureMemory)
    failure_seed[0]["errors"].append("mutated")
    failure_memory.add({"prompt_id": "p04", "errors": ["added"]})
    latest_failure = failure_memory.latest(1)
    assert latest_failure == [{"prompt_id": "p04", "errors": ["added"]}]
    latest_failure[0]["errors"].append("outside")
    assert failure_memory.snapshot() == [
        {"prompt_id": "p03", "errors": ["seed"]},
        {"prompt_id": "p04", "errors": ["added"]},
    ]


def test_seed_classmethods_return_seeded_instances_without_leaking_state():
    session_store = SessionStore.seed({"S-9": {"session_id": "S-9", "target_category": "Z-1"}})
    session_cache = SessionCache.seed({"S-9": {"recent_summary": "shared"}})
    success_memory = SuccessMemory.seed([{"prompt_id": "p09", "target_category": "Z-1"}])
    failure_memory = FailureMemory.seed([{"prompt_id": "p10", "refusal_guess": "policy"}])

    assert session_store.get("S-9") == {"session_id": "S-9", "target_category": "Z-1"}
    assert session_cache.get("S-9") == {"recent_summary": "shared"}
    assert success_memory.latest() == [{"prompt_id": "p09", "target_category": "Z-1"}]
    assert failure_memory.latest() == [{"prompt_id": "p10", "refusal_guess": "policy"}]

    assert SessionStore().get("S-9") is None
    assert SessionCache().get("S-9") is None
    assert SuccessMemory().latest() == []
    assert FailureMemory().latest() == []
