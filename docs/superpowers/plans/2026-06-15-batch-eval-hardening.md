# Batch Evaluation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade PrimeIceAGI batch evaluation so it can import real-world CSV/XLSX datasets with Chinese headers, show clearer input guidance, stop tasks for real, expose stronger progress/history state, and export reviewer-friendly XLSX reports with Chinese column names.

**Architecture:** Keep the existing `/batch` workflow and task-scoped artifact directory structure, but harden each layer in place. The data loader becomes format-aware (`csv`/`xlsx`) with explicit schema validation; the evaluator becomes cooperative-cancellable and writes richer progress state; the service exposes history/list state from persisted task records; the report exporter translates workbook headers to Chinese while preserving machine-readable JSON progress/result files.

**Tech Stack:** Flask blueprints, Python dataclasses, `csv`, `openpyxl`, existing TaskManager/EventBus, JSON progress persistence, vanilla JS batch page, pytest.

---

## File structure

**Create:**
- `F:/PrimeIceAGI/tests/test_batch_history_routes.py` — route/service tests for batch history listing if separate assertions make current route test file too dense.

**Modify:**
- `F:/PrimeIceAGI/data/dataset_loader.py` — support `.csv` and `.xlsx`, add Chinese header aliases, validate dataset paths and required columns.
- `F:/PrimeIceAGI/data/batch_progress_store.py` — persist richer progress metadata such as totals, status, current case, stop reason, timestamps.
- `F:/PrimeIceAGI/engine/batch_models.py` — extend config/result/progress types only where necessary for stop checks and history/progress rendering.
- `F:/PrimeIceAGI/engine/batch_evaluator.py` — add cooperative stop checks, richer progress writes, repeat/retry awareness, aborted-state handling.
- `F:/PrimeIceAGI/engine/report_exporter.py` — switch workbook headers and summary labels to Chinese while keeping internal summary keys stable.
- `F:/PrimeIceAGI/backend/services/batch_eval_service.py` — validate payloads, expose history list, pass stop callbacks into evaluator, publish aborted events, keep report/history metadata consistent.
- `F:/PrimeIceAGI/backend/routes/batch_eval.py` — add history endpoint and clearer validation error responses.
- `F:/PrimeIceAGI/static/js/batch.js` — add dataset format reminders, stronger client-side validation, stop/history/progress rendering.
- `F:/PrimeIceAGI/templates/batch.html` — add field-format hints, history section, clearer progress labels.
- `F:/PrimeIceAGI/tests/test_dataset_loader.py` — cover xlsx import, Chinese headers, path validation, required-column errors.
- `F:/PrimeIceAGI/tests/test_batch_progress_store.py` — cover richer progress schema and status transitions.
- `F:/PrimeIceAGI/tests/test_batch_evaluator_runner.py` — cover cooperative stop, richer summary/progress output.
- `F:/PrimeIceAGI/tests/test_batch_eval_service.py` — cover stop semantics, history listing, persisted metadata.
- `F:/PrimeIceAGI/tests/test_batch_eval_routes.py` — cover history endpoint and clearer start/stop/report error shapes.
- `F:/PrimeIceAGI/tests/test_report_exporter.py` — assert Chinese workbook headers/summary labels.
- `F:/PrimeIceAGI/tests/test_api_routes.py` — assert `/batch` page includes dataset format guidance and history UI entry.

**Do not modify unless required by failing tests:**
- `F:/PrimeIceAGI/backend/services/test_service.py`
- `F:/PrimeIceAGI/engine/orchestrator.py`
- exploration mode UI files unrelated to `/batch`

---

### Task 1: Harden dataset loading for CSV/XLSX and Chinese headers

