"""Knowledge base CRUD business logic with concurrency protection."""

import time
import threading
from data.kb_store import load_kb, save_kb, kb_meta, load_kb5, delete_kb5_inference, kb5_exists, delete_kb5_file
from data.tc260_standards import CATEGORIES
from data.bypass_knowledge import BYPASS_CONCEPTS, BYPASS_METHODS
from engine.target_client import PRESET_TEMPLATES
from backend.schemas import validate_kb_entry, ValidationError
from backend.task_manager import TaskManager

_kb_lock = threading.Lock()
_kb5_name = "推测的系统提示词边界"


def find_running_kb5_task_id() -> str | None:
    tm = TaskManager()
    for task in tm.list_tasks():
        if task.get("finished"):
            continue
        full_task = tm.get_task(task.get("task_id", "")) or {}
        config = full_task.get("config", {})
        if bool(config.get("agent3_enabled", True)):
            return task.get("task_id")
    return None


def get_kb5_state() -> dict:
    task_id = find_running_kb5_task_id()
    return {
        "kb_code": "KB5",
        "name": _kb5_name,
        "exists": kb5_exists(),
        "in_use": bool(task_id),
        "task_id": task_id,
    }


def delete_kb5() -> dict:
    task_id = find_running_kb5_task_id()
    if task_id:
        raise ValidationError("KB5 正在被测试任务使用，请先停止任务或等待完成后再删除")
    with _kb_lock:
        status = delete_kb5_file()
    return {
        "kb_code": "KB5",
        "name": _kb5_name,
        "status": status,
    }


def get_standards() -> dict:
    return {
        "categories": {
            k: {
                "name": v["name"],
                "priority": v["priority"],
                "subcategories": v["subcategories"],
                "sub_count": len(v["subcategories"]),
            }
            for k, v in CATEGORIES.items()
        },
        "total_subcategories": 31,
    }


def get_concepts() -> dict:
    return {
        "concepts": {
            k: {"name": v["name"], "layer": v["layer"], "principle": v["principle"]}
            for k, v in BYPASS_CONCEPTS.items()
        },
        "total": len(BYPASS_CONCEPTS),
    }


def get_methods() -> dict:
    return {
        "methods": {
            k: {"name": v["name"], "category": v["category"], "description": v["description"]}
            for k, v in BYPASS_METHODS.items()
        },
        "total": len(BYPASS_METHODS),
    }


def get_templates() -> dict:
    templates = {}
    for key, tpl in PRESET_TEMPLATES.items():
        templates[key] = {
            "name": tpl.get("name", key),
            "description": tpl.get("description", ""),
            "method": tpl.get("method", "POST"),
        }
    return {"templates": templates}


def list_kbs() -> list[dict]:
    return [kb_meta(k) for k in ["kb1", "kb2", "kb3", "kb4", "kb5"]]


def get_kb_data(kb_id: str) -> dict:
    if kb_id not in ("kb1", "kb2", "kb3", "kb4", "kb5"):
        raise ValidationError("无效的知识库 ID")
    return load_kb(kb_id)


def create_entry(kb_id: str, new_entry: dict) -> None:
    validate_kb_entry(kb_id, new_entry)
    with _kb_lock:
        data = load_kb(kb_id)
        if kb_id == "kb1":
            key = new_entry["key"]
            if "categories" not in data:
                data["categories"] = {}
            data["categories"][key] = {k: v for k, v in new_entry.items() if k != "key"}
        elif kb_id == "kb4":
            templates = data.get("templates", {})
            entry_id = new_entry.get("entry_id", "") or f"tpl_{len(templates) + 1:03d}"
            new_entry.setdefault("created_at", time.time())
            new_entry.setdefault("updated_at", time.time())
            templates[entry_id] = {k: v for k, v in new_entry.items() if k != "entry_id"}
            data["templates"] = templates
        else:
            key = new_entry["key"]
            container_key = "concepts" if kb_id == "kb2" else "methods"
            if container_key not in data:
                data[container_key] = {}
            data[container_key][key] = {k: v for k, v in new_entry.items() if k != "key"}
        save_kb(kb_id, data)


def update_entry(kb_id: str, entry_key: str, updates: dict) -> None:
    if kb_id == "kb5":
        raise ValidationError("KB5 由 Agent3 自动填充，不可手动编辑")
    if kb_id not in ("kb1", "kb2", "kb3", "kb4"):
        raise ValidationError("无效的知识库 ID")
    with _kb_lock:
        data = load_kb(kb_id)
        if kb_id == "kb1":
            container = data.get("categories", {})
        elif kb_id == "kb4":
            container = data.get("templates", {})
        elif kb_id == "kb2":
            container = data.get("concepts", {})
        else:
            container = data.get("methods", {})
        if entry_key not in container:
            raise ValidationError(f"条目 {entry_key} 不存在")
        container[entry_key].update({k: v for k, v in updates.items() if k not in ("key", "entry_id")})
        if kb_id == "kb4":
            container[entry_key]["updated_at"] = time.time()
        save_kb(kb_id, data)


def delete_entry(kb_id: str, entry_key: str) -> None:
    if kb_id == "kb5":
        raise ValidationError("请使用 delete_kb5_inference 删除 KB5 记录")
    if kb_id not in ("kb1", "kb2", "kb3", "kb4"):
        raise ValidationError("无效的知识库 ID")
    with _kb_lock:
        data = load_kb(kb_id)
        if kb_id == "kb1":
            container = data.get("categories", {})
        elif kb_id == "kb4":
            container = data.get("templates", {})
        elif kb_id == "kb2":
            container = data.get("concepts", {})
        else:
            container = data.get("methods", {})
        if entry_key not in container:
            raise ValidationError(f"条目 {entry_key} 不存在")
        del container[entry_key]
        save_kb(kb_id, data)


def delete_inference(inference_id: str) -> bool:
    return delete_kb5_inference(inference_id)
