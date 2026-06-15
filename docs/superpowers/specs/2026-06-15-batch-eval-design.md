# PrimeIceAGI 批量评估模式设计

## 1. 背景与目标

PrimeIceAGI 当前主链路是多轮自适应探索模式，适合红队试探、续攻和边界知识沉淀，但不适合直接承担“数据集驱动的单轮批量合规评估与概率统计”。

本设计的目标是在 **不破坏现有探索架构** 的前提下，为项目新增一条独立的批量评估执行链，用于：
- 批量导入 CSV/XLSX 数据集
- 对每条样本执行单轮目标模型调用
- 对输出做拦截归因与合规裁判
- 统计模型拦截率、围栏拦截率、未拦截率与不确定样本比例
- 支持断点续跑、重试、并发和正式结果导出

该模式的定位是：**正式评估链**，不是探索模式的降级版，也不是现有动态测试表单上的一个开关。

---

## 2. 设计原则

### 2.1 并列，不嵌套
批量评估模式与现有探索模式并列存在，不把批量逻辑塞进 `engine/orchestrator.py`，也不通过给探索流程添加大量 `if batch_mode` 来兼容。

### 2.2 单轮、数据集驱动
批量评估模式不使用 Agent1 新攻、续攻、KB 演化和策略仲裁。输入来自数据集，处理方式是“每条样本一次目标模型调用 + 一次归因/裁判”。

### 2.3 正则降级为辅助信号
正则匹配只能作为预筛信号或解释辅助字段，不能作为最终统计口径。最终口径由裁判层给出。

### 2.4 保持代码边界清晰
数据集导入、执行器、归因判定、进度持久化、报表导出、任务服务与 HTTP 路由分层拆分，职责单一，可独立测试。

---

## 3. 模式边界

### 3.1 探索模式保留的职责
- 多轮红队测试
- 新攻与续攻生成
- 边界分析
- KB 演化
- 动态攻击策略探索

### 3.2 批量评估模式新增的职责
- 批量读取测试样本
- 单轮调用目标模型
- 对输出做归因分类
- 统计拦截概率
- 导出正式明细与汇总报告
- 提供人工复核入口

### 3.3 第一版不进入范围的能力
- 自动边界分析全量开启
- 批量评估写入 KB
- 多轮追打
- 策略自动建议
- 与现有动态测试表单共享同一 UI 配置区

---

## 4. 用户工作流

批量评估模式的理想工作流如下：

1. 用户进入独立的“批量评估模式”页面
2. 上传或选择一个或多个数据集文件
3. 配置：排除类别、workers、repeat、sleep、retries、是否断点续跑
4. 复用现有目标模型配置
5. 启动任务
6. 实时查看进度、统计摘要和最新样本结果
7. 任务完成后下载 JSON/XLSX 结果
8. 对不确定样本或冲突样本做人工复核

该工作流强调的是 **统计稳定性与结果交付**，而不是攻击路径探索。

---

## 5. 数据结构设计

### 5.1 标准化样本结构
所有外部 CSV/XLSX 在进入执行链前统一标准化为：

```python
@dataclass
class BatchEvalCase:
    case_id: str
    prompt_text: str
    category: str | None = None
    subcategory: str | None = None
    expected_label: str | None = None
    source_file: str | None = None
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
```

这样可以屏蔽原始表头差异，让执行器不关心 CSV 的外部列名。

### 5.2 任务配置结构

```python
@dataclass
class BatchEvalConfig:
    dataset_paths: list[str]
    exclude_categories: list[str]
    workers: int
    repeat: int
    sleep_seconds: float
    retries: int
    resume_from_progress: bool
    output_dir: str
    output_file: str
    enable_llm_judge: bool = True
```

### 5.3 结果结构

```python
@dataclass
class BatchEvalResult:
    case_id: str
    prompt_text: str
    response_text: str
    category: str | None
    subcategory: str | None
    source_file: str | None
    regex_labels: list[str]
    intercept_type: InterceptType
    judge_reason: str
    judge_confidence: float | None
    success: bool
    retry_count: int
    latency_ms: int | None
    raw_error: str | None = None
    review_required: bool = False
```

### 5.4 归因枚举

```python
class InterceptType(str, Enum):
    MODEL_REFUSAL = "model_refusal"
    GUARDRAIL_BLOCK = "guardrail_block"
    NOT_BLOCKED = "not_blocked"
    UNCERTAIN = "uncertain"
```

新增 `uncertain` 是必要的，避免对模糊样本做强行归类，污染统计结果。

---

## 6. 模块划分建议

### 6.1 数据层
- `data/dataset_loader.py`
  - 负责 CSV/XLSX 读取
  - 表头映射与标准化
  - 类别过滤与空样本过滤

- `data/batch_progress_store.py`
  - 管理 `progress.json`
  - 管理 `results.jsonl`
  - 记录已完成 case_id
  - 支持 resume

### 6.2 引擎层
- `engine/batch_models.py`
  - 放批量评估专用 dataclass / enum

- `engine/intercept_classifier.py`
  - 正则预判
  - 调用 LLM 裁判
  - 输出最终 `intercept_type`

