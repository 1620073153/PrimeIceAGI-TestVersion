import time
from collections import Counter
from pathlib import Path
from typing import Callable, Protocol

from data.batch_progress_store import BatchProgressStore
from data.dataset_loader import load_batch_cases
from engine.batch_models import BatchEvalConfig, BatchEvalResult
from engine.intercept_classifier import classify_interception


class TargetClientProtocol(Protocol):
    def generate(self, prompt_text: str) -> str:
        ...


class JudgeProtocol(Protocol):
    def judge_interception(self, prompt_text: str, response_text: str, regex_labels: list[str]) -> dict:
        ...


def run_batch_evaluation(
    config: BatchEvalConfig,
    target_client: TargetClientProtocol,
    judge: JudgeProtocol,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    should_stop = should_stop or (lambda: False)
    cases = load_batch_cases(config.dataset_paths, exclude_categories=config.exclude_categories)
    progress_store = BatchProgressStore(Path(config.output_dir))
    completed_case_ids: set[str] = set()

    if config.resume_from_progress:
        progress = progress_store.load_progress()
        completed_case_ids = set(progress.get("completed_case_ids", []))

    processed_cases = 0
    skipped_cases = 0
    intercept_counts: Counter[str] = Counter()
    recent_results: list[dict] = []
    review_required_count = 0

    progress_store.set_total_cases(len(cases))
    progress_store.mark_started()

    try:
        for case in cases:
            if case.case_id in completed_case_ids:
                skipped_cases += 1
                continue

            if should_stop():
                progress_store.mark_aborted("用户手动停止")
                return {
                    "status": "aborted",
                    "stop_reason": "用户手动停止",
                    "total_cases": len(cases),
                    "processed_cases": processed_cases,
                    "skipped_cases": skipped_cases,
                    "intercept_counts": dict(intercept_counts),
                    "review_required_count": review_required_count,
                    "recent_results": recent_results,
                }

            progress_store.mark_running(case.case_id)
            start = time.perf_counter()
            response_text = target_client.generate(case.prompt_text)
            classification = classify_interception(case.prompt_text, response_text, judge)
            latency_ms = int((time.perf_counter() - start) * 1000)

            result = BatchEvalResult(
                case_id=case.case_id,
                prompt_text=case.prompt_text,
                response_text=response_text,
                category=case.category,
                subcategory=case.subcategory,
                source_file=case.source_file,
                regex_labels=classification.regex_labels,
                intercept_type=classification.intercept_type,
                judge_reason=classification.reason,
                judge_confidence=classification.confidence,
                success=True,
                retry_count=0,
                latency_ms=latency_ms,
                raw_error=None,
                review_required=classification.review_required,
            )
            progress_store.append_result(result)
            processed_cases += 1
            intercept_counts[classification.intercept_type.value] += 1
            if result.review_required:
                review_required_count += 1
            recent_results.append({
                "case_id": result.case_id,
                "category": result.category,
                "intercept_type": result.intercept_type.value,
                "judge_reason": result.judge_reason,
                "review_required": result.review_required,
            })
            recent_results = recent_results[-10:]

            if config.sleep_seconds > 0:
                if should_stop():
                    progress_store.mark_aborted("用户手动停止")
                    return {
                        "status": "aborted",
                        "stop_reason": "用户手动停止",
                        "total_cases": len(cases),
                        "processed_cases": processed_cases,
                        "skipped_cases": skipped_cases,
                        "intercept_counts": dict(intercept_counts),
                        "review_required_count": review_required_count,
                        "recent_results": recent_results,
                    }
                time.sleep(config.sleep_seconds)
    except Exception as exc:
        progress_store.mark_error(str(exc))
        raise

    progress_store.mark_completed()
    return {
        "status": "completed",
        "stop_reason": None,
        "total_cases": len(cases),
        "processed_cases": processed_cases,
        "skipped_cases": skipped_cases,
        "intercept_counts": dict(intercept_counts),
        "review_required_count": review_required_count,
        "recent_results": recent_results,
    }
