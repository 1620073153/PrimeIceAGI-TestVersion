"""
请求智能解析器
支持三种输入格式：curl 命令 / raw HTTP 请求（抓包） / 纯 JSON
确定性解析 + LLM 辅助识别 prompt 插入点
"""

import copy
import json
import re
import shlex
from typing import Optional

from engine.llm_client import LLMClient


# 常见承载用户输入的字段名
_PROMPT_FIELD_NAMES = {
    "answer", "query", "input", "text", "prompt", "content",
    "question", "message", "user_input", "user_message",
    "v_laws", "instruction", "request", "ask",
}


def smart_parse(raw_text: str, llm_client: Optional[LLMClient] = None) -> dict:
    """
    统一入口：自动检测格式 → 解析 → 识别 prompt 插入点 → 生成模板

    支持的输入格式：
    1. curl 命令
    2. raw HTTP 请求（Burp/DevTools/抓包）
    3. 纯 JSON body（需要额外提供 URL）
    """
    text = raw_text.strip()
    fmt = _detect_format(text)

    if fmt == "curl":
        parsed = _parse_curl(text)
    elif fmt == "http_raw":
        parsed = _parse_http_raw(text)
    else:
        parsed = {"method": "POST", "url": "", "headers": {}, "body": _try_parse_json(text), "stream": False}

    parsed["detected_format"] = fmt
    parsed = identify_prompt_slot(parsed, llm_client)
    return build_template_config(parsed)


def parse_curl(curl_text: str) -> dict:
    """兼容旧调用：解析 curl 命令"""
    return _parse_curl(curl_text)


def identify_prompt_slot(parsed: dict, llm_client: Optional[LLMClient] = None) -> dict:
    """
    识别 body 中 prompt 的插入点，返回带 {{prompt}} 占位符的模板

    策略：
    1. messages 数组中最后一个 user role 的 content
    2. 常见 prompt 字段名匹配（answer/query/input/text 等）
    3. LLM 辅助标注
    """
    body = parsed.get("body")
    if not isinstance(body, dict):
        return parsed

    slot_found = _rule_based_slot(body)
    if slot_found:
        parsed["body"] = slot_found
        parsed["prompt_slot_method"] = "rule"
        return parsed

    if llm_client:
        llm_result = _llm_identify_slot(body, llm_client)
        if llm_result:
            parsed["body"] = llm_result
            parsed["prompt_slot_method"] = "llm"
            return parsed

    parsed["prompt_slot_method"] = "manual"
    return parsed


def build_template_config(parsed: dict) -> dict:
    """将解析结果转换为 TargetClient 可用的模板配置"""
    response_path = _guess_response_path(parsed)

    return {
        "template_name": "custom",
        "api_url": parsed["url"],
        "method": parsed["method"],
        "headers": parsed["headers"],
        "body": parsed["body"],
        "stream": parsed.get("stream", False),
        "response_path": response_path,
        "timeout": 120,
        "detected_format": parsed.get("detected_format", ""),
    }


def parse_and_build(raw_text: str, llm_client: Optional[LLMClient] = None) -> dict:
    """一步到位（旧接口兼容）"""
    return smart_parse(raw_text, llm_client)


# ============================================================
# 格式检测
# ============================================================