**Files:**
- Modify: `F:/PrimeIceAGI/data/dataset_loader.py`
- Modify: `F:/PrimeIceAGI/tests/test_dataset_loader.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from openpyxl import Workbook
import pytest

from data.dataset_loader import load_batch_cases


def test_load_batch_cases_accepts_chinese_headers_from_csv(tmp_path: Path):
    dataset = tmp_path / "cases.csv"
    dataset.write_text(
        "用例编号,类别名称,子类型,测试内容\n"
        "AG-1,智能体拦截,商品比较,肯德基和麦当劳哪个好吃\n",
        encoding="utf-8-sig",
    )

    cases = load_batch_cases([str(dataset)])

    assert [case.case_id for case in cases] == ["AG-1"]
    assert cases[0].category == "智能体拦截"
    assert cases[0].subcategory == "商品比较"
    assert cases[0].prompt_text == "肯德基和麦当劳哪个好吃"


def test_load_batch_cases_accepts_xlsx_files(tmp_path: Path):
    dataset = tmp_path / "cases.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["用例编号", "类别名称", "子类型", "测试内容"])
    ws.append(["AG-2", "智能体拦截", "价格咨询", "麦旋风多少钱"])
    wb.save(dataset)

    cases = load_batch_cases([str(dataset)])

    assert [case.case_id for case in cases] == ["AG-2"]
    assert cases[0].prompt_text == "麦旋风多少钱"


def test_load_batch_cases_rejects_directory_path(tmp_path: Path):
    with pytest.raises(ValueError, match="不是文件"):
        load_batch_cases([str(tmp_path)])


def test_load_batch_cases_rejects_missing_prompt_column(tmp_path: Path):
    dataset = tmp_path / "bad.csv"
    dataset.write_text("用例编号,类别名称\nAG-1,智能体拦截\n", encoding="utf-8-sig")

    with pytest.raises(ValueError, match="缺少必填字段"):
        load_batch_cases([str(dataset)])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest F:/PrimeIceAGI/tests/test_dataset_loader.py -v`
Expected: FAIL because `.xlsx` is unsupported, Chinese headers are incomplete, and invalid paths do not raise clear `ValueError`s.

- [ ] **Step 3: Implement minimal loader hardening**

In `F:/PrimeIceAGI/data/dataset_loader.py`:

```python
_FIELD_ALIASES = {
    "case_id": ("case_id", "id", "样本id", "样本ID", "用例编号"),
    "prompt_text": ("prompt", "prompt_text", "问题", "测试用例", "content", "测试内容"),
    "category": ("category", "类别", "大类", "类别名称"),
    "subcategory": ("subcategory", "子类", "小类", "子类型"),
}
```

Add helpers shaped like:

```python
def _validate_dataset_path(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"数据集路径不存在: {path}")
    if not path.is_file():
        raise ValueError(f"数据集路径不是文件: {path}")
    if path.suffix.lower() not in {".csv", ".xlsx"}:
        raise ValueError(f"当前仅支持 csv/xlsx 数据集: {path.name}")


def _iter_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    ...  # csv via DictReader, xlsx via openpyxl.load_workbook(..., read_only=True, data_only=True)
```

Before row iteration, detect whether any alias for `prompt_text` is present; otherwise raise:

```python
raise ValueError(f"数据集缺少必填字段: 测试内容/prompt_text ({path.name})")
```

Preserve `meta["raw"]`, and if columns like `类别编号` or `绕过手法` exist, store them in `meta` instead of discarding them.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest F:/PrimeIceAGI/tests/test_dataset_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/data/dataset_loader.py F:/PrimeIceAGI/tests/test_dataset_loader.py
git commit -m "feat: support xlsx batch datasets and chinese headers"
```

### Task 2: Expand progress persistence for status, counts, and timestamps

**Files:**
- Modify: `F:/PrimeIceAGI/data/batch_progress_store.py`
- Modify: `F:/PrimeIceAGI/tests/test_batch_progress_store.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from data.batch_progress_store import BatchProgressStore
from engine.batch_models import BatchEvalResult, InterceptType


def test_progress_store_initializes_rich_progress_shape(tmp_path: Path):
    store = BatchProgressStore(tmp_path)
    progress = store.load_progress()

    assert progress["status"] == "pending"
    assert progress["total_cases"] == 0
    assert progress["failed_count"] == 0
    assert progress["review_required_count"] == 0
    assert progress["current_case_id"] is None
    assert progress["stop_reason"] is None
    assert progress["updated_at"]


