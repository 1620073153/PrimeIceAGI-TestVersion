"""
LLM 脚本编译器
将用户粘贴的流量包编译为可执行 Python 脚本（call_target 函数）
"""

import re
from typing import Optional

from engine.llm_client import LLMClient


OUTPUT_CONTRACT = """
def call_target(prompt: str, history: list = None) -> dict:
    '''
    发送 prompt 到目标模型，返回标准化结果。

    参数:
    - prompt: 当前要发送的提示词
    - history: 可选，之前的对话历史，格式 [{"role":"user","content":"..."},{"role":"assistant","content":"..."}]
              如果目标 API 支持多轮对话（如 messages 数组），应将 history + 当前 prompt 拼接发送。
              如果目标 API 不支持多轮，忽略 history 直接发 prompt 即可。

    返回值必须包含:
    {
        "response_text": str,   # 模型回复的主要文本内容
        "reasoning_text": "",   # 思考过程（没有就留空字符串）
        "status": "success",    # "success" 或 "error"
        "error": None,          # 出错时填错误信息字符串
        "latency_ms": int,      # 请求耗时毫秒数
    }
    '''
"""

SESSION_CONTRACT = """
def create_session() -> dict:
    '''
    创建新会话，返回会话标识信息。
    返回的 dict 会传给 call_target 的第二个参数。
    '''
"""


COMPILER_SYSTEM_PROMPT = """你是 API 自动化脚本生成专家。用户会给你 HTTP 请求流量包（可能是 curl 或 raw HTTP 格式），你需要生成一个 Python 脚本。

## 严格要求

1. 脚本只能 import: requests, json, time, re
2. 必须定义 `call_target(prompt: str, history: list = None) -> dict` 函数
3. history 参数是之前的对话记录，格式: [{"role":"user","content":"..."},{"role":"assistant","content":"..."},...]
   - 如果目标 API 支持多轮（如 messages 数组），把 history + 当前 prompt 拼成完整 messages 发送
   - 如果目标 API 不支持多轮（简单问答接口），忽略 history，只发当前 prompt
4. call_target 的返回值必须严格符合以下契约:
```python
{
    "response_text": str,   # 模型回复的主要文本（必须有值）
    "reasoning_text": "",   # 思考过程，没有就空字符串
    "status": "success",    # 成功时 "success"，失败时 "error"
    "error": None,          # 成功时 None，失败时错误信息字符串
    "latency_ms": int,      # 请求耗时毫秒数（用 time.time() 计算）
}
```
5. 如果响应是 SSE 流式（text/event-stream），必须逐行读取 `data:` 行并拼接内容
6. 必须有 try/except 处理网络错误，出错时返回 status="error"
7. prompt 参数要替换到请求体中正确的位置（用户输入内容的字段）
8. 不要写 main()，不要写 print()，不要写测试代码
9. 只输出 Python 代码块，不要有任何解释文字
10. **必须使用 requests.post(url, headers=headers, json=payload) 发送请求，禁止手动拼接 JSON 字符串**。prompt 中可能包含双引号、换行符等特殊字符，手动拼接会导致 JSON 格式错误。
11. 构建 payload 时使用 Python dict，让 requests 库自动序列化，例如:
```python
payload = {"messages": [{"role": "user", "content": prompt}]}
resp = requests.post(url, headers=headers, json=payload, timeout=60)
```

## 双流量包模式

如果用户提供了"会话创建请求包"，额外定义:
```python
def create_session() -> dict:
    # 调用会话创建接口，返回会话标识信息（字段名按实际 API 来）
    # 返回值示例: {"conversation_id": "xxx"} 或 {"chat_id": "yyy", "token": "zzz"}
```

此时 call_target 签名变为:
```python
def call_target(prompt: str, session: dict = None, history: list = None) -> dict:
    # session 参数来自 create_session() 的返回值，续攻时传入同一个 session 复用会话
    # 用 session 中的标识替换请求中的会话字段（不管字段叫什么名字）
    # history 同上，如果 API 支持多轮就拼接发送
```
"""


