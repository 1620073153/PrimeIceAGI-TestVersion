"""Test control routes — thin layer delegating to test_service."""

import json
from flask import Blueprint, request, Response
from backend.services import test_service
from backend.response import ok, err
from backend.schemas import ValidationError

test_bp = Blueprint("test", __name__)


@test_bp.route("/api/test/start", methods=["POST"])
def start_test():
    try:
        config = request.get_json(force=True)
        task_id = test_service.start_test(config)
        return ok({"task_id": task_id})
    except ValidationError as e:
        return err(e.message, 400)


@test_bp.route("/api/test/latest")
def latest_task():
    task = test_service.get_latest_task()
    if not task:
        return ok(None)
    return ok(task)


@test_bp.route("/api/test/<task_id>/stream")
def stream(task_id: str):
    events = test_service.subscribe_events(task_id)
    if events is None:
        return err("任务不存在或已过期", 404)

    def generate():
        for event in events:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("event") in ("complete", "aborted", "error"):
                break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@test_bp.route("/api/test/<task_id>/status")
def task_status(task_id: str):
    status = test_service.get_status(task_id)
    if not status:
        return err("任务不存在", 404)
    return ok(status)


@test_bp.route("/api/test/<task_id>/stop", methods=["POST"])
def stop_test(task_id: str):
    if not test_service.stop_test(task_id):
        return err("任务不存在", 404)
    return ok({"status": "stopped"})


@test_bp.route("/api/test/<task_id>/report")
def get_report(task_id: str):
    report = test_service.get_report(task_id)
    if report is None:
        return err("任务不存在", 404)
    if "error" in report:
        return err(report["error"], 400)
    return ok(report)


@test_bp.route("/api/parse-curl", methods=["POST"])
def parse_curl_endpoint():
    """解析请求文本（curl / raw HTTP / JSON），返回结构化模板配置"""
    data = request.get_json(force=True)
    raw_text = data.get("curl", "").strip()
    use_llm = data.get("use_llm", True)

    if not raw_text:
        return err("请提供 curl 命令或 HTTP 请求文本", 400)

    llm_client = None
    if use_llm and data.get("agent_api_url") and data.get("agent_api_key"):
        from engine.llm_client import LLMClient
        try:
            llm_client = LLMClient(
                api_url=data["agent_api_url"],
                api_key=data["agent_api_key"],
                model=data.get("agent_model", "deepseek-chat"),
                rate_limit=5.0,
                timeout=30.0,
            )
        except Exception:
            pass

    from engine.curl_parser import smart_parse
    try:
        config = smart_parse(raw_text, llm_client)
    except Exception as e:
        return err(f"解析失败: {str(e)[:200]}", 400)

    if not config.get("api_url"):
        return err("未能提取到 API 地址，请检查输入格式", 400)

    return ok(config)


@test_bp.route("/api/compile-script", methods=["POST"])
def compile_script_endpoint():
    """将流量包编译为可执行 Python 脚本"""
    data = request.get_json(force=True)

    prompt_packet = data.get("prompt_packet", "").strip()
    if not prompt_packet:
        return err("请提供提示词请求包", 400)

    agent_url = data.get("agent_api_url", "").strip()
    agent_key = data.get("agent_api_key", "").strip()
    if not agent_url or not agent_key:
        return err("请先配置辅助模型（攻击侧 LLM）的 API 地址和 Key", 400)

    from engine.llm_client import LLMClient
    from engine.script_compiler import compile_script

    try:
        llm_client = LLMClient(
            api_url=agent_url,
            api_key=agent_key,
            model=data.get("agent_model", "deepseek-chat"),
            rate_limit=5.0,
            timeout=60.0,
        )
    except Exception as e:
        return err(f"辅助模型连接失败: {str(e)[:200]}", 400)

    result = compile_script(
        prompt_packet=prompt_packet,
        prompt_response_sample=data.get("prompt_response", ""),
        session_packet=data.get("session_packet", ""),
        session_response_sample=data.get("session_response", ""),
        llm_client=llm_client,
    )

    if result["error"]:
        return err(result["error"], 400)

    return ok({"script": result["script"], "mode": result["mode"]})


@test_bp.route("/api/test-fire", methods=["POST"])
def test_fire_script():
    """试射：用测试 prompt 执行编译脚本，验证响应提取是否正确"""
    data = request.get_json(force=True)
    compiled_script = data.get("compiled_script", "").strip()
    if not compiled_script:
        return err("无编译脚本", 400)

    script_mode = data.get("script_mode", "single")
    test_prompt = data.get("test_prompt", "你好")

    from engine.script_target_client import ScriptTargetClient

    try:
        client = ScriptTargetClient({
            "compiled_script": compiled_script,
            "script_mode": script_mode,
        })
    except RuntimeError as e:
        return err(f"脚本加载失败: {str(e)[:300]}", 400)

    result = client.call_single(prompt=test_prompt, prompt_id="test-fire")

    if result.get("response_text"):
        return ok({
            "response_text": result["response_text"][:500],
            "latency_ms": result.get("latency_ms", 0),
            "status": "success",
        })

    # 响应为空 — 尝试用 LLM 修正提取逻辑
    raw = result.get("raw_response")
    raw_sample = ""
    if raw and isinstance(raw, dict):
        raw_sample = json.dumps(raw, ensure_ascii=False)[:1000]
    elif result.get("error"):
        raw_sample = str(result["error"])[:500]

    agent_url = data.get("agent_api_url", "").strip()
    agent_key = data.get("agent_api_key", "").strip()

    if agent_url and agent_key and raw_sample:
        from engine.llm_client import LLMClient
        try:
            llm = LLMClient(
                api_url=agent_url,
                api_key=agent_key,
                model=data.get("agent_model", "deepseek-chat"),
                rate_limit=5.0,
                timeout=60.0,
            )
            fix_result = _try_fix_extraction(compiled_script, raw_sample, script_mode, llm)
            if fix_result:
                return ok({
                    "response_text": "",
                    "fix_applied": True,
                    "fixed_script": fix_result,
                    "raw_response_sample": raw_sample,
                })
        except Exception:
            pass

    return ok({
        "response_text": "",
        "error": result.get("error") or "response_text 为空，提取路径可能有误",
        "raw_response_sample": raw_sample,
        "status": "empty",
    })


def _try_fix_extraction(script: str, raw_response: str, mode: str, llm) -> str:
    """让 LLM 根据实际响应修正脚本的提取逻辑"""
    prompt = f"""以下 Python 脚本用于调用目标 API 并提取响应，但试射时 response_text 返回为空。

## 当前脚本
```python
{script}
```

## 实际原始响应（截取）
```
{raw_response}
```

请修正脚本中的响应提取逻辑，使 response_text 能正确提取到模型回复内容。
只输出修正后的完整 Python 脚本（```python 代码块），不要解释。
保持函数签名和其他逻辑不变，只修正提取部分。"""

    import re
    try:
        raw_out = llm.call(
            system_prompt="你是 Python 脚本修正专家。只输出修正后的代码，不要解释。",
            user_message=prompt,
            temperature=0.2,
            max_tokens=4096,
        )
        match = re.search(r"```python\s*(.*?)\s*```", raw_out, re.DOTALL)
        if match and "def call_target" in match.group(1):
            return match.group(1).strip()
    except Exception:
        pass
    return ""
