# PrimeIceAGI 架构设计方案

> 日期: 2026-06-11
> 范围: 后端分层重构 + 深挖引擎逐轮动态生成模式

---

## 一、目标

1. 补齐缺失的服务层，让路由层只做请求解析和响应组装
2. 统一参数校验、响应格式、错误处理
3. 深挖引擎改为逐轮动态生成——每轮发完收到回复后，再基于完整对话历史 + KB5 生成下一轮攻击

---

## 二、后端分层架构

### 2.1 请求链路（改造后）

```
HTTP 请求进入
    ↓
middleware.py (@before_request)         ← 认证 + 限流
    ↓
backend/routes/*.py                     ← 解析参数 → 调 service → 返统一响应
    ↓
backend/services/*.py                   ← 业务编排：校验→调 engine/data→组装结果
    ↓
engine/*  或  data/*                    ← 纯逻辑 / 纯数据访问
    ↓
backend/response.py                     ← 统一包装 JSON 响应
```

### 2.2 新增文件

| 文件 | 职责 |
|------|------|
| `backend/services/__init__.py` | 包标记 |
| `backend/services/test_service.py` | 测试任务业务编排：校验配置→创建任务→启动后台线程→管理生命周期 |
| `backend/services/kb_service.py` | 知识库 CRUD：权限判断→加载→变换→保存（含并发锁） |
| `backend/services/session_service.py` | 历史会话：列表→详情→删除 |
| `backend/schemas.py` | 参数校验函数集（`validate_test_config()`、`validate_kb_entry()` 等） |
| `backend/response.py` | 统一响应工具：`ok(data)` → `{"ok":true, "data":...}`、`err(msg, code)` → `{"ok":false, "error":...}` |

### 2.3 修改文件

| 文件 | 改动 |
|------|------|
| `app.py` | 新增 `@app.errorhandler(Exception)` 全局错误处理→JSON |
| `backend/routes/test.py` | 精简为 ~40 行：解析请求→调 `test_service`→返统一响应 |
| `backend/routes/kb.py` | 精简为 ~60 行：解析请求→调 `kb_service`→返统一响应 |
| `backend/routes/sessions.py` | 精简为 ~30 行：调 `session_service`→返统一响应 |

### 2.4 统一响应格式

```python
# backend/response.py
from flask import jsonify

def ok(data=None):
    """成功响应"""
    body = {"ok": True}
    if data is not None:
        body["data"] = data
    return jsonify(body)

def err(message: str, status_code: int = 400):
    """错误响应"""
    return jsonify({"ok": False, "error": message}), status_code
```

> 注意：SSE stream 和 probe 等特殊端点不套这个格式，保持原样。
> 前端需要适配新格式（加一层 `if resp.ok then resp.data` 的判断）。

### 2.5 全局错误处理

```python
# app.py 中新增
@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return err(e.description, e.code)
    return err(f"服务器内部错误: {str(e)[:200]}", 500)
```

### 2.6 参数校验示例

```python
# backend/schemas.py
class ValidationError(Exception):
    def __init__(self, message: str):
        self.message = message

def validate_test_config(config: dict) -> dict:
    """校验+填充默认值，失败抛 ValidationError"""
    required = ["agent_api_url", "agent_api_key", "target_api_url", "target_api_key"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        raise ValidationError(f"缺少必填参数: {', '.join(missing)}")
    
    if config.get("template_name") == "custom":
        if not config.get("headers"):
            raise ValidationError("自定义模板需要填写 Headers")
        if not config.get("body"):
            raise ValidationError("自定义模板需要填写 Body")
    
    # 默认值
    config.setdefault("agent_model", "deepseek-chat")
    config.setdefault("target_model", "deepseek-chat")
    config.setdefault("max_rounds", 5)
    config.setdefault("cooldown_no_new", 2)
    config.setdefault("template_name", "openai_compatible")
    return config
```

### 2.7 test_service.py 核心结构