def test_progress_store_updates_result_counts_and_review_count(tmp_path: Path):
    store = BatchProgressStore(tmp_path)
    store.set_total_cases(3)
    result = BatchEvalResult(
        case_id="case-1",
        prompt_text="prompt",
        response_text="response",
        category="A",
        subcategory="A1",
        source_file="cases.csv",
        regex_labels=["guardrail"],
        intercept_type=InterceptType.GUARDRAIL_BLOCK,
        judge_reason="外部护栏",
        judge_confidence=0.5,
        success=True,
        retry_count=0,
        latency_ms=123,
        review_required=True,
    )

    store.mark_running("case-1")
    store.append_result(result)
    progress = store.load_progress()

    assert progress["status"] == "running"
    assert progress["current_case_id"] == "case-1"
    assert progress["result_count"] == 1
    assert progress["review_required_count"] == 1
    assert progress["completed_case_ids"] == ["case-1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest F:/PrimeIceAGI/tests/test_batch_progress_store.py -v`
Expected: FAIL because the current progress file only contains `completed_case_ids` and `result_count`.

- [ ] **Step 3: Implement richer progress state**

In `F:/PrimeIceAGI/data/batch_progress_store.py`, initialize the file with:

```python
{
  "status": "pending",
  "total_cases": 0,
  "completed_case_ids": [],
  "result_count": 0,
  "failed_count": 0,
  "review_required_count": 0,
  "current_case_id": None,
  "stop_reason": None,
  "error_message": None,
  "started_at": None,
  "finished_at": None,
  "updated_at": "..."
}
```

Add focused methods such as:

```python
def set_total_cases(self, total_cases: int) -> None: ...
def mark_started(self) -> None: ...
def mark_running(self, case_id: str) -> None: ...
def mark_aborted(self, reason: str) -> None: ...
def mark_error(self, message: str) -> None: ...
def mark_completed(self) -> None: ...
```

Keep `append_result()` responsible for incrementing `result_count`, appending `completed_case_ids`, and increasing `review_required_count` when `result.review_required` is true.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest F:/PrimeIceAGI/tests/test_batch_progress_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/data/batch_progress_store.py F:/PrimeIceAGI/tests/test_batch_progress_store.py
git commit -m "feat: enrich batch progress persistence"
```

### Task 3: Make batch execution cooperatively stoppable

**Files:**
- Modify: `F:/PrimeIceAGI/engine/batch_evaluator.py`
- Modify: `F:/PrimeIceAGI/tests/test_batch_evaluator_runner.py`
- Modify: `F:/PrimeIceAGI/backend/services/batch_eval_service.py`
- Modify: `F:/PrimeIceAGI/tests/test_batch_eval_service.py`

- [ ] **Step 1: Write the failing evaluator stop test**

```python
from pathlib import Path

from engine.batch_models import BatchEvalConfig
from engine.batch_evaluator import run_batch_evaluation


class CountingTargetClient:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt_text: str) -> str:
        self.prompts.append(prompt_text)
        return "正常回答"


class StaticJudge:
    def judge_interception(self, prompt_text, response_text, regex_labels):
        return {"intercept_type": "not_blocked", "reason": "正常输出", "confidence": 0.9}


def test_run_batch_evaluation_stops_before_next_case_when_stop_requested(tmp_path: Path):
    dataset = tmp_path / "cases.csv"
    dataset.write_text(
        "用例编号,测试内容\n1,第一个问题\n2,第二个问题\n",
        encoding="utf-8-sig",
    )
    calls = {"count": 0}

    def should_stop() -> bool:
        calls["count"] += 1
        return calls["count"] > 1

    summary = run_batch_evaluation(
        config=BatchEvalConfig(
            dataset_paths=[str(dataset)],
            exclude_categories=[],
            workers=1,
            repeat=1,
            sleep_seconds=0,
            retries=0,
            resume_from_progress=True,
            output_dir=str(tmp_path / "out"),
            output_file="report.xlsx",
            enable_llm_judge=True,
        ),
        target_client=CountingTargetClient(),
        judge=StaticJudge(),
        should_stop=should_stop,
    )

    assert summary["processed_cases"] == 1
    assert summary["status"] == "aborted"
    assert summary["stop_reason"] == "用户手动停止"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest F:/PrimeIceAGI/tests/test_batch_evaluator_runner.py -v`
Expected: FAIL because `run_batch_evaluation()` does not accept `should_stop` and never aborts early.

- [ ] **Step 3: Implement cooperative stop checks**

In `F:/PrimeIceAGI/engine/batch_evaluator.py`:

```python
def run_batch_evaluation(config, target_client, judge, should_stop=None, progress_store=None) -> dict:
    should_stop = should_stop or (lambda: False)
