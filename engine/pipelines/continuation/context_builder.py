def build_continuation_context(*, current_round: int, candidate_count: int, selected_sessions: list[dict]) -> dict:
    enriched = []
    for session in selected_sessions:
        messages = list(session.get("messages", []))
        enriched.append({
            **dict(session),
            "state_summary": {
                "session_id": session.get("session_id", ""),
                "target_category": session.get("target_category", ""),
                "selection_reason": session.get("selection_reason", ""),
            },
            "recent_context_fragments": [
                {"role": item.get("role", ""), "content": item.get("content", "")[:400]}
                for item in messages[-2:]
            ],
        })
    return {
        "round": current_round,
        "candidate_count": candidate_count,
        "selected_sessions": enriched,
    }
