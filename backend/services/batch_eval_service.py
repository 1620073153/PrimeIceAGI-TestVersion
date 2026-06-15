"""Batch evaluation task service — validate, create, run, persist."""

import threading
import time
from pathlib import Path

from backend.event_bus import EventBus
from backend.task_manager import TaskManager
from data.batch_progress_store import BatchProgressStore
from engine.batch_evaluator import run_batch_evaluation
from engine.batch_models import BatchEvalConfig
from engine.llm_client import LLMClient
from engine.report_exporter import export_batch_report
from engine.response_judge import judge_interception
from engine.target_client import TargetClient

_tm = TaskManager()
_bus = EventBus()
_REPORTS_ROOT = Path(__file__).resolve().parent.parent.parent / "reports" / "batch"


class BatchInterceptionJudge:
    def __init__(self, llm_client: LLMClient | None):
        self._llm_client = llm_client

    def judge_interception(self, prompt_text: str, response_text: str, regex_labels: list[str]) -> dict:
        if self._llm_client is None:
            return {
                "intercept_type": "uncertain",
                "confidence": 0.5,
                "reason": "未配置裁判模型，回退为不确定",
            }
        return judge_interception(
            prompt_text=prompt_text,
            response_text=response_text,
            regex_labels=regex_labels,
            llm_client=self._llm_client,
        )


class BatchTargetClient:
    def __init__(self, client: TargetClient):
        self._client = client

    def generate(self, prompt_text: str) -> str:
        result = self._client.call_single(prompt_text)
        return result.get("response_text", "")


def start_batch_eval(config: dict) -> str:
    normalized = validate_batch_eval_config(config)
    task_id = _tm.create_task(normalized)
    thread = threading.Thread(target=_run, args=(task_id,), daemon=True)
    thread.start()
    return task_id


def get_status(task_id: str) -> dict | None:
    task = _tm.get_task(task_id)
    if not task:
        return None
    progress = _load_progress_snapshot(task_id)
    return {
        "task_id": task_id,
        "finished": task.get("finished", False),
        "stopped": task.get("stopped", False),
        "report": task.get("report"),
        "progress": progress,
    }


def list_batch_eval_tasks(limit: int = 20) -> list[dict]:
    tasks = []
    for task_id, task in sorted(_tm._tasks.items(), key=lambda item: item[1].get("created_at", 0), reverse=True):
        report = task.get("report") or {}
        summary = report.get("summary") or {}
        finished = task.get("finished", False)
        stopped = task.get("stopped", False)
        progress = _load_progress_snapshot(task_id)
        status = summary.get("status") or (progress or {}).get("status")
        if not status:
            status = "aborted" if stopped else ("completed" if finished else "running")
        if not task.get("config", {}).get("dataset_paths"):
            continue
        if not report and not progress and status == "completed":
            continue
        if finished and not stopped and not progress and not summary and not report.get("report_file"):
            continue
        tasks.append({
            "task_id": task_id,
            "status": status,
            "created_at": task.get("created_at"),
            "report_file": report.get("report_file"),
            "summary": summary,
            "progress": progress,
            "last_updated_at": (progress or {}).get("updated_at"),
            "dataset_paths": task.get("config", {}).get("dataset_paths", []),
        })
        if len(tasks) >= limit:
            break
    return tasks


def get_report(task_id: str) -> dict | None:
    task = _tm.get_task(task_id)
    if not task:
        return None
    if not task.get("finished"):
        return {"error": "批量评估尚未完成"}
    return task.get("report", {})


def resolve_download_file(task_id: str, filename: str) -> Path | None:
    task_dir = _REPORTS_ROOT / task_id
    candidate = (task_dir / Path(filename).name).resolve()
    try:
        if task_dir.resolve() not in candidate.parents and candidate != task_dir.resolve():
            return None
    except FileNotFoundError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def stop_batch_eval(task_id: str) -> bool:
    return _tm.stop_task(task_id)


def subscribe_events(task_id: str):
    task = _tm.get_task(task_id)
    if not task:
        return None
    return _bus.subscribe(task_id, from_beginning=True)


def build_target_client(config: dict) -> BatchTargetClient:
    target_config = {
        "api_url": config["target_api_url"],
        "api_key": config["target_api_key"],
        "model": config.get("target_model", "deepseek-chat"),
        "template_name": config.get("template_name", "openai_compatible"),
    }
    if config.get("template_name") == "custom":
        target_config.update({
            "method": config.get("method", "POST"),
            "headers": config.get("headers", {}),
            "body": config.get("body", {}),
            "response_path": config.get("response_path", {"content": "", "reasoning": ""}),
            "timeout": config.get("timeout", 120),
        })
    for key in ("temperature", "top_p"):
        if key in config:
            target_config[key] = config[key]
    return BatchTargetClient(TargetClient(target_config))


