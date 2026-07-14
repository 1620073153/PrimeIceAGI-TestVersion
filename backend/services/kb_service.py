"""Knowledge base CRUD business logic with concurrency protection."""

import time
import threading
from data.kb_store import load_kb, save_kb, kb_meta, load_kb5, delete_kb5_inference, kb5_exists, delete_kb5_file
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
    from data.kb_store import load_kb
    kb1 = load_kb("kb1")
    categories = kb1.get("categories", {})
    total = sum(len(v.get("subcategories", {})) for v in categories.values())
    return {
        "categories": {
            k: {"name": v["name"], "priority": v.get("priority", "P1"),
                "subcategories": v.get("subcategories", {}), "sub_count": len(v.get("subcategories", {}))}
            for k, v in categories.items()
        },
        "total_subcategories": total,
    }


def get_concepts() -> dict:
    return {
        "concepts": {
            k: {"layer": v.get("layer", ""), "principle": v.get("principle", "")}
            for k, v in BYPASS_CONCEPTS.items()
        },
        "total": len(BYPASS_CONCEPTS),
    }


def get_methods() -> dict:
    return {
        "methods": {
            k: {"category": v.get("category", ""), "description": v.get("description", "")}
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
            entry_id = new_entry.get("entry_id", "").strip() or new_entry.get("key", "").strip()
            if not entry_id:
                # 自动递增 ID: t01, t02, ...
                existing_nums = []
                for k in templates.keys():
                    if k.startswith("t") and k[1:].isdigit():
                        existing_nums.append(int(k[1:]))
                next_num = max(existing_nums, default=0) + 1
                entry_id = f"t{next_num:02d}"
            new_entry.setdefault("created_at", time.time())
            new_entry.setdefault("updated_at", time.time())
            # 只保留 template_text + 时间戳
            templates[entry_id] = {
                "template_text": new_entry.get("template_text", ""),
                "created_at": new_entry.get("created_at"),
                "updated_at": new_entry.get("updated_at"),
            }
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
        if kb_id == "kb4":
            # KB4 简化：只更新 template_text
            container[entry_key]["template_text"] = updates.get("template_text", container[entry_key].get("template_text", ""))
            container[entry_key]["updated_at"] = time.time()
        else:
            container[entry_key].update({k: v for k, v in updates.items() if k not in ("key", "entry_id")})
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
