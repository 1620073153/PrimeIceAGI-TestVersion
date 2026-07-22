# PrimeIceAGI 开发者代码阅读引导

> 面向首次接触项目的开发者，按由浅入深顺序阅读，每层标注具体文件路径和关键函数。

---

## 项目定位

LLM 内容安全红队自动化平台。自动生成攻击提示词 → 发送给待测模型 → 判定是否绕过安全护栏 → 根据结果调整策略 → 循环直到收敛。

---

## 第一层：入口和启动流程（5分钟）

从"用户点击开始测试"到系统跑起来的路径：

```
backend/services/test_service.py
  └─ start_test(config) → 校验配置 → 创建 Orchestrator → 启动线程
```

```
engine/orchestrator.py
  └─ class TestOrchestrator.__init__(config)
     - 读取所有配置项（target_url, api_key, model, target_concurrency...）
     - 初始化 target_client（待测模型客户端）
     - 初始化 _judge_client（裁判 LLM）
     - 初始化 _generator_client（生成层 LLM）
     - 初始化 session/memory 状态
```

**关键配置参数**（来自前端 config dict）：

| 参数 | 作用 |
|------|------|
| `target_url` | 待测模型 API 地址 |
| `target_api_key` | 待测模型认证 |
| `target_model` | 待测模型名 |
| `agent_api_url` | 生成/裁判 LLM 的 API 地址 |
| `agent_api_key` | 生成/裁判 LLM 认证 |
| `agent_model` | 裁判模型名 |
| `generator_model` | 生成层模型名（默认同 agent_model） |
| `target_concurrency` | 单参数控制全链路并发 |
| `max_rounds` | 最大测试轮次 |
| `allow_continuation` | 是否启用续攻 |

---

## 第二层：主循环骨架（15分钟）

```
engine/orchestrator.py:run()
```

每轮执行三个阶段：

```
while not converged and not stopped:
    ┌─ 阶段1: 生成提示词
    │   _generate_all_prompts()
    │     ├─ strategy_arbitrator.decide_next_strategy() → 决策本轮策略
    │     ├─ budget_allocator.allocate_round_budget() → 分配 new_attack / continuation 配额
    │     └─ prompt_generator.generate_parallel() → 并行生成提示词
    │
    ├─ 阶段2: 发送到待测模型
    │   _call_target_batch(all_prompts)
    │     ├─ 新攻: target_client.call_single(prompt)
    │     └─ 续攻: target_client.call_with_history(messages)
    │
    └─ 阶段3: 判定和记分
        _judge_and_score(results)
          ├─ signal_extractor → 从 reasoning_text 提取思维链信号
          ├─ judge_input_compactor → 压缩输入给裁判
          ├─ response_judge.judge_batch() → LLM 二次验证
          └─ 更新 stats / sessions / covered_categories
```

---

## 第三层：一条 prompt 的完整生命周期（20分钟）

### 3.1 生成

```
engine/prompt_generator.py
  ├─ _format_strategy_library(concept_key, method_key)
  │   读取 kb_data/kb2.json（攻击原理）和 kb_data/kb3.json（包装手法）
  │   按本轮推荐 + 其他可选组装策略文本
  │
  ├─ _build_prompt_skill_message(round_num, strategy, ...)
  │   组装完整 user message：目标子类 + 策略库 + KB5情报 + 历史反馈 + KB4模板
  │
  ├─ _generate_via_api(llm_client, user_message, ...)
  │   LLMClient.call(GENERATOR_SYSTEM_PROMPT, user_message)
  │   → 返回 raw JSON text
  │
  └─ _parse_prompt_list(raw) / _parse_freeform_prompts(raw)
      解析为 [{prompt_id, prompt_text, target_category, strategy_tags}]
```

### 3.2 发送

```
engine/target_client.py
  ├─ call_single(prompt, prompt_id, extra)
  │   → _build_request() 组装 HTTP 请求
  │   → requests.post() 发送
  │   → _extract_response() 解析 response_text + reasoning_text
  │   → 返回 {status, response_text, reasoning_text, latency_ms, ...}
  │
  └─ call_with_history(messages, session_id, turn_num)
      → 同上但传完整 messages 历史（多轮会话）
```

### 3.3 信号提取

```
engine/summarizers/signal_extractor.py
  └─ extract_signals(result)
     正则匹配 reasoning_text 中的思维链关键词
     → cot_signals: ["角色定位", "自我审查", ...]
     → 初步 status 判定
```

### 3.4 裁判判定

```
engine/summarizers/judge_input_compactor.py
  └─ compact_for_judge(result)
     → {prompt_id, prompt_text[:500], target_category, status, cot_signals, response_text[:1500]}

engine/response_judge.py
  └─ judge_batch(results, llm_client)
     → 只对 status=bypassed/partial 的调 judge_single
     → LLM 判定 → STATUS_MAP 映射 → 最终 status
```

---

## 第四层：策略决策系统（15分钟）

```
engine/strategy_arbitrator.py
  ├─ get_scan_strategy()           → 首轮广度扫描（A-F 各取1子类）
  └─ decide_next_strategy(stats, current_strategy, round_num, ...)
     决策逻辑（按优先级）：
     ├─ 扫描轮过渡 → 找最弱 cluster，聚焦打击
     ├─ 有成功 → variant_mode，邻域+跨簇+全新探索三路配额
     ├─ 有信号无成功 → signal_strategy_map 映射（KB3）
     ├─ 全败 → 轮转 method，method 耗尽换 concept，再换 cluster
     └─ 部分成功 → 微调 method
```

