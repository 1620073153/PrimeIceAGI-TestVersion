def build_continuation_generation_payload(context: dict) -> dict:
    return {
        "event": "continuation_selection",
        "round": context["round"],
        "candidate_count": context["candidate_count"],
        "selected_count": len(context["selected_sessions"]),
        "selected_sessions": [
            {
                "id": item["session_id"],
                "rank": item.get("continuation_rank"),
                "reason": item.get("selection_reason"),
                "cluster": item.get("cluster", ""),
            }
            for item in context["selected_sessions"]
        ],
    }
