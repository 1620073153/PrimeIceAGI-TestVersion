"""
知识库 JSON 持久化层
kb_data/kb1.json — TC260-003 五大类三十一小类
kb_data/kb2.json — 9 个绕过概念
kb_data/kb3.json — 12 种绕过方法 + 信号映射 + 概念方法映射
kb_data/kb4.json — 用户高命中率注入模板 (初始空)
kb_data/kb5.json — Agent3 推测的系统提示词边界 (自动填充)
"""

import json
import os
import tempfile
import time

from pathlib import Path

from data.tc260_standards import CATEGORIES, CLUSTERS
from data.bypass_knowledge import BYPASS_CONCEPTS, BYPASS_METHODS, SIGNAL_STRATEGY_MAP, CONCEPT_METHOD_MAP


_KB_DEFAULTS = {
    "kb1": lambda: {"categories": CATEGORIES, "clusters": CLUSTERS},
    "kb2": lambda: {"concepts": BYPASS_CONCEPTS},
    "kb3": lambda: {
        "methods": BYPASS_METHODS,
        "signal_strategy_map": SIGNAL_STRATEGY_MAP,
        "concept_method_map": CONCEPT_METHOD_MAP,
    },
    "kb4": lambda: {"templates": {}},
    "kb5": lambda: {"inferences": []},
}

_KB_LEGACY_FILENAMES = {
    "kb1": "kb1_standards.json",
    "kb2": "kb2_concepts.json",
    "kb3": "kb3_methods.json",
    "kb4": "kb4_injection_templates.json",
    "kb5": "kb5_inferred_boundaries.json",
}


def _canonical_filename(kb_id: str) -> str:
    return f"{kb_id}.json"


def _kb_path(kb_id: str) -> str:
    return os.path.join(get_data_dir(), _canonical_filename(kb_id))


def _fallback_data(kb_id: str) -> dict:
    return _KB_DEFAULTS.get(kb_id, lambda: {})()


