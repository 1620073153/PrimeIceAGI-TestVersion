from pathlib import Path

from data.batch_progress_store import BatchProgressStore
from engine.batch_models import BatchEvalResult, InterceptType


def _make_result(
    case_id: str,
    *,
    success: bool = True,
    review_required: bool = False,
    intercept_type: InterceptType = InterceptType.GUARDRAIL_BLOCK,
) -> BatchEvalResult:
    return BatchEvalResult(
        case_id=case_id,
        prompt_text="prompt",
        response_text="response",
        category="A",
        subcategory="A1",
        source_file="cases.csv",
        regex_labels=["guardrail"],
        intercept_type=intercept_type,
        judge_reason="reason",
        judge_confidence=0.8,
        success=success,
        retry_count=0,
        latency_ms=500,
        raw_error=None if success else "boom",
        review_required=review_required,
    )


def test_progress_store_tracks_enhanced_progress_fields_and_aborted_state(tmp_path: Path):
    store = BatchProgressStore(tmp_path)

    initial = store.load_progress()
    assert initial["status"] == "pending"
    assert initial["total_cases"] == 0
    assert initial["completed_case_ids"] == []
    assert initial["result_count"] == 0
    assert initial["failed_count"] == 0
    assert initial["review_required_count"] == 0
    assert initial["current_case_id"] is None
    assert initial["stop_reason"] is None
    assert initial["error_message"] is None
    assert initial["last_result"] is None
    assert initial["started_at"] is None
    assert initial["finished_at"] is None
    assert initial["updated_at"] is not None

    store.set_total_cases(3)
    store.mark_started()
    store.mark_running("case-1")
    store.append_result(_make_result("case-1"))
    store.mark_running("case-2")
    store.append_result(_make_result("case-2", success=False, review_required=True, intercept_type=InterceptType.UNCERTAIN))
    store.mark_aborted("用户手动停止")

    progress = store.load_progress()
    assert progress["status"] == "aborted"
    assert progress["total_cases"] == 3
    assert progress["completed_case_ids"] == ["case-1", "case-2"]
    assert progress["result_count"] == 2
    assert progress["failed_count"] == 1
    assert progress["review_required_count"] == 1
    assert progress["current_case_id"] is None
    assert progress["stop_reason"] == "用户手动停止"
    assert progress["error_message"] is None
    assert progress["last_result"]["case_id"] == "case-2"
    assert progress["last_result"]["intercept_type"] == "uncertain"
    assert progress["started_at"] is not None
    assert progress["finished_at"] is not None
    assert progress["updated_at"] is not None
    assert (tmp_path / "results.jsonl").exists()


def test_progress_store_marks_error_and_completed_states(tmp_path: Path):
    error_store = BatchProgressStore(tmp_path / "error")
    error_store.mark_started()
    error_store.mark_running("case-error")
    error_store.mark_error("裁判模型异常")

    error_progress = error_store.load_progress()
    assert error_progress["status"] == "error"
    assert error_progress["current_case_id"] is None
    assert error_progress["error_message"] == "裁判模型异常"
    assert error_progress["finished_at"] is not None

    completed_store = BatchProgressStore(tmp_path / "completed")
    completed_store.set_total_cases(1)
    completed_store.mark_started()
    completed_store.mark_running("case-done")
    completed_store.append_result(_make_result("case-done", intercept_type=InterceptType.NOT_BLOCKED))
    completed_store.mark_completed()

    completed_progress = completed_store.load_progress()
    assert completed_progress["status"] == "completed"
    assert completed_progress["total_cases"] == 1
    assert completed_progress["completed_case_ids"] == ["case-done"]
    assert completed_progress["result_count"] == 1
    assert completed_progress["failed_count"] == 0
    assert completed_progress["review_required_count"] == 0
    assert completed_progress["current_case_id"] is None
    assert completed_progress["stop_reason"] is None
    assert completed_progress["error_message"] is None
    assert completed_progress["started_at"] is not None
    assert completed_progress["finished_at"] is not None
