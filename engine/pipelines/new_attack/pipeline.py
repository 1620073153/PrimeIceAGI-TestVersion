from engine.adapters.claude_agent_adapter import build_new_attack_generation_request

from .context_builder import build_new_attack_context
from .candidate_selector import select_new_attack_candidates
from .prompt_builder import build_new_attack_generation_payload
from .post_processor import normalize_new_attack_prompts
from .diversity_guard import filter_new_attack_duplicates


def summarize_successes_for_new_attack(successful: list[dict] | None) -> list[dict]:
    summarized = []
    for item in (successful or [])[:3]:
        summarized.append({
            "prompt_id": item.get("prompt_id", ""),
            "target_category": item.get("target_category", ""),
            "strategy_tags": list(item.get("strategy_tags", []))[:4],
            "concept": item.get("concept", ""),
            "method": item.get("method", ""),
            "type": item.get("type", "new"),
        })
    return summarized


def prepare_new_attack_payload(
    *,
    strategy: dict,
    kb5_summary: str,
    history_feedback: str,
    all_successful_prompts: list[dict] | None,
) -> dict:
    success_refs = summarize_successes_for_new_attack((all_successful_prompts or [])[-5:])
    candidates = select_new_attack_candidates(strategy=strategy)
    context = build_new_attack_context(
        strategy=strategy,
        kb5_summary=kb5_summary,
        history_feedback=history_feedback,
        success_refs=success_refs,
        candidates=candidates,
    )
    payload = build_new_attack_generation_payload(context)
    payload["successful_prompts"] = success_refs if success_refs else None
    payload["request"] = build_new_attack_generation_request(
        round_num=strategy.get("current_round") or 0,
        payload=payload,
    )
    return payload


def finalize_new_attack_prompts(prompts: list[dict]) -> list[dict]:
    normalized = normalize_new_attack_prompts(prompts)
    return filter_new_attack_duplicates(normalized)
