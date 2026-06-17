def compact_for_judge(result: dict) -> dict:
    return {
        "prompt_id": result.get("prompt_id", ""),
        "target_category": result.get("target_category", ""),
        "status": result.get("status", ""),
        "cot_signals": list(result.get("cot_signals", [])),
        "response_excerpt": str(result.get("response_text", ""))[:300].strip(),
    }


def compact_batch_for_judge(results: list[dict]) -> list[dict]:
    return [compact_for_judge(item) for item in results]
