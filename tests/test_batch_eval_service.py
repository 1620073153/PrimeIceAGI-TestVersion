from pathlib import Path

import backend.services.batch_eval_service as batch_eval_service
from backend.task_manager import TaskManager


class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


class FakeBatchEvaluator:
    def __call__(self, config, target_client, judge, should_stop):
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "batch-report.xlsx").write_bytes(b"xlsx")
        return {
            "status": "completed",
            "stop_reason": None,
            "total_cases": 2,
            "processed_cases": 2,
            "skipped_cases": 0,
            "intercept_counts": {"guardrail_block": 1, "not_blocked": 1},
            "review_required_count": 1,
            "recent_results": [
                {
                    "case_id": "case-2",
                    "category": "B",
                    "intercept_type": "guardrail_block",
                    "judge_reason": "命中外部护栏模板",
                    "review_required": True,
                }
            ],
        }


class FakeAbortedBatchEvaluator:
    def __init__(self):
        self.should_stop_seen = None

    def __call__(self, config, target_client, judge, should_stop):
        self.should_stop_seen = should_stop()
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "status": "aborted",
            "stop_reason": "用户手动停止",
            "total_cases": 2,
            "processed_cases": 1,
            "skipped_cases": 0,
            "intercept_counts": {"not_blocked": 1},
            "review_required_count": 0,
            "recent_results": [
                {
                    "case_id": "case-1",
                    "category": "A",
                    "intercept_type": "not_blocked",
                    "judge_reason": "模型正常输出",
                    "review_required": False,
                }
            ],
        }


class FakeTargetClient:
    pass


class FakeJudge:
    pass


def _fake_export_batch_report(results, summary, output_file):
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"xlsx")
    return output_path


def test_start_batch_eval_runs_task_and_records_report(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_eval_service.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(batch_eval_service, "run_batch_evaluation", FakeBatchEvaluator())
    monkeypatch.setattr(batch_eval_service, "build_target_client", lambda config: FakeTargetClient())
    monkeypatch.setattr(batch_eval_service, "build_interception_judge", lambda config: FakeJudge())
    monkeypatch.setattr(batch_eval_service, "export_batch_report", _fake_export_batch_report)
    monkeypatch.setattr(batch_eval_service, "_REPORTS_ROOT", tmp_path)

    task_id = batch_eval_service.start_batch_eval({
        "dataset_paths": ["cases.csv"],
        "workers": 1,
        "repeat": 1,
        "sleep_seconds": 0,
        "retries": 0,
        "resume_from_progress": True,
        "output_file": "batch-report.xlsx",
    })

    status = batch_eval_service.get_status(task_id)
    assert status is not None
    assert status["finished"] is True
    assert status["stopped"] is False
    assert status["report"]["summary"]["status"] == "completed"
    assert status["report"]["summary"]["processed_cases"] == 2
    assert status["report"]["summary"]["review_required_count"] == 1
    assert status["report"]["summary"]["recent_results"][0]["case_id"] == "case-2"
    assert status["report"]["report_file"].endswith("batch-report.xlsx")


def test_start_batch_eval_emits_aborted_event_and_marks_task_stopped(monkeypatch, tmp_path):
    evaluator = FakeAbortedBatchEvaluator()
    monkeypatch.setattr(batch_eval_service.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(batch_eval_service, "run_batch_evaluation", evaluator)
    monkeypatch.setattr(batch_eval_service, "build_target_client", lambda config: FakeTargetClient())
    monkeypatch.setattr(batch_eval_service, "build_interception_judge", lambda config: FakeJudge())
    monkeypatch.setattr(batch_eval_service, "export_batch_report", _fake_export_batch_report)
    monkeypatch.setattr(batch_eval_service, "_REPORTS_ROOT", tmp_path)

    task_id = batch_eval_service.start_batch_eval({
        "dataset_paths": ["cases.csv"],
        "workers": 1,
        "repeat": 1,
        "sleep_seconds": 0,
        "retries": 0,
        "resume_from_progress": True,
        "output_file": "batch-report.xlsx",
    })

    status = batch_eval_service.get_status(task_id)
    assert status is not None
    assert status["finished"] is True
    assert status["stopped"] is True
    assert status["report"]["summary"]["status"] == "aborted"
    assert status["report"]["summary"]["stop_reason"] == "用户手动停止"
    assert evaluator.should_stop_seen is False

    events = list(batch_eval_service.subscribe_events(task_id))
    assert [event["event"] for event in events] == ["started", "aborted"]


def test_get_report_returns_error_when_task_not_finished(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_eval_service, "_REPORTS_ROOT", tmp_path)
    task_id = batch_eval_service._tm.create_task({"dataset_paths": ["cases.csv"]})

    report = batch_eval_service.get_report(task_id)

    assert report == {"error": "批量评估尚未完成"}


def test_get_status_includes_progress_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_eval_service, "_REPORTS_ROOT", tmp_path)
    task_id = batch_eval_service._tm.create_task({"dataset_paths": ["cases.csv"]})
    task_dir = tmp_path / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "progress.json").write_text(
        '{\n  "status": "running",\n  "total_cases": 10,\n  "result_count": 3,\n  "review_required_count": 1,\n  "current_case_id": "A-0003",\n  "last_result": {"case_id": "A-0002", "intercept_type": "not_blocked", "judge_reason": "模型正常输出"}\n}',
        encoding="utf-8",
    )

    status = batch_eval_service.get_status(task_id)

    assert status is not None
    assert status["progress"]["status"] == "running"
    assert status["progress"]["total_cases"] == 10
    assert status["progress"]["result_count"] == 3
    assert status["progress"]["review_required_count"] == 1
    assert status["progress"]["current_case_id"] == "A-0003"
    assert status["progress"]["last_result"]["case_id"] == "A-0002"


