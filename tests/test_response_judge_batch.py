from engine.response_judge import judge_interception


class DummyLLMClient:
    def call(self, system_prompt, user_message, temperature, max_tokens):
        return '{"intercept_type":"guardrail_block","confidence":0.88,"reason":"外部风控模板"}'


def test_judge_interception_parses_batch_归因_json():
    result = judge_interception(
        prompt_text="危险问题",
        response_text="为了安全合规，本次内容无法展示。",
        regex_labels=["guardrail"],
        llm_client=DummyLLMClient(),
    )

    assert result["intercept_type"] == "guardrail_block"
    assert result["confidence"] == 0.88
    assert result["reason"] == "外部风控模板"