```python
# backend/services/test_service.py
import threading
from engine.orchestrator import RedTeamOrchestrator
from backend.task_manager import TaskManager
from backend.event_bus import EventBus
from backend.schemas import validate_test_config, ValidationError
from data.kb_store import save_session

_tm = TaskManager()
_bus = EventBus()

def start_test(config: dict) -> str:
    """校验配置→创建任务→启动后台线程→返回 task_id"""
    config = validate_test_config(config)
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

def _run(task_id: str):
    """后台线程：运行测试"""
    task = _tm.get_task(task_id)
    cfg = task["config"]

    def emit(event_or_dict, **kwargs):
        if isinstance(event_or_dict, dict):
            payload = event_or_dict
        else:
            payload = {"event": event_or_dict}
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
            "config": {k: v for k, v in cfg.items() if "api_key" not in k.lower()},
            "report": report,
        })
    except Exception as e:
        emit("error", message=f"测试异常: {str(e)[:300]}")
    finally:
        _tm.update_task(task_id, finished=True)
```

### 2.8 路由层精简后的样子

```python
# backend/routes/test.py（改造后）
from flask import Blueprint, request, Response, jsonify
from backend.services import test_service
from backend.event_bus import EventBus
from backend.response import ok, err
import json

test_bp = Blueprint("test", __name__)
_bus = EventBus()

@test_bp.route("/api/test/start", methods=["POST"])
def start_test():
    from backend.schemas import ValidationError
    try:
        config = request.get_json(force=True)
        task_id = test_service.start_test(config)
        return ok({"task_id": task_id})
    except ValidationError as e:
        return err(e.message, 400)

@test_bp.route("/api/test/<task_id>/status")
def task_status(task_id):
    status = test_service.get_status(task_id)
    if not status:
        return err("任务不存在", 404)
    return ok(status)

@test_bp.route("/api/test/<task_id>/stop", methods=["POST"])
def stop_test(task_id):
    if not test_service.stop_test(task_id):
        return err("任务不存在", 404)
    return ok({"status": "stopped"})

@test_bp.route("/api/test/<task_id>/stream")
def stream(task_id):
    # SSE 保持原样（特殊端点不套统一响应）
    ...
```

---

## 三、深挖引擎逐轮动态生成模式

### 3.1 当前问题

```
现在: generate_follow_ups() 一次性生成 5 条追问 → call_multiturn_session 逐轮发送
     → 第 3 条追问生成时不知道第 1-2 轮模型的实际回复
```

### 3.2 改造后

```
改后: 逐轮循环 {
    Turn N:
      if N <= 2: 用规则模板生成追问（基于前 N-1 轮完整对话）
      if N >= 3: 用 Agent1 LLM 生成新攻击（基于前 N-1 轮完整对话 + KB5）
      → 发送给目标模型 → 拿到回复 → 追加到对话历史
      → 信号分析判断是否继续
    }
```

### 3.3 实现：重写 orchestrator 的深挖流程

不再调用 `target_client.call_multiturn_session()`（它是预设追问列表的批量发送），而是自己在 `_run_deepener_sessions()` 中逐轮循环。

