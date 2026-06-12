"""健康检查 + 连通性探测路由"""

import json
import requests
from flask import Blueprint, request, jsonify

from engine.target_client import PRESET_TEMPLATES

health_bp = Blueprint("health", __name__)


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

    try:
        if method.upper() == "GET":
            resp = requests.get(api_url, headers=headers, params=body, timeout=10)
        else:
            resp = requests.post(api_url, headers=headers, json=body, timeout=10)
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