def compile_script(
    prompt_packet: str,
    prompt_response_sample: str = "",
    session_packet: str = "",
    session_response_sample: str = "",
    llm_client: Optional[LLMClient] = None,
) -> dict:
    """
    编译流量包为 Python 脚本

    返回: {"script": str, "mode": "single"|"dual", "error": str|None}
    """
    if not llm_client:
        return {"script": "", "mode": "single", "error": "未配置辅助模型"}

    mode = "dual" if session_packet.strip() else "single"

    user_msg = _build_user_message(
        prompt_packet, prompt_response_sample,
        session_packet, session_response_sample, mode
    )

    try:
        raw = llm_client.call(
            system_prompt=COMPILER_SYSTEM_PROMPT,
            user_message=user_msg,
            temperature=0.2,
            max_tokens=4096,
        )
    except Exception as e:
        return {"script": "", "mode": mode, "error": f"LLM 调用失败: {str(e)[:200]}"}

    script = _extract_python_code(raw)
    if not script:
        return {"script": "", "mode": mode, "error": "未能从 LLM 响应中提取有效 Python 代码"}

    validation = _validate_script(script, mode)
    if validation:
        return {"script": script, "mode": mode, "error": f"脚本校验失败: {validation}"}

    return {"script": script, "mode": mode, "error": None}


def _build_user_message(
    prompt_packet: str,
    prompt_response: str,
    session_packet: str,
    session_response: str,
    mode: str,
) -> str:
    parts = []

    parts.append("## 提示词请求包\n```\n" + prompt_packet.strip() + "\n```")

    if prompt_response.strip():
        parts.append("## 提示词请求的响应示例（重要！必须根据此示例确定 response_text 的提取路径）\n```\n" + prompt_response.strip()[:2000] + "\n```")
        parts.append("⚠️ 请仔细分析上面的响应结构，从中找到包含模型回复文本的字段路径，用于提取 response_text。不要猜测，以实际响应结构为准。")

    if mode == "dual":
        parts.append("## 会话创建请求包\n```\n" + session_packet.strip() + "\n```")
        if session_response.strip():
            parts.append("## 会话创建请求的响应示例\n```\n" + session_response.strip()[:2000] + "\n```")
        parts.append("\n请生成包含 create_session() 和 call_target(prompt, session=None) 的脚本。")
    else:
        parts.append("\n请生成 call_target(prompt) 函数。")

    return "\n\n".join(parts)


def _extract_python_code(raw: str) -> str:
    """从 LLM 响应中提取 Python 代码块"""
    # 尝试提取 ```python ... ``` 代码块
    match = re.search(r"```python\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 尝试提取 ``` ... ``` 代码块
    match = re.search(r"```\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        code = match.group(1).strip()
        if "def call_target" in code:
            return code

    # 如果整个响应看起来就是代码
    if "def call_target" in raw:
        lines = raw.strip().split("\n")
        code_lines = []
        in_code = False
        for line in lines:
            if line.startswith("import ") or line.startswith("def ") or in_code:
                in_code = True
                code_lines.append(line)
        if code_lines:
            return "\n".join(code_lines)

    return ""


def _validate_script(script: str, mode: str) -> str:
    """校验脚本基本结构，返回错误信息或空字符串"""
    if "def call_target" not in script:
        return "缺少 call_target 函数定义"

    if mode == "dual" and "def create_session" not in script:
        return "双流量包模式缺少 create_session 函数定义"

    # 检查危险操作
    dangerous = ["os.system", "subprocess", "eval(", "exec(", "__import__", "open("]
    for d in dangerous:
        if d in script:
            return f"包含不允许的操作: {d}"

    # 尝试语法检查
    try:
        compile(script, "<script>", "exec")
    except SyntaxError as e:
        return f"语法错误: {e}"

    return ""