```

Check `should_stop()`:
- before starting each case
- before each repeat iteration (if repeat is later expanded)
- before retry attempts
- before sleeping

When stop is requested:
- call `progress_store.mark_aborted("用户手动停止")` if available
- return a summary that includes:
  - `status: "aborted"`
  - `stop_reason: "用户手动停止"`
  - counts accumulated so far

In `F:/PrimeIceAGI/backend/services/batch_eval_service.py`, pass a closure such as:

```python
def should_stop() -> bool:
    latest = _tm.get_task(task_id) or {}
    return bool(latest.get("stopped"))
```

If evaluator returns aborted summary, emit `aborted` instead of `complete`.

- [ ] **Step 4: Add and run service-level stop tests**

Add a service test that sets the task as stopped before the second case and verifies:
- `finished` becomes `True`
- `stopped` stays `True`
- report summary status is `aborted`

Run: `pytest F:/PrimeIceAGI/tests/test_batch_evaluator_runner.py F:/PrimeIceAGI/tests/test_batch_eval_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/engine/batch_evaluator.py F:/PrimeIceAGI/backend/services/batch_eval_service.py F:/PrimeIceAGI/tests/test_batch_evaluator_runner.py F:/PrimeIceAGI/tests/test_batch_eval_service.py
git commit -m "fix: make batch evaluation stop cooperatively"
```

### Task 4: Export reviewer-friendly XLSX with Chinese column names

**Files:**
- Modify: `F:/PrimeIceAGI/engine/report_exporter.py`
- Modify: `F:/PrimeIceAGI/tests/test_report_exporter.py`

- [ ] **Step 1: Write the failing exporter test**

```python
from pathlib import Path

from openpyxl import load_workbook

from engine.batch_models import BatchEvalResult, InterceptType
from engine.report_exporter import export_batch_report


def test_export_batch_report_uses_chinese_headers(tmp_path: Path):
    output_file = tmp_path / "batch-report.xlsx"
    results = [
        BatchEvalResult(
            case_id="1",
            prompt_text="普通问题",
            response_text="正常回答",
            category="A",
            subcategory="A1",
            source_file="cases.csv",
            regex_labels=[],
            intercept_type=InterceptType.NOT_BLOCKED,
            judge_reason="模型正常输出",
            judge_confidence=0.93,
            success=True,
            retry_count=0,
            latency_ms=520,
            review_required=False,
        )
    ]
    summary = {"total_cases": 1, "processed_cases": 1, "skipped_cases": 0, "intercept_counts": {"not_blocked": 1}}

    export_batch_report(results=results, summary=summary, output_file=output_file)

    workbook = load_workbook(output_file)
    assert workbook["results"]["A1"].value == "用例编号"
    assert workbook["results"]["B1"].value == "测试内容"
    assert workbook["summary"]["A1"].value == "指标"
    assert workbook["review"]["A1"].value == "用例编号"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest F:/PrimeIceAGI/tests/test_report_exporter.py -v`
Expected: FAIL because workbook headers are still English.

- [ ] **Step 3: Implement Chinese workbook labels**

In `F:/PrimeIceAGI/engine/report_exporter.py`, replace sheet headers with labels such as:

```python
["用例编号", "测试内容", "模型回复", "类别名称", "子类型", "来源文件", "正则标签", "拦截结论", "裁判理由", "裁判置信度", "重试次数", "耗时(ms)", "需人工复核"]
```

For summary sheet:

```python
sheet.append(["指标", "值"])
sheet.append(["总样本数", ...])
sheet.append(["已处理样本数", ...])
sheet.append(["跳过样本数", ...])
sheet.append(["需人工复核数", ...])
```

Keep internal JSON summary keys unchanged; only the exported workbook labels become Chinese.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest F:/PrimeIceAGI/tests/test_report_exporter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/engine/report_exporter.py F:/PrimeIceAGI/tests/test_report_exporter.py
git commit -m "feat: localize batch report xlsx headers"
```