def test_list_batch_eval_tasks_returns_history_items(monkeypatch, tmp_path):
    task_manager = TaskManager()
    task_manager._tasks = {
        "task-old": {
            "task_id": "task-old",
            "config": {"dataset_paths": ["F:/datasets/old.csv"]},
            "finished": True,
            "stopped": False,
            "created_at": 1710000000.0,
            "report": {
                "report_file": "F:/reports/task-old/report.xlsx",
                "summary": {"processed_cases": 5, "status": "completed", "total_cases": 5},
            },
        },
        "task-new": {
            "task_id": "task-new",
            "config": {"dataset_paths": ["F:/datasets/new.xlsx"]},
            "finished": False,
            "stopped": False,
            "created_at": 1720000000.0,
            "report": {
                "report_file": None,
                "summary": {"processed_cases": 1, "status": "running"},
            },
        },
        "task-stopped": {
            "task_id": "task-stopped",
            "config": {"dataset_paths": ["F:/datasets/stopped.csv"]},
            "finished": True,
            "stopped": True,
            "created_at": 1730000000.0,
            "report": {
                "report_file": None,
                "summary": {"processed_cases": 2, "status": "aborted", "total_cases": 7},
            },
        },
        "task-noise": {
            "task_id": "task-noise",
            "config": {},
            "finished": True,
            "stopped": False,
            "created_at": 1740000000.0,
            "report": {},
        },
        "task-empty": {
            "task_id": "task-empty",
            "config": {"dataset_paths": ["F:/datasets/empty.csv"]},
            "finished": True,
            "stopped": False,
            "created_at": 1750000000.0,
            "report": {"report_file": None, "summary": {}},
        },
    }
    monkeypatch.setattr(batch_eval_service, "_tm", task_manager)
    monkeypatch.setattr(batch_eval_service, "_REPORTS_ROOT", tmp_path)
    running_task_dir = tmp_path / "task-new"
    running_task_dir.mkdir(parents=True, exist_ok=True)
    (running_task_dir / "progress.json").write_text(
        '{\n  "status": "running",\n  "result_count": 3,\n  "total_cases": 8,\n  "review_required_count": 1,\n  "current_case_id": "A-0003",\n  "last_result": {"case_id": "A-0002", "intercept_type": "not_blocked", "judge_reason": "模型正常输出"},\n  "updated_at": "2026-06-15T13:00:00+00:00"\n}',
        encoding="utf-8",
    )

    history = batch_eval_service.list_batch_eval_tasks(limit=3)

    assert [item["task_id"] for item in history] == ["task-stopped", "task-new", "task-old"]
    assert history[0]["status"] == "aborted"
    assert history[0]["dataset_paths"] == ["F:/datasets/stopped.csv"]
    assert history[1]["status"] == "running"
    assert history[1]["summary"]["processed_cases"] == 1
    assert history[1]["progress"]["result_count"] == 3
    assert history[1]["progress"]["total_cases"] == 8
    assert history[1]["progress"]["current_case_id"] == "A-0003"
    assert history[1]["progress"]["last_result"]["case_id"] == "A-0002"
    assert history[1]["last_updated_at"] == "2026-06-15T13:00:00+00:00"
    assert history[2]["report_file"] == "F:/reports/task-old/report.xlsx"