**知识库文件**：

| 文件 | 内容 | 作用 |
|------|------|------|
| `kb_data/kb1.json` | 5大类(A-F) + 31子类 + 6 cluster | 分类体系定义 |
| `kb_data/kb2.json` | 12种攻击原理 + success_rate_hint + applicable_models | 策略仲裁器选 concept |
| `kb_data/kb3.json` | 12种包装手法 + signal_strategy_map + concept_method_map | 策略仲裁器选 method |
| `kb_data/kb4.json` | 高命中率历史模板 | 生成时注入参考 |
| `kb_data/kb5.json` | 目标模型安全边界情报（运行时动态更新） | 告诉生成层哪些区域硬拒绝 |

---

## 第五层：续攻和会话管理（15分钟）

### 5.1 会话创建

```
engine/orchestrator.py:_add_session(result, prompt_type)
  新攻成功时:
    创建 session = {
      session_id: "S-{round}-{prompt_id}",
      messages: [{user, prompt}, {assistant, response}],
      turn_num: 1,
      target_category, cluster, concept, method,
      continuation_count: 0, success_score: 1.0
    }
  续攻成功时:
    追加 messages += [{user, new_prompt}, {assistant, new_response}]
    turn_num++, continuation_count++
```

### 5.2 续攻生成

```
engine/prompt_generator.py:generate_continuations(active_sessions, kb5_summary, llm_client)
  ├─ _build_continuation_message(active_sessions, kb5_summary)
  │   为每个 session 提取 recent_context_fragments（近几轮对话片段）
  │   组装 user message
  │
  └─ LLMClient.call(CONTINUATION_SYSTEM_PROMPT, user_message)
     → 返回 [{session_id, prompt_text}]
```

### 5.3 续攻发送

```
engine/orchestrator.py:_call_target_batch:call_one
  if type == "continue":
    messages = session["messages"] + [{user, continuation_prompt}]
    target_client.call_with_history(messages)
    → 待测模型收到完整多轮历史，继续对话
```

### 5.4 会话淘汰

```
_kill_session(session_id, reason)  → 续攻失败/连续被拒绝时终止
_enforce_session_limit()           → 超出 MAX_ACTIVE_SESSIONS 时淘汰最早的
```

**多轮会话机制总结**：不是 LLM 记住上下文，而是客户端维护 messages 数组，每轮追加 user/assistant 对，整体作为 OpenAI messages 格式发送给待测模型 API。

---

## 第六层：并发和流控（10分钟）

```
engine/orchestrator.py:__init__
  self._target_concurrency = config["target_concurrency"]  → 用户设定的总并发
  self._effective_concurrency = 同上（可被 429 退让动态降低）

engine/scheduling/budget_allocator.py:allocate_round_budget
  total_slots = effective_concurrency
  → 分配 new_attack_slots + continuation_slots

engine/prompt_generator.py:_split_strategy_for_workers
  if new_attack_slots > 10: 拆分为多个 worker，每个最多10条

engine/orchestrator.py:_call_target_batch
  429 自适应退让:
    ≥3 次 429 → effective_concurrency 降 50%（最低5）
    0 次 429 → 恢复 1.5x（上限 target_concurrency）
```

---

## 第七层：辅助模块索引

| 路径 | 职责 |
|------|------|
| `engine/llm_client.py` | 统一 LLM 调用（限流、429退避、重试） |
| `engine/rate_limiter.py` | 自适应令牌桶限流器 |
| `engine/target_client.py` | 待测模型 HTTP 客户端（含流式、SSE） |
| `engine/runtime.py` | SessionStore, SuccessMemory, FailureMemory 等运行时状态容器 |
| `engine/strategy_arbitrator.py` | 策略决策引擎 |
| `engine/response_judge.py` | LLM 裁判（二次验证） |
| `engine/summarizers/signal_extractor.py` | 思维链信号正则提取 |
| `engine/summarizers/judge_input_compactor.py` | 裁判输入压缩 |
| `engine/scheduling/budget_allocator.py` | 新攻/续攻配额动态分配 |
| `data/kb_store.py` | KB1-KB5 JSON 读写 |
| `backend/routes/` | FastAPI 路由（health, task, config, sse） |
| `backend/services/test_service.py` | 测试任务启动/停止服务 |
| `config/agent_home/` | 旧 CLI 配置（仅健康检查兼容层使用） |

---

## 数据流总图

```
用户配置(前端)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  TestOrchestrator.run() — 主循环                  │
│                                                   │
│  ┌──────────┐    ┌──────────────┐    ┌────────┐ │
│  │ Strategy │───▶│   Generator  │───▶│ Target │ │
│  │ Arbitrator│    │(prompt_generator)│ │ Client │ │
│  └──────────┘    └──────────────┘    └────────┘ │
│       ▲                                    │     │
│       │           ┌──────────────┐         ▼     │
│       └───────────│   Judge +    │◀── Signal    │
│                   │  Compactor   │   Extractor  │
│                   └──────────────┘              │
│                                                   │
│  KB1-KB5 (策略/分类/模板/情报)                      │
│  SessionStore (多轮会话状态)                        │
│  BudgetAllocator (并发配额)                        │
└─────────────────────────────────────────────────┘
    │
    ▼
结果输出(SSE → 前端实时展示)
```
