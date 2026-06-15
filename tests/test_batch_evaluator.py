from engine.batch_models import BatchEvalCase, BatchEvalConfig, BatchEvalResult, InterceptType


def test_batch_models_capture_core_fields():
    case = BatchEvalCase(
        case_id="case-1",
        prompt_text="测试提示词",
        category="A",
        subcategory="A1",
        expected_label=None,
        source_file="cases.csv",
        tags=["red"],
        meta={"row": 2},
    )
    config = BatchEvalConfig(
        dataset_paths=["cases.csv"],
        exclude_categories=["A"],
        workers=5,
        repeat=1,
        sleep_seconds=2.0,
        retries=2,
        resume_from_progress=True,
        output_dir="reports/batch/task-1",
        output_file="report.xlsx",
        enable_llm_judge=True,
    )
    result = BatchEvalResult(
        case_id="case-1",
        prompt_text="测试提示词",
        response_text="抱歉，我不能帮助你。",
        category="A",
        subcategory="A1",
        source_file="cases.csv",
        regex_labels=["model_refusal"],
        intercept_type=InterceptType.MODEL_REFUSAL,
        judge_reason="命中模型拒答模板",
        judge_confidence=0.91,
        success=True,
        retry_count=1,
        latency_ms=900,
        raw_error=None,
        review_required=False,
    )

    assert case.case_id == "case-1"
    assert config.workers == 5
    assert result.intercept_type is InterceptType.MODEL_REFUSAL
