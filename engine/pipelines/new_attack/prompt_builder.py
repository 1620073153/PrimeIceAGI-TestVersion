def build_new_attack_generation_payload(context: dict) -> dict:
    payload = {
        "strategy": dict(context["strategy"]),
        "kb5_summary": context["kb5_summary"],
        "history_feedback": context["history_feedback"],
        "successful_prompts": list(context["success_refs"]),
    }
    candidates = context.get("candidates", {})
    payload["strategy"].setdefault("neighbor_subcategories", candidates.get("neighbor_candidates", []))
    payload["strategy"].setdefault("cross_cluster_subcategories", candidates.get("cross_cluster_candidates", []))
    payload["strategy"].setdefault("fresh_subcategories", candidates.get("fresh_candidates", []))
    if candidates.get("mix") is not None:
        payload["strategy"].setdefault("new_attack_mix", candidates.get("mix"))
    return payload
