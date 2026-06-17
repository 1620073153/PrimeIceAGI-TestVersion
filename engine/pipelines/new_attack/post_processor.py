def normalize_new_attack_prompts(prompts: list[dict] | None) -> list[dict]:
    normalized = []
    for item in prompts or []:
        current = dict(item)
        current.setdefault("type", "new")
        current.setdefault("strategy_tags", [])
        normalized.append(current)
    return normalized