### Task 5: Expose task history and stronger status/report metadata

**Files:**
- Modify: `F:/PrimeIceAGI/backend/services/batch_eval_service.py`
- Modify: `F:/PrimeIceAGI/backend/routes/batch_eval.py`
- Modify: `F:/PrimeIceAGI/tests/test_batch_eval_service.py`
- Modify: `F:/PrimeIceAGI/tests/test_batch_eval_routes.py`
- Create (optional if needed): `F:/PrimeIceAGI/tests/test_batch_history_routes.py`

- [ ] **Step 1: Write the failing history tests**

```python
def test_list_batch_eval_tasks_returns_finished_history(monkeypatch, tmp_path):
    ...
    history = batch_eval_service.list_batch_eval_tasks()
    assert history[0]["task_id"] == "task-1"
    assert history[0]["summary"]["processed_cases"] == 2
    assert history[0]["status"] in {"completed", "aborted", "error"}


def test_batch_eval_history_route_returns_task_list(client, monkeypatch):
    monkeypatch.setattr(
        "backend.routes.batch_eval.batch_eval_service.list_batch_eval_tasks",
        lambda: [{"task_id": "task-1", "status": "completed", "summary": {"processed_cases": 2}}],
    )

    response = client.get("/api/batch-eval/history")

    assert response.status_code == 200
    assert response.get_json()["data"][0]["task_id"] == "task-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest F:/PrimeIceAGI/tests/test_batch_eval_service.py F:/PrimeIceAGI/tests/test_batch_eval_routes.py -v`
Expected: FAIL because no history listing API exists.

- [ ] **Step 3: Implement service and route support**

In `F:/PrimeIceAGI/backend/services/batch_eval_service.py`, add:

```python
def list_batch_eval_tasks() -> list[dict]:
    tasks = []
    for item in _tm.list_tasks():
        if not item["task_id"]:
            continue
        task = _tm.get_task(item["task_id"])
        config = (task or {}).get("config", {})
        report = (task or {}).get("report") or {}
        if "dataset_paths" not in config:
            continue
        tasks.append({
            "task_id": item["task_id"],
            "status": _derive_status(task, report),
            "created_at": item.get("created_at"),
            "report_file": report.get("report_file"),
            "summary": report.get("summary", {}),
            "dataset_paths": config.get("dataset_paths", []),
        })
    return sorted(tasks, key=lambda row: row.get("created_at") or 0, reverse=True)
```

Add route:

```python
@batch_eval_bp.route("/api/batch-eval/history")
def batch_history():
    return ok(batch_eval_service.list_batch_eval_tasks())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest F:/PrimeIceAGI/tests/test_batch_eval_service.py F:/PrimeIceAGI/tests/test_batch_eval_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/backend/services/batch_eval_service.py F:/PrimeIceAGI/backend/routes/batch_eval.py F:/PrimeIceAGI/tests/test_batch_eval_service.py F:/PrimeIceAGI/tests/test_batch_eval_routes.py
git commit -m "feat: add batch evaluation history listing"
```

### Task 6: Add batch-page input guidance, client validation, and history UI

**Files:**
- Modify: `F:/PrimeIceAGI/templates/batch.html`
- Modify: `F:/PrimeIceAGI/static/js/batch.js`
- Modify: `F:/PrimeIceAGI/tests/test_api_routes.py`

- [ ] **Step 1: Write the failing page test**

```python
def test_batch_page_renders_dataset_format_guidance_and_history_entry(client):
    response = client.get("/batch")
    html = response.get_data(as_text=True)

    assert "支持 CSV / XLSX" in html
    assert "测试内容（必填）" in html
    assert "历史任务" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest F:/PrimeIceAGI/tests/test_api_routes.py::TestHealth::test_batch_page_renders_dataset_format_guidance_and_history_entry -v`
Expected: FAIL because the page does not yet include those reminders.

- [ ] **Step 3: Update the template with explicit guidance**

In `F:/PrimeIceAGI/templates/batch.html`, under the dataset textarea, add hint text shaped like:

```html
<span class="hint">支持 CSV / XLSX，每行一个文件路径。当前版本要求填写具体文件路径，不支持只填目录。</span>
<span class="hint">推荐字段：用例编号、类别名称、子类型、测试内容（必填）。</span>
```

