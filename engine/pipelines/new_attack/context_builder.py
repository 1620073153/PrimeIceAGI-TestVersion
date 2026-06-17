def build_new_attack_context(*, strategy: dict, kb5_summary: str, history_feedback: str, success_refs: list[dict], candidates: dict) -> dict:
    return {
        "strategy": dict(strategy),
        "kb5_summary": kb5_summary,
        "history_feedback": history_feedback,
        "success_refs": list(success_refs),
        "candidates": dict(candidates),
        "constraints": {
            "use_success_summary_only": True,
            "disallow_history_fulltext": True,
        },
    }
