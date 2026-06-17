def normalize_continuation_prompts(prompts: list[dict] | None) -> list[dict]:
    normalized = []
    for item in prompts or []:
        current = dict(item)
        current.setdefault("type", "continue")
        normalized.append(current)
    return normalized