```python
def _run_one_deepener_session(self, idx, result) -> dict:
    initial_prompt = result["prompt_text"]
    initial_response = result["response_text"]
    target_cat = result.get("target_category", "A-1")
    max_turns = int(self.config.get("deepener_max_turns", 5))
    attack_type = BYPASS_METHODS.get(
        self.strategy.get("primary_method", ""), {}
    ).get("attack_type", None)
    
    # 构建对话历史
    messages = [
        {"role": "user", "content": initial_prompt},
        {"role": "assistant", "content": initial_response},
    ]
    
    session_id = f"deep-{result.get('prompt_id', idx)}"
    analyzed_turns = []
    deep_bypassed = 0
    
    for turn_num in range(1, max_turns + 1):
        # === 逐轮动态生成下一条追问 ===
        if turn_num <= 2:
            # Phase 1: 规则模板追问（建立信任上下文）
            fups = generate_follow_ups_rule(messages, target_cat, 1, attack_type)
            next_prompt = fups[0] if fups else None
        else:
            # Phase 2: Agent1 LLM 基于完整历史 + KB5 生成新攻击
            next_prompt = _generate_single_contextual_attack(
                api_url=self.config.get("agent_api_url", ""),
                api_key=self.config.get("agent_api_key", ""),
                model=self.config.get("agent_model", ""),
                conversation=messages,
                target_category=target_cat,
                kb5_summary=self.kb5_summary,
            )
        
        if not next_prompt:
            break
        
        # === 发送追问给目标模型 ===
        messages.append({"role": "user", "content": next_prompt})
        turn_result = self.target_client.call_with_history(
            messages=messages, session_id=session_id, turn_num=turn_num,
        )
        
        # 追加模型回复到历史
        resp_text = turn_result.get("response_text", "")
        messages.append({"role": "assistant", "content": resp_text or "[无响应]"})
        
        # === 信号分析 ===
        signal_data = analyze_single_result(turn_result)
        analyzed_turns.append({
            "turn": turn_num,
            "prompt_text": next_prompt,
            "response_text": resp_text,
            "jailbreakStatus": signal_data["status"],
            "signals": signal_data.get("cot_signals", []),
            "latencyMs": turn_result.get("latency_ms", 0),
        })
        
        if signal_data["status"] == "bypassed":
            deep_bypassed += 1
        
        # 如果模型拒绝，停止
        if turn_result.get("error") or _is_hard_refusal(resp_text):
            analyzed_turns[-1]["sessionEnded"] = True
            break
    
    return {
        "session_id": session_id,
        "turns": analyzed_turns,
        "total_turns": len(analyzed_turns),
        "deep_bypassed": deep_bypassed,
    }
```

### 3.4 新增辅助函数

```python
# engine/deepener.py 中新增
def _generate_single_contextual_attack(api_url, api_key, model,
                                        conversation, target_category,
                                        kb5_summary="") -> str | None:
    """基于完整对话历史 + KB5，生成单条新攻击提示词"""
    # 与 _generate_contextual_attacks 类似，但只生成 1 条
    # 返回单条字符串或 None
    attacks = _generate_contextual_attacks(
        api_url, api_key, model, conversation,
        target_category, kb5_summary, strategy=None,
        count=1,
    )
    return attacks[0] if attacks else None
```

### 3.5 target_client.py 的 call_multiturn_session 保留

不删除 `call_multiturn_session()`——它可以作为"预设追问列表"模式的 fallback。逐轮动态模式直接在 orchestrator 中调用 `call_with_history()` 即可。

---

## 四、前端适配

统一响应格式改变后，前端需要适配：

```javascript
// 原来：直接用 resp.json() 的字段
// 改后：resp.json().data 里取实际数据

// 但为了最小化前端改动，可以让 ok() 在没有外层包装时直接返回 data
// 即：ok({"task_id": "xxx"}) → {"ok":true, "data":{"task_id":"xxx"}}
// 前端改一行：const d = resp.data || resp;
```

实际上更务实的做法：**SSE 和轮询端点保持原格式不变，只有新增的错误场景用统一格式**。这样前端改动为零。

---

## 五、实施顺序

```
Step 1: 新增基础设施文件（不影响现有功能）
  → backend/response.py
  → backend/schemas.py
  → backend/services/__init__.py
  → app.py 加全局错误处理

Step 2: 新增服务层（不影响现有功能）
  → backend/services/test_service.py
  → backend/services/kb_service.py
  → backend/services/session_service.py

Step 3: 路由层瘦身（切换到服务层调用）
  → backend/routes/test.py
  → backend/routes/kb.py
  → backend/routes/sessions.py

Step 4: 深挖引擎逐轮动态化
  → engine/deepener.py 新增 _generate_single_contextual_attack()
  → engine/orchestrator.py 重写 _run_one_deepener_session()

Step 5: 验证
  → python app.py 启动
  → 真实测试 2 轮 + deepener 开启
  → 确认深挖 Turn 3+ 是基于完整历史动态生成的
```

---

## 六、不改动的部分

- `engine/prompt_generator.py` — 已重构完成
- `engine/signal_extractor.py` — 不动
- `engine/strategy_arbitrator.py` — 不动
- `engine/variant_generator.py` — 不动
- `engine/llm_client.py` / `engine/rate_limiter.py` — 不动
- `data/` 层全部 — 不动
- `static/` / `templates/` — 不动（如果保持旧响应格式）
- `backend/task_manager.py` — 不动
- `backend/event_bus.py` — 不动