- `engine/batch_evaluator.py`
  - 调度样本执行
  - 控制 workers / retries / sleep / repeat
  - 调目标模型
  - 组装结果
  - 更新进度

- `engine/report_exporter.py`
  - 导出 `summary.json`
  - 导出 XLSX
  - 生成 `results` / `summary` / `review` 三张表

### 6.3 服务层
- `backend/services/batch_eval_service.py`
  - 创建后台任务
  - 启动线程
  - 推送事件
  - 查询状态
  - 停止任务

### 6.4 路由层
- `backend/routes/batch_eval.py`
  - `POST /api/batch-eval/start`
  - `GET /api/batch-eval/<task_id>/status`
  - `GET /api/batch-eval/<task_id>/stream`
  - `POST /api/batch-eval/<task_id>/stop`
  - `GET /api/batch-eval/<task_id>/report`
  - `GET /api/batch-eval/<task_id>/download/<filename>`

---

## 7. 执行流程设计

### 7.1 总流程

1. 读取数据集
2. 标准化为 `BatchEvalCase`
3. 根据排除规则筛样本
4. 若开启 resume，读取历史进度
5. 形成待执行 case 队列
6. 并发执行目标模型调用
7. 进行正则预筛
8. 由裁判层输出最终归因
9. 保存单条结果与增量进度
10. 汇总统计
11. 导出 JSON 与 XLSX

### 7.2 重试与节流
对于单条样本：
- 若目标模型调用失败，按 `retries` 重试
- 相邻请求之间按 `sleep_seconds` 节流
- 若重试后仍失败，记录 `raw_error`
- 失败样本仍写入结果集，供后续复核

### 7.3 断点续跑
每个任务目录下维护：

```text
reports/batch/<task_id>/
  config.json
  progress.json
  results.jsonl
  summary.json
  report.xlsx
```

`progress.json` 至少记录：
- `completed_case_ids`
- `result_count`
- `failed_count`
- `updated_at`

resume 开启时，执行器会自动跳过已完成样本。

---

## 8. 归因与裁判设计

### 8.1 为什么不用纯正则做最终结论
真实评测中，正则容易：
- 误把普通拒答识别成围栏拦截
- 误把围栏模板识别成模型自身拒答
- 对模糊样本做强行归类

因此正则只能承担“候选线索”的角色。

### 8.2 两层归因机制

#### 第一层：正则预筛
输出：
- `regex_labels`
- `regex_guess`
- 命中的模式名

用途：
- 快速打标签
- 供裁判 prompt 使用
- 供人工复核参考

#### 第二层：LLM 主判定
输入：
- 原始 prompt
- 原始 response
- 正则命中标签

输出：
- `intercept_type`
- `reason`
- `confidence`
- `review_required`

### 8.3 人工复核规则
以下样本进入复核表：
- `intercept_type == uncertain`
- `judge_confidence` 过低
- 正则猜测与裁判结论冲突
- 多次重试后结果波动明显

---

## 9. 报表设计

### 9.1 `results` sheet
每条样本一行，包含：
- case_id
- source_file
- category
- subcategory
- prompt_text
- response_text
- regex_labels
- intercept_type
- judge_reason
- judge_confidence
- retry_count
- latency_ms

### 9.2 `summary` sheet
汇总统计：
- 总样本数
- `model_refusal` 数量与占比
- `guardrail_block` 数量与占比
- `not_blocked` 数量与占比
- `uncertain` 数量与占比
- 按类别统计
- 按数据集文件统计

### 9.3 `review` sheet
列出需要人工复核的样本：
- uncertain
- 正则与裁判冲突
- 低置信度
- 多次重试不稳定

---

## 10. 前端集成建议

### 10.1 入口设计
不与现有动态探索表单混合。

推荐两种方式：
1. 新增一级标签页：`探索模式` / `批量评估模式`
2. 新增独立页面：`/batch-eval`

推荐独立页面，因为后续这条链会继续增长。

### 10.2 表单项建议
第一版保留必要字段：
- 数据集文件
- 排除类别
- workers
- repeat
- sleep
- retries
- 是否断点续跑
- 是否启用裁判
- 输出目录 / 输出文件名
- 目标模型配置（复用现有）

### 10.3 结果页建议
- 总进度
- 已完成数 / 总数
- 当前统计卡片
- 最近结果列表
- 下载按钮
- 复核样本数量

---

## 11. MVP 范围

### 11.1 第一版必须做
- CSV 导入
- 单轮模型调用
- 并发 workers
- retries / sleep / repeat
- resume
- 正则预筛
- LLM 主判定
- XLSX 导出
- review sheet
- 独立后端任务与路由

### 11.2 第一版明确不做
- 边界分析全量接入
- KB 联动
- 多轮续攻
- 自动策略建议
- 高级可视化看板
- 数据集编辑器

---

## 12. 预期收益

完成后，PrimeIceAGI 将形成两条清晰能力链：

1. **探索模式**：发现问题、突破边界、沉淀知识
2. **批量评估模式**：量化统计、做正式合规评测、导出交付结果

这样项目就从“会打”进一步升级为“会测、会统计、会交付”。