def get_data_dir() -> str:
    """返回 kb_data/ 目录的绝对路径，不存在则创建"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kb_data")
    os.makedirs(path, exist_ok=True)
    return path


def _atomic_write(filepath: str, data: dict):
    """原子写入：先写临时文件再 os.replace"""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(filepath), suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, filepath)
    except Exception:
        os.unlink(tmp)
        raise


def _load_json_file(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _migrate_legacy_file(kb_id: str) -> bool:
    data_dir = get_data_dir()
    canonical_path = os.path.join(data_dir, _canonical_filename(kb_id))
    if os.path.exists(canonical_path):
        return True

    legacy_filename = _KB_LEGACY_FILENAMES.get(kb_id)
    if not legacy_filename:
        return False

    legacy_path = os.path.join(data_dir, legacy_filename)
    if not os.path.exists(legacy_path):
        return False

    try:
        data = _load_json_file(legacy_path)
    except (json.JSONDecodeError, OSError):
        return False

    _atomic_write(canonical_path, data)
    return True


def ensure_seed_files():
    """
    首次启动时，从 Python 硬编码数据生成所有 5 个权威 JSON 文件。
    如果旧命名文件存在且新文件不存在，先迁移旧文件。
    如果权威文件已存在，不覆盖。
    """
    data_dir = get_data_dir()

    for kb_id, get_default in _KB_DEFAULTS.items():
        if _migrate_legacy_file(kb_id):
            continue
        filepath = os.path.join(data_dir, _canonical_filename(kb_id))
        if not os.path.exists(filepath):
            _atomic_write(filepath, get_default())


def load_kb(kb_id: str) -> dict:
    """
    加载知识库 JSON，损坏或缺失时回退到 Python 模块数据。
    kb_id 可以是: kb1, kb2, kb3, kb4, kb5
    """
    try:
        _migrate_legacy_file(kb_id)
        return _load_json_file(_kb_path(kb_id))
    except (FileNotFoundError, json.JSONDecodeError):
        return _fallback_data(kb_id)
    except Exception:
        return _fallback_data(kb_id)


def save_kb(kb_id: str, data: dict) -> bool:
    """保存 KB1-KB4 到 JSON 文件。KB5 请使用 save_kb5_inference。"""
    if kb_id == "kb5":
        return False
    try:
        _atomic_write(_kb_path(kb_id), data)
        return True
    except Exception as e:
        print(f"[kb_store] save_kb({kb_id}) failed: {e}")
        return False


def _legacy_kb_path(kb_id: str) -> Path | None:
    legacy_filename = _KB_LEGACY_FILENAMES.get(kb_id)
    if not legacy_filename:
        return None
    return Path(get_data_dir()) / legacy_filename


def kb5_file_path() -> Path:
    return Path(_kb_path("kb5"))


def kb5_exists() -> bool:
    canonical = kb5_file_path()
    legacy = _legacy_kb_path("kb5")
    return canonical.exists() or bool(legacy and legacy.exists())


def delete_kb5_file() -> str:
    canonical = kb5_file_path()
    legacy = _legacy_kb_path("kb5")
    targets = []
    if canonical.exists():
        targets.append(canonical)
    if legacy and legacy.exists() and legacy != canonical:
        targets.append(legacy)
    if not targets:
        return "already_deleted"
    for path in targets:
        path.unlink()
    return "deleted"


def _cleanup_legacy_kb_file(kb_id: str) -> None:
    legacy = _legacy_kb_path(kb_id)
    canonical = Path(_kb_path(kb_id))
    if legacy and legacy.exists() and legacy != canonical:
        legacy.unlink()


def load_kb5() -> dict:
    """加载 KB5（推测的系统提示词边界）"""
    data = load_kb("kb5")
    if "inferences" not in data:
        data["inferences"] = []
    return data


def save_kb5_inference(inference: dict) -> bool:
    """
    将一条新的推测记录追加到 KB5。
    保留最近 50 条，超出则截断。
    """
    try:
        data = load_kb5()
        inferences = data.get("inferences", [])
        inferences.append(inference)
        if len(inferences) > 50:
            inferences = inferences[-50:]
        data["inferences"] = inferences
        _atomic_write(_kb_path("kb5"), data)
        _cleanup_legacy_kb_file("kb5")
        return True
    except Exception as e:
        print(f"[kb_store] save_kb5_inference failed: {e}")
        return False


def delete_kb5_inference(inference_id: str) -> bool:
    """删除指定 ID 的推测记录"""
    try:
        data = load_kb5()
        inferences = data.get("inferences", [])
        data["inferences"] = [inf for inf in inferences if inf.get("inference_id") != inference_id]
        _atomic_write(_kb_path("kb5"), data)
        _cleanup_legacy_kb_file("kb5")
        return True
    except Exception as e:
        print(f"[kb_store] delete_kb5_inference failed: {e}")
        return False


def kb_meta(kb_id: str) -> dict:
    """返回知识库元数据"""
    data = load_kb(kb_id)

    if kb_id == "kb1":
        cats = data.get("categories", {})
        total = sum(len(c.get("subcategories", {})) for c in cats.values())
        return {"kb_id": kb_id, "name": "TC260-003 安全标准", "entry_count": len(cats), "total_items": total}
    elif kb_id == "kb2":
        concepts = data.get("concepts", {})
        return {"kb_id": kb_id, "name": "绕过概念库", "entry_count": len(concepts)}
    elif kb_id == "kb3":
        methods = data.get("methods", {})
        return {"kb_id": kb_id, "name": "绕过方法库", "entry_count": len(methods)}
    elif kb_id == "kb4":
        templates = data.get("templates", {})
        return {"kb_id": kb_id, "name": "高命中率注入模板", "entry_count": len(templates)}
    elif kb_id == "kb5":
        inferences = data.get("inferences", [])
        return {"kb_id": kb_id, "name": "推测的系统提示词边界", "entry_count": len(inferences)}
    return {"kb_id": kb_id, "name": "未知", "entry_count": 0}


def get_sessions_dir() -> str:
    """返回 sessions/ 目录的绝对路径"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sessions")
    os.makedirs(path, exist_ok=True)
    return path


def save_session(session_id: str, session_data: dict) -> bool:
    """保存测试会话到 sessions/<session_id>.json"""
    try:
        filepath = os.path.join(get_sessions_dir(), f"{session_id}.json")
        session_data.setdefault("saved_at", time.time())
        _atomic_write(filepath, session_data)
        return True
    except Exception as e:
        print(f"[kb_store] save_session({session_id}) failed: {e}")
        return False


def list_sessions() -> list[dict]:
    """列出所有会话（仅元数据，不含完整报告）"""
    sessions = []
    sessions_dir = get_sessions_dir()
    try:
        for filename in os.listdir(sessions_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(sessions_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            report = data.get("report", {})
            sessions.append({
                "session_id": data.get("session_id", filename.replace(".json", "")),
                "created_at": data.get("created_at", 0),
                "saved_at": data.get("saved_at", 0),
                "config": {
                    k: data.get("config", {}).get(k, "")
                    for k in ("agent_model", "target_model", "max_rounds")
                },
                "total_rounds": report.get("total_rounds", 0),
                "total_bypassed": report.get("total_bypassed", 0),
                "coverage_rate": report.get("coverage_rate", "0%"),
                "best_bypass_rate": report.get("best_bypass_rate", "0%"),
                "covered_count": report.get("coverage_count", 0),
                "stopped_by_user": report.get("stopped_by_user", False),
            })
    except OSError:
        pass
    sessions.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    return sessions


def load_session(session_id: str) -> dict | None:
    """加载完整的测试会话"""
    filepath = os.path.join(get_sessions_dir(), f"{session_id}.json")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def delete_session(session_id: str) -> bool:
    """删除测试会话"""
    filepath = os.path.join(get_sessions_dir(), f"{session_id}.json")
    try:
        os.unlink(filepath)
        return True
    except OSError:
        return False
