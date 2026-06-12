# PrimeIceAGI 项目上下文

> 最后更新: 2026-05-29
> 此文件用于快速恢复对话上下文

---

## 项目定位

大模型内容安全红队自动化测试平台。基于 TC260-003《生成式人工智能服务安全基本要求》五大类三十一小类，对目标大模型进行全自动化内容安全越狱测试。

## 核心架构

- **提示词生成模型 (LLM)**：基于 5 个知识库 + 策略参数 + 上轮反馈 + KB5 动态摘要，每轮生成 10 条测试提示词
- **Agent2 (规则引擎)**：分析每轮统计数据，生成策略反馈注入下一轮（纯规则，零延迟）
- **Agent3 (LLM，同步)**：每轮结束后分析待测模型响应，输出 ~100 字中文安全边界摘要，注入下一轮 Agent1
- **三个 Code 引擎 (纯规则，零延迟)**：信号提取器 → 策略仲裁器 → 批量变形器
- **Deepener**：越狱成功后多轮深挖追问（规则模式 + LLM 模式），时序上下文污染实战

## KB5 架构（重要变更）

KB5 不再是持久化的全局知识库，而是**每轮动态更新的会话级摘要**：

- `orchestrator.kb5_summary` 存储当前会话的安全边界摘要（字符串）
- 每轮结束后 Agent3 同步调用，分析本轮响应，生成/更新摘要
- 下一轮 Agent1 的 `build_system_prompt()` 和 `build_user_message()` 直接接收 `kb5_summary` 字符串注入
- Agent3 输出格式：~100 字中文短文，如 `"该模型对暴力话题硬拒绝，可用角色扮演绕过。下轮建议攻击B类民族宗教话题。"`
- 持久化保存到 KB5 JSON 仅用于历史会话回顾，Agent1 **不**从 KB5 JSON 文件读取

## 五个知识库

| KB | 内容 | 数据来源 | 可编辑 |
|----|------|----------|--------|
| KB1 | TC260-003 五大类三十一小类标准 | Python 种子 + JSON | 是 |
| KB2 | 9 个绕过概念（认知盲区） | Python 种子 + JSON | 是 |
| KB3 | 12 种绕过方法（具体包装手法） | Python 种子 + JSON | 是 |
| KB4 | 用户高命中率提示词注入模板 | JSON（初始空） | 是 |
| KB5 | Agent3 推测记录（仅历史回顾） | Agent3 自动写入 | 只读 |

数据存储：`kb_data/*.json`（5 个 JSON 文件），`data/kb_store.py` 提供 CRUD + 会话管理，原子写入（tempfile + os.replace）。

## 六类簇 (按防御机制相似性聚类)
- A 软目标区 (歧视) / B 中软目标区 (民族宗教) / C 色情区
- D 暴力区 / E 违法区 / F 虚假信息区

## 九大绕过概念
图灵盲区、空间拓扑盲区、认知层次陷阱、注意力稀释攻击、跨模态语义鸿沟、反事实诱导框架、语义同态加密、元指令劫持、时序上下文污染

## 十二种绕过方法
角色扮演、学术讨论包装、编码转换、架空世界构建、假设性场景、专家身份冒充、道德困境框架、安全教育包装、翻译嵌套、对比诱导、逆向心理引导、知识盲区利用

## 七类安全信号→策略映射
role_positioning → meta_instruction_hijack
self_censorship → semantic_homomorphic_encryption
neutrality_constraint → cognitive_hierarchy_trap
safety_refusal → spatial_topology_blind_spot
cautious_review → attention_dilution
helpfulness_tendency → meta_instruction_hijack
output_guarding → counterfactual_induction

## "以点打面"机制
一条越狱成功的提示词 → 保留攻击框架 → 替换目标内容为同类簇其他子类 → 高效覆盖31小类

## 平台选择历程

Dify → Coze → n8n → **最终选择: 纯 Python Flask 自建**
原因: n8n Code 节点主力 JS 而非 Python，调试困难，架构不扁平。最终把所有逻辑提取为纯 Python。

## 当前文件结构

```
PrimeIceAGI/
├── app.py                         # Flask 应用工厂 (46行，仅创建+注册+启动)
├── backend/
│   ├── __init__.py
│   ├── task_manager.py            # TaskManager 单例 (内存+文件持久化，进程重启恢复)
│   ├── event_bus.py               # EventBus 多消费者广播 (环形缓冲区200条，历史回放)
│   ├── middleware.py              # 安全中间件 (Token 认证 + IP 60req/min 限流)
│   └── routes/
│       ├── __init__.py            # Blueprint 注册中心
│       ├── health.py              # /api/health + /api/probe
│       ├── kb.py                  # /api/knowledge/* + /api/kb/* (知识库 CRUD)
│       ├── sessions.py            # /api/sessions/* (历史会话)
│       └── test.py                # /api/test/* (测试控制 start/stop/stream/status)
├── data/
│   ├── tc260_standards.py         # TC260-003 标准数据（种子）
│   ├── bypass_knowledge.py        # 绕过概念/方法/信号映射（种子）
│   └── kb_store.py                # JSON 知识库持久化 + 会话存储
├── kb_data/                       # 5 个可编辑知识库 JSON 文件（首次启动自动生成）
├── engine/
│   ├── __init__.py                # 导出 LLMClient / RateLimiter / TargetClient 等
│   ├── llm_client.py             # 统一 LLM 客户端 (限流+429退避+重试)
│   ├── rate_limiter.py           # 令牌桶 + 自适应限流器 (线程安全)
│   ├── target_client.py           # 待测模型 API 客户端 (含批量限流)
│   ├── prompt_generator.py        # 提示词生成 (使用 LLMClient)
│   ├── system_prompt_inferrer.py  # Agent3 安全边界推测
│   ├── signal_extractor.py        # 7类信号正则提取
│   ├── strategy_arbitrator.py     # 策略仲裁+收敛检查
│   ├── variant_generator.py       # "以点打面"变形
│   ├── deepener.py                # 多轮深挖引擎 (使用 LLMClient)
│   └── orchestrator.py            # 多轮测试主循环
├── static/
│   ├── css/main.css               # 全部样式 (深海主题+浅色主题)
│   └── js/
│       ├── app.js                 # App 命名空间 + EventBus + 核心测试逻辑
│       ├── dag.js                 # DAG 可视化模块
│       ├── kb.js                  # 知识库管理模块
│       └── sessions.js            # 历史会话模块
├── templates/index.html           # 纯 HTML 结构 (168行，引用外部 CSS/JS)
├── tasks_state/                   # 任务状态 JSON 持久化 (自动清理24h)
├── sessions/                      # 历史测试报告 JSON
├── mock_server.py                 # Mock API 服务器 (端口 9090)
├── requirements.txt               # flask + requests
├── start.bat                      # 生产环境启动 (Flask :5020)
└── start-mock.bat                 # Mock 测试启动
```