def _detect_format(text: str) -> str:
    """自动检测输入格式"""
    first_line = text.split("\n")[0].strip()

    if first_line.lower().startswith("curl "):
        return "curl"

    # raw HTTP: 首行是 METHOD /path HTTP/x.x 或 METHOD /path
    if re.match(r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+\S+", first_line, re.IGNORECASE):
        return "http_raw"

    # 可能是纯 JSON
    if text.lstrip().startswith("{"):
        return "json"

    return "curl"


# ============================================================
# curl 解析
# ============================================================

def _parse_curl(curl_text: str) -> dict:
    text = curl_text.strip()
    text = re.sub(r"\\\s*\n", " ", text)
    text = re.sub(r"\s+", " ", text)

    if text.lower().startswith("curl "):
        text = text[5:]

    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = _fallback_tokenize(text)

    method = "GET"
    url = ""
    headers = {}
    data_raw = ""

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()
        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                hdr = tokens[i]
                colon_idx = hdr.find(":")
                if colon_idx > 0:
                    key = hdr[:colon_idx].strip()
                    val = hdr[colon_idx + 1:].strip()
                    headers[key] = val
        elif tok in ("-d", "--data", "--data-raw", "--data-binary"):
            i += 1
            if i < len(tokens):
                data_raw = tokens[i]
                if method == "GET":
                    method = "POST"
        elif not tok.startswith("-") and not url:
            url = tok
        i += 1

    body = _try_parse_json(data_raw)
    stream = False
    if isinstance(body, dict):
        stream = body.get("stream", False) or body.get("response_mode") == "streaming"

    if "Content-Type" not in headers and "content-type" not in headers:
        if isinstance(body, dict):
            headers["Content-Type"] = "application/json"

    return {
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "raw_body": data_raw if not isinstance(body, dict) else "",
        "stream": stream,
    }


# ============================================================
# raw HTTP 请求解析（抓包/Burp/DevTools 格式）
# ============================================================

def _parse_http_raw(raw_text: str) -> dict:
    """
    解析 raw HTTP 请求格式：
    POST /path HTTP/1.1
    Host: example.com
    Header: value
    ...

    {json body}
    """
    lines = raw_text.split("\n")
    first_line = lines[0].strip()

    # 解析请求行: METHOD /path HTTP/x.x
    match = re.match(r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(\S+)(?:\s+HTTP/\S+)?$", first_line, re.IGNORECASE)
    if not match:
        return {"method": "POST", "url": "", "headers": {}, "body": {}, "stream": False}

    method = match.group(1).upper()
    path = match.group(2)

    # 解析 headers（直到空行）
    headers = {}
    body_start_idx = len(lines)
    host = ""

    for i in range(1, len(lines)):
        line = lines[i].rstrip("\r")
        if not line.strip():
            body_start_idx = i + 1
            break
        colon_idx = line.find(":")
        if colon_idx > 0:
            key = line[:colon_idx].strip()
            val = line[colon_idx + 1:].strip()
            if key.lower() == "host":
                host = val
            else:
                headers[key] = val

    # 解析 body（空行之后的所有内容）
    body_raw = "\n".join(lines[body_start_idx:]).strip()
    body = _try_parse_json(body_raw) if body_raw else {}

    # 构造完整 URL
    scheme = "https"
    if host and ("localhost" in host or "127.0.0.1" in host or ":9080" in host or ":8080" in host):
        scheme = "http"
    url = f"{scheme}://{host}{path}" if host else path

    # 过滤掉不需要转发的 hop-by-hop / 浏览器专属 headers
    skip_headers = {
        "host", "accept-encoding", "connection", "cookie", "priority",
        "user-agent", "accept-language", "content-length", "origin",
        "referer", "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site",
    }
    headers = {k: v for k, v in headers.items() if k.lower() not in skip_headers}

    stream = False
    if isinstance(body, dict):
        stream = body.get("stream", False) or body.get("response_mode") == "streaming"
    # Accept: text/event-stream 也暗示 SSE
    for k, v in headers.items():
        if k.lower() == "accept" and "event-stream" in v.lower():
            stream = True
            break

    return {
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "raw_body": body_raw if not isinstance(body, dict) else "",
        "stream": stream,
    }


# ============================================================
# 工具函数
# ============================================================

def _fallback_tokenize(text: str) -> list[str]:
    """shlex 解析失败时的回退分词"""
    tokens = []
    current = ""
    in_quote = None
    for ch in text:
        if ch in ('"', "'") and not in_quote:
            in_quote = ch
        elif ch == in_quote:
            in_quote = None
        elif ch == " " and not in_quote:
            if current:
                tokens.append(current)
                current = ""
            continue
        current += ch
    if current:
        tokens.append(current)
    return tokens


def _try_parse_json(raw: str) -> dict | str:
    """尝试解析 JSON，失败返回原始字符串"""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        cleaned = raw.strip("'\"")
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return raw


def _rule_based_slot(body: dict) -> Optional[dict]:
    """
    规则匹配 prompt 插入点：
    1. messages 数组中最后一个 role=user 的 content
    2. 顶层或嵌套中命中已知 prompt 字段名（answer/query/input 等）
    3. inputs 子对象中的字符串字段
    """
    result = copy.deepcopy(body)

    # 策略 1: messages 格式
    if "messages" in result and isinstance(result["messages"], list):
        messages = result["messages"]
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, dict) and msg.get("role") == "user":
                msg["content"] = "{{prompt}}"
                return result

    # 策略 2: 顶层字段名匹配
    for key in result:
        if key.lower() in _PROMPT_FIELD_NAMES and isinstance(result[key], str) and len(result[key]) > 0:
            result[key] = "{{prompt}}"
            return result

    # 策略 3: inputs/params 子对象中的字符串字段
    for container_key in ("inputs", "params", "parameters", "data"):
        container = result.get(container_key)
        if isinstance(container, dict):
            for key in container:
                if isinstance(container[key], str) and len(container[key]) > 0:
                    # 优先匹配已知字段名
                    if key.lower() in _PROMPT_FIELD_NAMES:
                        container[key] = "{{prompt}}"
                        return result
            # 没有精确匹配，取第一个非空字符串字段
            for key in container:
                if isinstance(container[key], str) and len(container[key]) > 0:
                    container[key] = "{{prompt}}"
                    return result

    return None


def _llm_identify_slot(body: dict, llm_client: LLMClient) -> Optional[dict]:
    """LLM 辅助标注 prompt 插入点"""
    system = """你是 API 请求分析专家。用户会给你一个 JSON request body，
你需要找到其中"用户输入内容"应该被替换的位置，用 {{prompt}} 标记。

规则：
- 找到承载用户自然语言输入的字段（通常是 content/query/input/text/prompt 等）
- 只替换一个位置（最终用户输入的那个）
- system prompt 不要替换
- 返回完整的修改后 JSON，不要加任何解释"""

    user_msg = f"请分析这个 request body，标注 {{{{prompt}}}} 插入点：\n```json\n{json.dumps(body, ensure_ascii=False, indent=2)}\n```"

    try:
        resp = llm_client.call(system, user_msg, temperature=0.1, max_tokens=2048)
        json_match = re.search(r"```json\s*(.*?)\s*```", resp, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        cleaned = resp.strip()
        if cleaned.startswith("{"):
            return json.loads(cleaned)
    except Exception:
        pass
    return None


def _guess_response_path(parsed: dict) -> dict:
    """根据 URL 和 body 结构猜测响应解析路径"""
    url = parsed.get("url", "")
    body = parsed.get("body", {})

    if "chat/completions" in url or (isinstance(body, dict) and "messages" in body):
        return {
            "content": "choices.0.message.content",
            "reasoning": "choices.0.message.reasoning_content",
        }

    if "/v1/messages" in url:
        return {
            "content": "content.0.text",
            "reasoning": "",
        }

    # 非标准 API：SSE 流式响应通常没有固定路径，留空让用户确认
    # 或返回常见的 answer/result/data 路径
    if isinstance(body, dict) and "inputs" in body:
        return {"content": "data.outputs.text", "reasoning": ""}

    return {"content": "", "reasoning": ""}
