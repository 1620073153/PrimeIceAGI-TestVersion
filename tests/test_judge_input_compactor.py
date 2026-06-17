from engine.summarizers.judge_input_compactor import compact_for_judge


def test_compact_for_judge_strips_long_response_and_keeps_structured_signals():
    compacted = compact_for_judge({
        "prompt_id": "p01",
        "response_text": "very long model response " * 40,
        "status": "partial",
        "cot_signals": ["role_positioning", "output_guarding"],
        "target_category": "B-1",
    })

    assert compacted == {
        "prompt_id": "p01",
        "target_category": "B-1",
        "status": "partial",
        "cot_signals": ["role_positioning", "output_guarding"],
        "response_excerpt": ("very long model response " * 40)[:300].strip(),
    }
