"""Batch evaluation service — validate, create, run, report."""

import json
import threading
import time
from pathlib import Path

from backend.event_bus import EventBus
from backend.task_manager import TaskManager
from data.batch_progress_store import BatchProgressStore
from data.dataset_loader import load_datasets
from engine.batch_evaluator import run_batch_evaluation
from engine.batch_models import BatchEvalConfig, GuardrailSignature
from engine.llm_client import LLMClient
from engine.report_exporter import export_report
from engine.target_client import TargetClient

_tm = TaskManager()
_bus = EventBus()
_REPORTS_ROOT = Path(__file__).resolve().parent.parent.parent / "reports" / "batch"


class _TargetClientAdapter:
    def __init__(self, client: TargetClient):
        self._client = client

    def call_single(self, prompt_text: str) -> str:
        result = self._client.call_single(prompt_text)
        if result.get("error"):
            raise RuntimeError(f"目标API调用失败: {result['error']}")
        return result.get("response_text", "")


def start_batch_eval(raw_config: dict) -> str:
    validated = _validate_config(raw_config)
    task_id = _tm.create_task(validated)
    threading.Thread(target=_run, args=(task_id,), daemon=True).start()
    return task_id


def resume_batch_eval(task_id: str, credentials: dict) -> str:
    """复用旧 task_id 的 output_dir 和 config，重启 _run 线程"""
    task = _tm.get_task(task_id)
    if not task:
        raise ValueError("任务不存在")
    if not task.get("finished"):
        raise ValueError("任务仍在运行中，无需续跑")

    # 重置任务状态（让 TaskManager 认为它可以再次运行）
    _tm.reset_task(task_id)

    # 合并 credentials 到内存中的 config（不落盘）
    cfg = task["config"]
    cfg["target_api_key"] = credentials.get("target_api_key", "")
    cfg["agent_api_key"] = credentials.get("agent_api_key", "")
    # 可选：允许前端覆盖 api_url / model（用于修改后重跑）
    if credentials.get("target_api_url"):
        cfg["target_api_url"] = credentials["target_api_url"]
    if credentials.get("agent_api_url"):
        cfg["agent_api_url"] = credentials["agent_api_url"]

    # 清理旧的 EventBus channel，让下次 publish 创建新 channel
    _bus.cleanup(task_id)

    # 启动 _run 线程（复用同一个 task_id -> 同一个 output_dir）
    threading.Thread(target=_run, args=(task_id,), daemon=True).start()
    return task_id


def get_status(task_id: str) -> dict | None:
    task = _tm.get_task(task_id)
    if not task:
        return None
    progress = _load_progress(task_id)
    return {
        "task_id": task_id,
        "finished": task.get("finished", False),
        "stopped": task.get("stopped", False),
        "report": task.get("report"),
        "progress": progress,
    }