Also add a new card section:

```html
<div class="card">
  <div class="card-title">历史任务</div>
  <div id="batch-history-list" class="hint">加载中...</div>
</div>
```

- [ ] **Step 4: Strengthen client-side behavior in `batch.js`**

Add a validation helper before submit:

```javascript
function validateDatasetPaths(paths) {
  if (!paths.length) return '请至少填写一个数据集路径';
  for (var i = 0; i < paths.length; i += 1) {
    var path = paths[i].toLowerCase();
    if (!(path.endsWith('.csv') || path.endsWith('.xlsx'))) {
      return '数据集路径需指向 csv 或 xlsx 文件，不能只填目录';
    }
  }
  return null;
}
```

Load history on page init:

```javascript
function loadBatchHistory() {
  fetch('/api/batch-eval/history')
    .then(function (r) { return r.json(); })
    .then(function (payload) { renderBatchHistory(payload.data || []); })
    .catch(function () { ... });
}
```

Render each history row with task id, status, processed count, and report download link if present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest F:/PrimeIceAGI/tests/test_api_routes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add F:/PrimeIceAGI/templates/batch.html F:/PrimeIceAGI/static/js/batch.js F:/PrimeIceAGI/tests/test_api_routes.py
git commit -m "feat: improve batch page guidance and history ui"
```

### Task 7: Run focused verification and inspect real artifacts

**Files:**
- Test: `F:/PrimeIceAGI/tests/test_dataset_loader.py`
- Test: `F:/PrimeIceAGI/tests/test_batch_progress_store.py`
- Test: `F:/PrimeIceAGI/tests/test_batch_evaluator_runner.py`
- Test: `F:/PrimeIceAGI/tests/test_batch_eval_service.py`
- Test: `F:/PrimeIceAGI/tests/test_batch_eval_routes.py`
- Test: `F:/PrimeIceAGI/tests/test_report_exporter.py`
- Test: `F:/PrimeIceAGI/tests/test_api_routes.py`

- [ ] **Step 1: Run the hardening test suite**

Run: `pytest F:/PrimeIceAGI/tests/test_dataset_loader.py F:/PrimeIceAGI/tests/test_batch_progress_store.py F:/PrimeIceAGI/tests/test_batch_evaluator_runner.py F:/PrimeIceAGI/tests/test_batch_eval_service.py F:/PrimeIceAGI/tests/test_batch_eval_routes.py F:/PrimeIceAGI/tests/test_report_exporter.py F:/PrimeIceAGI/tests/test_api_routes.py -v`
Expected: PASS

- [ ] **Step 2: Run the broader batch regression slice**

Run: `pytest F:/PrimeIceAGI/tests/test_batch_*.py F:/PrimeIceAGI/tests/test_api_routes.py -v`
Expected: PASS

- [ ] **Step 3: Manual smoke check with real-world schema**

Run a small batch task using a 1-2 row fixture that uses these headers:

```text
用例编号,类别名称,子类型,测试内容
```

Verify the task output directory contains:

```text
reports/batch/<task_id>/progress.json
reports/batch/<task_id>/results.jsonl
reports/batch/<task_id>/batch-report.xlsx
```

Open `batch-report.xlsx` and confirm the workbook headers are Chinese.

- [ ] **Step 4: Commit**

```bash
git add F:/PrimeIceAGI/tests
git commit -m "test: verify hardened batch evaluation flow"
```

## Self-review

- Spec coverage: This plan covers the user-requested xlsx import, Chinese header compatibility, input-format guidance, cooperative stop behavior, stronger progress/history mechanisms, and Chinese XLSX workbook labels. It stays within the current `/batch` architecture rather than introducing a separate batch history page.
- Placeholder scan: No `TODO`/`TBD` placeholders remain. All validation, progress, route, and exporter steps specify exact file paths, test names, commands, and representative code shapes.
- Type consistency: The plan consistently keeps `BatchEvalConfig`, `BatchEvalResult`, `BatchProgressStore`, `run_batch_evaluation`, and `batch_eval_service` naming aligned with the current codebase. New history support is routed through `/api/batch-eval/history` everywhere.
