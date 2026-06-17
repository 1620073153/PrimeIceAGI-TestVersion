def build_event(event: str, **payload) -> dict:
    return {"event": event, **payload}
