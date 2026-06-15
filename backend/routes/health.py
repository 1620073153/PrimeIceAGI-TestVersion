"""健康检查 + 连通性探测 + Claude智能体配置路由"""

import json
import os
import requests
from flask import Blueprint, request, jsonify

from engine.target_client import PRESET_TEMPLATES
from engine.claude_agent import AGENT_HOME

health_bp = Blueprint("health", __name__)

AGENT_SETTINGS_PATH = os.path.join(AGENT_HOME, ".claude", "settings.json")


@health_bp.route("/api/health")
def health():
    return jsonify({"status": "ok", "server": "PrimeIceAGI v2"})


@health_bp.route("/api/probe", methods=["POST"])
def probe_target():
    """测试待测模型连通性"""
    data: dict = request.get_json(force=True)
    api_url = data.get("api_url", "").rstrip("/")
    api_key = data.get("api_key", "")
    model = data.get("model", "deepseek-chat")
    template_name = data.get("template_name", "openai_compatible")

    if not api_url or not api_key:
        return jsonify({"reachable": False, "error": "缺少 API 地址或 Key"})

    if template_name == "custom":
        method = data.get("method", "POST")
        headers = data.get("headers", {})
        body = data.get("body", {})
    else:
        preset = PRESET_TEMPLATES.get(template_name, PRESET_TEMPLATES["openai_compatible"])
        method = preset["method"]
        headers = dict(preset["headers"])
        body = dict(preset["body"])
        ep = preset.get("endpoint", "")
        if ep and not api_url.endswith(ep):
            api_url = api_url + ep

    # 渲染变量
    for k, v in headers.items():
        headers[k] = str(v).replace("{{api_key}}", api_key)
    if isinstance(body, dict):
        body_str = json.dumps(body)
        body_str = body_str.replace("{{api_key}}", api_key)
        body_str = body_str.replace("{{model}}", model)
        body_str = body_str.replace("{{prompt}}", "Hello, this is a connectivity test.")
        body = json.loads(body_str)
        if "temperature" in data:
            body["temperature"] = data["temperature"]
        if "top_p" in data:
            body["top_p"] = data["top_p"]

    try:
        if method.upper() == "GET":
            resp = requests.get(api_url, headers=headers, params=body, timeout=10)
        else:
            resp = requests.post(api_url, headers=headers, json=body, timeout=10)

        if resp.status_code == 401:
            return jsonify({"reachable": False, "status_code": 401, "error": "认证失败 (401) — API Key 无效或过期"})
        if resp.status_code == 403:
            return jsonify({"reachable": False, "status_code": 403, "error": "权限不足 (403) — 无权访问该端点"})
        if resp.status_code >= 500:
            return jsonify({"reachable": False, "status_code": resp.status_code, "error": f"服务端错误 ({resp.status_code})"})

        return jsonify({
            "reachable": True,
            "status_code": resp.status_code,
            "response_preview": (resp.text or "")[:300],
        })
    except requests.exceptions.ConnectionError:
        return jsonify({"reachable": False, "error": "连接被拒绝 — 请检查 API 地址"})
    except requests.exceptions.Timeout:
        return jsonify({"reachable": False, "error": "连接超时 (10s)"})
    except Exception as e:
        return jsonify({"reachable": False, "error": str(e)[:200]})


@health_bp.route("/api/claude-agent/config", methods=["GET"])
def get_claude_agent_config():
    """读取 Claude 智能体配置"""
    try:
        with open(AGENT_SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        env = settings.get("env", {})
        return jsonify({
            "ok": True,
            "data": {
                "url": env.get("ANTHROPIC_BASE_URL", ""),
                "key": env.get("ANTHROPIC_AUTH_TOKEN", ""),
                "model": env.get("ANTHROPIC_MODEL", ""),
            }
        })
    except FileNotFoundError:
        return jsonify({"ok": True, "data": {"url": "", "key": "", "model": ""}})


@health_bp.route("/api/claude-agent/config", methods=["POST"])
def save_claude_agent_config():
    """保存 Claude 智能体配置"""
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    key = data.get("key", "").strip()
    model = data.get("model", "").strip()

    if not url or not key or not model:
        return jsonify({"ok": False, "error": "URL/Key/Model 均为必填"}), 400

    settings = {"env": {
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_BASE_URL": url,
        "ANTHROPIC_MODEL": model,
    }, "permissions": {"allow": []}}

    os.makedirs(os.path.dirname(AGENT_SETTINGS_PATH), exist_ok=True)
    with open(AGENT_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "message": "已保存"})
