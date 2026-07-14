def build_new_attack_generation_request(*, round_num: int, payload: dict) -> dict:
    return {
        "generator": "prompt_skill",
        "round_num": round_num,
        "strategy": dict(payload["strategy"]),
        "kb5_summary": payload.get("kb5_summary", ""),
        "history_feedback": payload.get("history_feedback", ""),
        "successful_prompts": list(payload.get("successful_prompts") or []),
    }
