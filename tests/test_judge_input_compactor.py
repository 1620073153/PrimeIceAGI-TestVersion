from engine.summarizers.judge_input_compactor import compact_for_judge


def test_compact_for_judge_strips_long_response_and_keeps_structured_signals():
    compacted = compact_for_judge({
        "prompt_id": "p01",
        "prompt_text": "some prompt",
        "response_text": "very long model response " * 40,
        "status": "partial",
        "cot_signals": ["role_positioning", "output_guarding"],
        "target_category": "A2-a",
    })

    assert compacted == {
        "prompt_id": "p01",
        "prompt_text": "some prompt",
        "target_category": "A2-a",
        "status": "partial",
        "cot_signals": ["role_positioning", "output_guarding"],
        "response_text": ("very long model response " * 40)[:1500].strip(),
    }
