"""
TaskManager — 任务生命周期管理
=============================
- 内存中维护活跃任务 dict
- 每次状态变更同步写入 tasks_state/ 目录的 JSON 文件
- 进程重启时从文件恢复已完成任务（运行中的标记为 interrupted）
- 自动清理超过 24 小时的任务文件
"""

import json
import time
import threading
import uuid
from pathlib import Path
from typing import Optional


_STATE_DIR = Path(__file__).resolve().parent.parent / "tasks_state"
_EXPIRY_SECONDS = 24 * 3600  # 24 hours


class TaskManager:
    """单例任务管理器"""

    _instance: Optional["TaskManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tasks: dict[str, dict] = {}
        self._task_lock = threading.Lock()
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._recover_from_disk()
        self._start_cleanup_timer()

    # ─── Public API ─────────────────────────────────────────

    def create_task(self, config: dict) -> str:
        """创建任务，返回 task_id"""
        task_id = uuid.uuid4().hex[:12]
        task = {
            "task_id": task_id,
            "config": config,
            "current_round": 0,
            "finished": False,
            "stopped": False,
            "orchestrator": None,
            "report": None,
            "created_at": time.time(),
        }
        with self._task_lock:
            self._tasks[task_id] = task
        self._persist(task_id)
        return task_id

    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务信息"""
        with self._task_lock:
            return self._tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs) -> bool:
        """更新任务字段"""
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task.update(kwargs)
        self._persist(task_id)
        return True

    def stop_task(self, task_id: str) -> bool:
        """停止任务"""
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task["stopped"] = True
            orch = task.get("orchestrator")
        if orch:
            orch.stop()
        self._persist(task_id)
        return True

    def list_tasks(self) -> list[dict]:
        """列出所有任务（不含 orchestrator 对象和 config 敏感字段）"""
        result = []
        with self._task_lock:
            for tid, t in self._tasks.items():
                result.append({
                    "task_id": tid,
                    "current_round": t.get("current_round", 0),
                    "finished": t.get("finished", False),
                    "stopped": t.get("stopped", False),
                    "created_at": t.get("created_at"),
                    "has_report": t.get("report") is not None,
                })
        return result

    # ─── Persistence ────────────────────────────────────────

    def _persist(self, task_id: str):
        """将任务状态写入磁盘 JSON"""
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            serializable = {
                "task_id": task_id,
                "current_round": task.get("current_round", 0),
                "finished": task.get("finished", False),
                "stopped": task.get("stopped", False),
                "created_at": task.get("created_at"),
                "report": task.get("report"),
                "config": {k: v for k, v in task.get("config", {}).items()
                           if "api_key" not in k.lower()},
            }
        filepath = _STATE_DIR / f"{task_id}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _recover_from_disk(self):
        """从磁盘恢复任务状态（仅恢复已完成的报告，运行中标记 interrupted）"""
        for filepath in _STATE_DIR.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                task_id = data.get("task_id", filepath.stem)
                # 如果上次没完成，标记为中断
                if not data.get("finished"):
                    data["finished"] = True
                    data["stopped"] = True
                    data["report"] = data.get("report") or {
                        "error": "任务被中断（进程重启）"
                    }
                data["orchestrator"] = None
                with self._task_lock:
                    self._tasks[task_id] = data
            except (json.JSONDecodeError, OSError):
                continue

    def _start_cleanup_timer(self):
        """定时清理过期任务文件（每小时检查一次）"""
        def cleanup():
            now = time.time()
            expired = []
            with self._task_lock:
                for tid, t in list(self._tasks.items()):
                    if t.get("finished") and (now - t.get("created_at", 0)) > _EXPIRY_SECONDS:
                        expired.append(tid)
                for tid in expired:
                    del self._tasks[tid]
            for tid in expired:
                fp = _STATE_DIR / f"{tid}.json"
                try:
                    fp.unlink(missing_ok=True)
                except OSError:
                    pass
            # 重新调度
            timer = threading.Timer(3600, cleanup)
            timer.daemon = True
            timer.start()

        timer = threading.Timer(3600, cleanup)
        timer.daemon = True
        timer.start()
