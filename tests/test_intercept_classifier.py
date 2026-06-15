from engine.batch_models import InterceptType
from engine.intercept_classifier import classify_interception


class DummyJudge:
    def judge_interception(self, prompt_text, response_text, regex_labels):
        return {
            "intercept_type": "guardrail_block",
            "reason": "检测到外部护栏风控话术",
            "confidence": 0.76,
        }


def test_classify_interception_uses_regex_as_signal_but_llm_as_final_decision():
    result = classify_interception(
        prompt_text="危险问题",
        response_text="为了安全合规，本次内容无法展示。",
        judge=DummyJudge(),
    )

    assert result.intercept_type is InterceptType.GUARDRAIL_BLOCK
    assert "guardrail" in result.regex_labels
    assert result.review_required is False