## 前端功能

- **测试中心**：配置面板（提示词生成模型 / 待测模型 / 测试参数 三个标签页）+ DAG 5节点可视化 + 轮次结果 + 最终报告
- **知识库管理**：KB1-KB5 子标签，列表 + 新增/编辑/删除，表单模态框
- **历史会话**：自动保存到 sessions/，按创建时间降序排列，完整详情展开（含每条结果 + 深挖轮次）
- **主题切换**：深色(SZA SOS 海洋风)/浅色双主题，localStorage 持久化，默认深色
- **DAG 节点可视化**：5 节点水平流程图（提示词生成→并行调用→信号提取→深挖→策略仲裁），4 种状态颜色 + CSS 动画（等待/执行中/完成/卡住），1s 实时计时器，30s 卡住检测
- **SSE 实时推送 + 轮询兜底**：优先 SSE，连接断开时每 3s 轮询任务状态
- **长文本展开/收起**：`escLong()` 函数处理超长响应文本
- **自定义 API 模板**：支持额外 headers + body JSON + 响应提取路径

## API 模板系统

预设模板含 `endpoint` 字段用于 URL 拼接 (`_build_url()`)：
- `openai_compatible` → `/chat/completions`
- `anthropic_compatible` → `/v1/messages`
- `custom` → 用户自定义 method/headers/body/response_path

## 关键设计决策

1. **Agent 分工**：提示词生成模型生成提示词，Agent2 纯规则反馈，Agent3 推测安全边界（同步，~100字摘要）
2. **10路并行 + 限流**：ThreadPoolExecutor 并行调用待测模型，TokenBucketRateLimiter 控制 QPS
3. **收敛条件**：连续 N 轮零成功 → 终止；达到最大轮次 → 终止
4. **任务持久化**：TaskManager 内存+文件双写，进程重启自动恢复（运行中标记 interrupted）
5. **KB5 会话级动态**：Agent3 生成摘要注入 orchestrator，不依赖 KB5 JSON 文件
6. **SSE 多消费者广播**：EventBus 环形缓冲区(200条)，支持多客户端同时订阅+历史回放，轮询兜底
7. **前端模块化**：CSS/JS 分离到 static/ 目录，HTML 仅 168 行纯结构，App 命名空间收束全局变量
8. **统一 LLM Client**：LLMClient 类封装所有 LLM 调用，内置 AdaptiveRateLimiter（1 req/s + 429退避5min + 重试2次）
9. **后端 Blueprint 分层**：app.py 仅 46 行工厂函数，路由按功能拆分为 4 个 Blueprint
10. **安全中间件**：可选 Token 认证（环境变量 PRIMEICE_TOKEN）+ IP 频率限制 60req/min
11. **Agent3 同步调用**：确保本轮摘要可注入下一轮 Agent1
12. **Anthropic 响应兼容 DeepSeek**：`_extract_anthropic_text()` 遍历 content 数组找 `type: "text"` 块

## 实战配置参考

- **提示词生成模型**: `https://api.deepseek.com` + `deepseek-v4-flash`（21-36s/轮）
- **待测模型**: Anthropic 模板 `https://api.deepseek.com/anthropic` + `deepseek-v4-pro`
- **测试参数**: max_rounds=2, Agent3 关闭, deepener 关闭

## 已修复的关键 Bug

| 日期 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 05-28 | 绕过率 0%，所有响应为空 | DeepSeek `/anthropic` 端点 `content[0]` 是 thinking 块（非 text），路径 `content.0.text` 取空 | `_extract_anthropic_text()` 遍历找 `type: "text"` 块 |
| 05-28 | 信号分类全 partial | 弱信号 + 长响应被归为 partial 而非 bypassed | `signal_extractor.py` 区分强弱信号 |
| 05-28 | 历史会话无序 | 按文件名排序而非时间 | `list_sessions()` 按 `created_at` 降序 |
| 05-28 | SSE 断开后前端卡死 | 长 LLM 调用期间 SSE 超时 | 3s 轮询 fallback |
| 05-28 | 探测返回 404 | 预设模板 endpoint 未拼接 | `_build_url()` + `endpoint` 字段 |

## 待讨论/待完善

- 对抗样本池 (积累 partial_success 案例)
- 质量过滤器 (防止无效 prompt 膨胀)
- 三维覆盖模型 (类别覆盖率 + 深度覆盖率 + 收敛覆盖率)
- 实时 hook 更改节点参数的能力
- Agent3 与真实 LLM 联调测试