def build_interception_judge(config: dict) -> BatchInterceptionJudge:
    if not config.get("enable_llm_judge", True):
        return BatchInterceptionJudge(None)
    if not (config.get("agent_api_url") and config.get("agent_api_key")):
        return BatchInterceptionJudge(None)
    llm_client = LLMClient(
        api_url=config["agent_api_url"],
        api_key=config["agent_api_key"],
        model=config.get("agent_model", "deepseek-chat"),
        rate_limit=10.0,
        timeout=30.0,
        backoff_429=60.0,
    )
    return BatchInterceptionJudge(llm_client)


def validate_batch_eval_config(config: dict) -> dict:
    if not config.get("dataset_paths"):
        raise ValueError("缺少 dataset_paths")
    if not config.get("target_api_url"):
        config["target_api_url"] = "http://127.0.0.1/mock"
    if not config.get("target_api_key"):
        config["target_api_key"] = "mock-key"

    normalized = dict(config)
    normalized.setdefault("exclude_categories", [])
    normalized.setdefault("workers", 1)
    normalized.setdefault("repeat", 1)
    normalized.setdefault("sleep_seconds", 0)
    normalized.setdefault("retries", 0)
    normalized.setdefault("resume_from_progress", True)
    normalized.setdefault("output_file", "batch-report.xlsx")
    normalized.setdefault("enable_llm_judge", True)
    normalized.setdefault("template_name", "openai_compatible")
    return normalized


def _run(task_id: str):
    task = _tm.get_task(task_id)
    if not task:
        return
    cfg = task["config"]
    output_dir = _REPORTS_ROOT / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg["output_dir"] = str(output_dir)

    def emit(event_or_dict, **kwargs):
        if isinstance(event_or_dict, dict):
            payload = event_or_dict
            payload.setdefault("timestamp", time.time())
        else:
            payload = {"event": event_or_dict, "timestamp": time.time()}
            payload.update(kwargs)
        _bus.publish(task_id, payload)

    def should_stop() -> bool:
        current_task = _tm.get_task(task_id)
        if not current_task:
            return False
        return bool(current_task.get("stopped", False))

    try:
        emit("started", task_id=task_id)
        target_client = build_target_client(cfg)
        judge = build_interception_judge(cfg)
        summary = run_batch_evaluation(
            config=BatchEvalConfig(**{
                "dataset_paths": cfg["dataset_paths"],
                "exclude_categories": cfg.get("exclude_categories", []),
                "workers": cfg.get("workers", 1),
                "repeat": cfg.get("repeat", 1),
                "sleep_seconds": cfg.get("sleep_seconds", 0),
                "retries": cfg.get("retries", 0),
                "resume_from_progress": cfg.get("resume_from_progress", True),
                "output_dir": cfg["output_dir"],
                "output_file": cfg.get("output_file", "batch-report.xlsx"),
                "enable_llm_judge": cfg.get("enable_llm_judge", True),
            }),
            target_client=target_client,
            judge=judge,
            should_stop=should_stop,
        )

        report_file = output_dir / cfg.get("output_file", "batch-report.xlsx")
        results = _load_results(output_dir / "results.jsonl")
        export_batch_report(results=results, summary=summary, output_file=report_file)

        report = {
            "summary": summary,
            "report_file": str(report_file),
            "output_dir": str(output_dir),
        }

        if summary.get("status") == "aborted":
            _tm.update_task(task_id, report=report, stopped=True)
            emit("aborted", report=report, reason=summary.get("stop_reason"))
        else:
            _tm.update_task(task_id, report=report)
            emit("complete", report=report)
    except Exception as exc:
        emit("error", message=f"批量评估异常: {str(exc)[:300]}")
    finally:
        _tm.update_task(task_id, finished=True)


def _load_progress_snapshot(task_id: str) -> dict | None:
    progress_file = _REPORTS_ROOT / task_id / "progress.json"
    if not progress_file.exists():
        return None
    return BatchProgressStore(progress_file.parent).load_progress()


def _load_results(results_file: Path):
    import json
    from engine.batch_models import BatchEvalResult, InterceptType

    if not results_file.exists():
        return []

    results = []
    for line in results_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        data["intercept_type"] = InterceptType(data["intercept_type"])
        results.append(BatchEvalResult(**data))
    return results
