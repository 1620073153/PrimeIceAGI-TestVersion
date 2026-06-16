"""Test task business logic — validate, create, run, persist."""

import time
import threading
from engine.orchestrator import RedTeamOrchestrator
from engine.claude_agent import validate_claude_ready_for_start
from backend.task_manager import TaskManager
from backend.event_bus import EventBus
from backend.schemas import validate_test_config, ValidationError
from data.kb_store import save_session

_tm = TaskManager()
_bus = EventBus()
EVENT_BUS_CLEANUP_DELAY_SECONDS = 300


def _schedule_event_bus_cleanup(task_id: str):
    timer = threading.Timer(EVENT_BUS_CLEANUP_DELAY_SECONDS, _bus.cleanup, args=(task_id,))
    timer.daemon = True
    timer.start()


def start_test(config: dict) -> str:
    config = validate_test_config(config)
    preflight = validate_claude_ready_for_start(config)
    if not preflight["ok"]:
        raise ValidationError(preflight["message"])
    task_id = _tm.create_task(config)
    thread = threading.Thread(target=_run, args=(task_id,), daemon=True)
    thread.start()
    return task_id


def stop_test(task_id: str) -> bool:
    return _tm.stop_task(task_id)


def get_status(task_id: str) -> dict | None:
    task = _tm.get_task(task_id)
    if not task:
        return None
    orch = task.get("orchestrator")
    return {
        "task_id": task_id,
        "current_round": orch.current_round if orch else 0,
        "finished": task["finished"],
        "report": task.get("report"),
    }


def get_report(task_id: str) -> dict | None:
    task = _tm.get_task(task_id)
    if not task:
        return None
    if not task.get("finished"):
        return {"error": "测试尚未完成"}
    return task.get("report", {})


def subscribe_events(task_id: str):
    task = _tm.get_task(task_id)
    if not task:
        return None
    return _bus.subscribe(task_id, from_beginning=True)


def _run(task_id: str):
    task = _tm.get_task(task_id)
    if not task:
        return
    cfg = task["config"]

    def emit(event_or_dict, **kwargs):
        if isinstance(event_or_dict, dict):
            payload = event_or_dict
            payload.setdefault("timestamp", time.time())
        else:
            payload = {"event": event_or_dict, "timestamp": time.time()}
            payload.update(kwargs)
        _bus.publish(task_id, payload)

    try:
        orch = RedTeamOrchestrator(cfg, event_callback=emit)
        _tm.update_task(task_id, orchestrator=orch)
        report = orch.run()
        _tm.update_task(task_id, report=report)
        save_session(task_id, {
            "session_id": task_id,
            "created_at": task.get("created_at"),
            "finished_at": time.time(),
            "config": {k: v for k, v in cfg.items() if "api_key" not in k.lower()},
            "report": report,
        })
    except Exception as e:
        emit("error", message=f"测试异常: {str(e)[:300]}")
    finally:
        _tm.update_task(task_id, finished=True, current_round=None)
        _schedule_event_bus_cleanup(task_id)