def list_batch_eval_tasks(limit: int = 20) -> list[dict]:
    tasks = []
    for task_id, task in sorted(
        _tm._tasks.items(),
        key=lambda item: item[1].get("created_at", 0),
        reverse=True,
    ):
        cfg = task.get("config", {})
        # 优先用 task_type 区分；兼容旧任务用 black_dataset_paths 判断
        if cfg.get("task_type") != "batch_eval" and not cfg.get("black_dataset_paths"):
            continue
        progress = _load_progress(task_id)
        report = task.get("report") or {}
        tasks.append({
            "task_id": task_id,
            "status": _derive_status(task, progress),
            "created_at": task.get("created_at"),
            "last_updated_at": progress.get("updated_at") if progress else None,
            "dataset_paths": task.get("config", {}).get("black_dataset_paths", []),
            "report_file": report.get("report_file"),
            "progress": progress,
            "summary": report.get("summary"),
            "config_summary": {
                "mode": task.get("config", {}).get("mode"),
                "target_api_url": task.get("config", {}).get("target_api_url"),
                "target_model": task.get("config", {}).get("target_model"),
                "agent_api_url": task.get("config", {}).get("agent_api_url"),
                "agent_model": task.get("config", {}).get("agent_model"),
                "template_name": task.get("config", {}).get("template_name"),
                "workers": task.get("config", {}).get("workers"),
            },
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
    if not candidate.exists() or not candidate.is_file():
        return None
    if task_dir.resolve() not in candidate.parents and candidate != task_dir.resolve():
        return None
    return candidate


def export_current_report(task_id: str) -> dict | None:
    """从已有的 results.jsonl 生成 XLSX 报告（运行中或停止后均可调用）"""
    task = _tm.get_task(task_id)
    if not task:
        return None

    output_dir = _REPORTS_ROOT / task_id
    results_file = output_dir / "results.jsonl"
    if not results_file.exists():
        return None

    from engine.batch_models import BatchEvalResult, InterceptType

    results = []
    try:
        with results_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    intercept_type = InterceptType(data.get("intercept_type", "not_blocked"))
                    results.append(BatchEvalResult(
                        case_id=data.get("case_id", ""),
                        prompt_text=data.get("prompt_text", ""),
                        response_text=data.get("response_text", ""),
                        intercept_type=intercept_type,
                        confidence=data.get("confidence", 0.0),
                        reason=data.get("reason", ""),
                        review_required=data.get("review_required", False),
                        expected_label=data.get("expected_label", "block"),
                        is_correct=data.get("is_correct", False),
                        category=data.get("category"),
                        category_name=data.get("category_name"),
                        elapsed_ms=data.get("elapsed_ms", 0),
                        error=data.get("error"),
                        repeat_index=data.get("repeat_index", 1),
                        subcategory=data.get("subcategory"),
                        bypass_technique=data.get("bypass_technique"),
                    ))
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue
    except OSError:
        return None

    if not results:
        return None

    cfg = task.get("config", {})
    mode = cfg.get("mode", "guardrail")
    output_filename = Path(cfg.get("output_file", "batch-report.xlsx")).name
    report_path = str(output_dir / output_filename)
    export_report(results=results, mode=mode, output_path=report_path)

    from engine.batch_statistics import compute_statistics, format_summary
    stats = compute_statistics(results, mode)
    summary = format_summary(stats)
    summary["processed_cases"] = len(results)

    filename = Path(report_path).name
    download_url = f"/api/batch-eval/{task_id}/download/{filename}"

    return {
        "report_file": report_path,
        "download_url": download_url,
        "summary": summary,
    }


def stop_batch_eval(task_id: str) -> bool:
    return _tm.stop_task(task_id)


def subscribe_events(task_id: str):
    task = _tm.get_task(task_id)
    if not task:
        return None
    return _bus.subscribe(task_id, from_beginning=True)


def _validate_config(raw: dict) -> dict:
    if not raw.get("black_dataset_paths") and not raw.get("dataset_paths"):
        raise ValueError("缺少数据集路径")
    if not raw.get("target_api_url"):
        raise ValueError("缺少目标模型 API 地址")

    config = dict(raw)
    if "dataset_paths" in config and "black_dataset_paths" not in config:
        config["black_dataset_paths"] = config.pop("dataset_paths")
    config.setdefault("white_dataset_paths", [])
    config.setdefault("mode", "guardrail")
    config.setdefault("guardrail_signatures", [])
    config.setdefault("exclude_categories", [])
    config.setdefault("workers", 4)
    config.setdefault("repeat", 1)
    config.setdefault("retries", 3)
    config.setdefault("sleep_seconds", 1.0)
    config.setdefault("resume_from_progress", True)
    config.setdefault("enable_llm_judge", True)
    config.setdefault("output_file", "batch-report.xlsx")
    config["task_type"] = "batch_eval"
    return config


def _build_eval_config(cfg: dict) -> BatchEvalConfig:
    signatures = []
    for sig in cfg.get("guardrail_signatures", []):
        if isinstance(sig, dict) and sig.get("pattern"):
            signatures.append(GuardrailSignature(
                type=sig.get("type", "text_contains"),
                pattern=sig["pattern"],
            ))

    return BatchEvalConfig(
        mode=cfg.get("mode", "guardrail"),
        guardrail_signatures=signatures,
        black_dataset_paths=cfg.get("black_dataset_paths", []),
        white_dataset_paths=cfg.get("white_dataset_paths", []),
        workers=cfg.get("workers", 4),
        repeat=cfg.get("repeat", 1),
        retries=cfg.get("retries", 3),
        sleep_seconds=cfg.get("sleep_seconds", 1.0),
        resume_from_progress=cfg.get("resume_from_progress", True),
        enable_llm_judge=cfg.get("enable_llm_judge", True),
        output_file=cfg.get("output_file", "batch-report.xlsx"),
        target_api_base=cfg.get("target_api_url", ""),
        target_api_key=cfg.get("target_api_key", ""),
        target_model=cfg.get("target_model", ""),
        judge_api_base=cfg.get("agent_api_url", ""),
        judge_api_key=cfg.get("agent_api_key", ""),
        judge_model=cfg.get("agent_model", ""),
    )


def _build_target_client(cfg: dict) -> _TargetClientAdapter:
    target_config = {
        "api_url": cfg["target_api_url"],
        "api_key": cfg["target_api_key"],
        "model": cfg.get("target_model", "deepseek-chat"),
        "template_name": cfg.get("template_name", "openai_compatible"),
    }
    if cfg.get("template_name") == "custom":
        target_config.update({
            "method": cfg.get("method", "POST"),
            "headers": cfg.get("headers", {}),
            "body": cfg.get("body", {}),
            "response_path": cfg.get("response_path", {"content": "", "reasoning": ""}),
            "timeout": cfg.get("timeout", 120),
        })
    for key in ("temperature", "top_p"):
        if key in cfg:
            target_config[key] = cfg[key]
    return _TargetClientAdapter(TargetClient(target_config))


def _build_llm_judge_client(cfg: dict) -> LLMClient | None:
    if not cfg.get("enable_llm_judge", True):
        return None
    if not (cfg.get("agent_api_url") and cfg.get("agent_api_key")):
        return None
    return LLMClient(
        api_url=cfg["agent_api_url"],
        api_key=cfg["agent_api_key"],
        model=cfg.get("agent_model", "deepseek-chat"),
        rate_limit=10.0,
        timeout=30.0,
        backoff_429=60.0,
    )


def _run(task_id: str):
    task = _tm.get_task(task_id)
    if not task:
        return
    cfg = task["config"]
    output_dir = _REPORTS_ROOT / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    def emit(event: str, **kwargs):
        payload = {"event": event, "timestamp": time.time()}
        payload.update(kwargs)
        _bus.publish(task_id, payload)

    def should_stop() -> bool:
        t = _tm.get_task(task_id)
        return bool(t and t.get("stopped", False))

    try:
        emit("started", task_id=task_id)
        eval_config = _build_eval_config(cfg)
        target_client = _build_target_client(cfg)
        llm_judge = _build_llm_judge_client(cfg)
        progress_store = BatchProgressStore(output_dir)

        black_cases = load_datasets(
            paths=eval_config.black_dataset_paths,
            default_expected_label="block",
            exclude_categories=cfg.get("exclude_categories"),
        )
        white_cases = load_datasets(
            paths=eval_config.white_dataset_paths,
            default_expected_label="allow",
            exclude_categories=cfg.get("exclude_categories"),
        ) if eval_config.white_dataset_paths else []

        all_cases = black_cases + white_cases
        progress_store.set_total_cases(len(all_cases))
        progress_store.mark_started()

        def on_progress(result):
            emit("progress", case_id=result.case_id, intercept_type=result.intercept_type.value,
                 is_correct=result.is_correct, category=result.category,
                 category_name=result.category_name, reason=result.reason)

        results = run_batch_evaluation(
            cases=all_cases,
            config=eval_config,
            target_client=target_client,
            progress_store=progress_store,
            on_progress=on_progress,
            should_stop=should_stop,
            llm_judge_client=llm_judge,
        )


        # 续跑场景：从 results.jsonl 加载之前积累的结果，合并后生成完整报告
        results_file = output_dir / "results.jsonl"
        if results_file.exists() and eval_config.resume_from_progress:
            existing_results = _load_existing_results(results_file, len(results))
            if existing_results:
                all_results = existing_results + results
            else:
                all_results = results
        else:
            all_results = results

        report_path = str(output_dir / Path(eval_config.output_file).name)
        export_report(results=all_results, mode=eval_config.mode, output_path=report_path)

        from engine.batch_statistics import compute_statistics, format_summary
        stats = compute_statistics(all_results, eval_config.mode)
        summary = format_summary(stats)

        summary["processed_cases"] = len(all_results)
        summary["review_required_count"] = sum(1 for r in all_results if r.review_required)
        summary["skipped_cases"] = 0
        intercept_counts = {}
        for r in all_results:
            key = r.intercept_type.value
            intercept_counts[key] = intercept_counts.get(key, 0) + 1
        summary["intercept_counts"] = intercept_counts
        summary["recent_results"] = [
            {"case_id": r.case_id, "category": r.category,
             "category_name": r.category_name,
             "intercept_type": r.intercept_type.value, "is_correct": r.is_correct,
             "reason": r.reason}
            for r in all_results[-10:]
        ]

        report = {
            "summary": summary,
            "report_file": report_path,
            "total_results": len(all_results),
        }

        if should_stop():
            _tm.update_task(task_id, report=report, stopped=True)
            emit("aborted", report=report)
        else:
            _tm.update_task(task_id, report=report)
            emit("complete", report=report)

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        error_msg = f"批量评估异常: {str(exc)[:300]}"
        emit("error", message=error_msg)
        # Write error to progress store for debugging
        progress_file = _REPORTS_ROOT / task_id / "progress.json"
        if progress_file.exists():
            import json as _json
            try:
                p = _json.loads(progress_file.read_text(encoding="utf-8"))
                p["status"] = "error"
                p["error_message"] = f"{error_msg}\n{tb[-500:]}"
                progress_file.write_text(_json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
    finally:
        _tm.update_task(task_id, finished=True)
        # 延迟清理 EventBus channel，给前端 SSE 留出读取时间
        threading.Timer(300, lambda: _bus.cleanup(task_id)).start()


def _load_existing_results(results_file: Path, current_count: int) -> list:
    """从 results.jsonl 加载之前续跑积累的旧结果（不含本次新增的）"""
    from engine.batch_models import BatchEvalResult, InterceptType
    all_lines = []
    try:
        with results_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                all_lines.append(line)
    except OSError:
        return []

    # 旧结果 = 全部行数 - 本次运行的结果数
    old_count = len(all_lines) - current_count
    if old_count <= 0:
        return []

    old_results = []
    for line in all_lines[:old_count]:
        try:
            data = json.loads(line)
            intercept_type = InterceptType(data.get("intercept_type", "not_blocked"))
            old_results.append(BatchEvalResult(
                case_id=data.get("case_id", ""),
                prompt_text=data.get("prompt_text", ""),
                response_text=data.get("response_text", ""),
                intercept_type=intercept_type,
                confidence=data.get("confidence", 0.0),
                reason=data.get("reason", ""),
                review_required=data.get("review_required", False),
                expected_label=data.get("expected_label", "block"),
                is_correct=data.get("is_correct", False),
                category=data.get("category"),
                category_name=data.get("category_name"),
                elapsed_ms=data.get("elapsed_ms", 0),
                error=data.get("error"),
                repeat_index=data.get("repeat_index", 1),
                subcategory=data.get("subcategory"),
                bypass_technique=data.get("bypass_technique"),
            ))
        except (json.JSONDecodeError, ValueError, KeyError):
            continue
    return old_results


def _load_progress(task_id: str) -> dict | None:
    progress_file = _REPORTS_ROOT / task_id / "progress.json"
    if not progress_file.exists():
        return None
    return BatchProgressStore(progress_file.parent).load_progress()


def _derive_status(task: dict, progress: dict | None) -> str:
    if task.get("stopped"):
        return "aborted"
    if task.get("finished"):
        return "completed"
    return "running"
