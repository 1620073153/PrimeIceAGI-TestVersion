import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from engine.batch_models import BatchEvalResult


class BatchProgressStore:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.progress_file = self.output_dir / "progress.json"
        self.results_file = self.output_dir / "results.jsonl"
        if not self.progress_file.exists():
            self._save_progress(self._default_progress())

    def load_progress(self) -> dict:
        progress = self._default_progress()
        if self.progress_file.exists():
            progress.update(json.loads(self.progress_file.read_text(encoding="utf-8")))
        progress["completed_case_ids"] = list(progress.get("completed_case_ids") or [])
        if progress.get("updated_at") is None:
            progress["updated_at"] = self._timestamp()
            self._save_progress(progress)
        return progress

    def set_total_cases(self, total_cases: int) -> None:
        progress = self.load_progress()
        progress["total_cases"] = total_cases
        progress["updated_at"] = self._timestamp()
        self._save_progress(progress)

    def mark_started(self) -> None:
        progress = self.load_progress()
        progress["status"] = "running"
        progress["stop_reason"] = None
        progress["error_message"] = None
        progress["current_case_id"] = None
        progress["started_at"] = progress.get("started_at") or self._timestamp()
        progress["finished_at"] = None
        progress["updated_at"] = self._timestamp()
        self._save_progress(progress)

    def mark_running(self, case_id: str) -> None:
        progress = self.load_progress()
        progress["status"] = "running"
        progress["current_case_id"] = case_id
        progress["started_at"] = progress.get("started_at") or self._timestamp()
        progress["finished_at"] = None
        progress["updated_at"] = self._timestamp()
        self._save_progress(progress)

    def mark_aborted(self, reason: str) -> None:
        progress = self.load_progress()
        progress["status"] = "aborted"
        progress["current_case_id"] = None
        progress["stop_reason"] = reason
        progress["finished_at"] = self._timestamp()
        progress["updated_at"] = self._timestamp()
        self._save_progress(progress)

    def mark_error(self, message: str) -> None:
        progress = self.load_progress()
        progress["status"] = "error"
        progress["current_case_id"] = None
        progress["error_message"] = message
        progress["finished_at"] = self._timestamp()
        progress["updated_at"] = self._timestamp()
        self._save_progress(progress)

    def mark_completed(self) -> None:
        progress = self.load_progress()
        progress["status"] = "completed"
        progress["current_case_id"] = None
        progress["stop_reason"] = None
        progress["error_message"] = None
        progress["finished_at"] = self._timestamp()
        progress["updated_at"] = self._timestamp()
        self._save_progress(progress)

    def append_result(self, result: BatchEvalResult) -> None:
        payload = asdict(result)
        payload["intercept_type"] = result.intercept_type.value
        with self.results_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

        progress = self.load_progress()
        if result.case_id not in progress["completed_case_ids"]:
            progress["completed_case_ids"].append(result.case_id)
        progress["result_count"] += 1
        if not result.success:
            progress["failed_count"] += 1
        if result.review_required:
            progress["review_required_count"] += 1
        progress["last_result"] = {
            "case_id": result.case_id,
            "category": result.category,
            "intercept_type": result.intercept_type.value,
            "judge_reason": result.judge_reason,
            "review_required": result.review_required,
            "success": result.success,
        }
        progress["updated_at"] = self._timestamp()
        self._save_progress(progress)

    def _default_progress(self) -> dict:
        return {
            "status": "pending",
            "total_cases": 0,
            "completed_case_ids": [],
            "result_count": 0,
            "failed_count": 0,
            "review_required_count": 0,
            "current_case_id": None,
            "stop_reason": None,
            "error_message": None,
            "last_result": None,
            "started_at": None,
            "finished_at": None,
            "updated_at": self._timestamp(),
        }

    def _save_progress(self, progress: dict) -> None:
        self.progress_file.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

    def _timestamp(self) -> str:
        return datetime.now(UTC).isoformat()
