# Claude isolated startup implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the GitHub-delivered PrimeIceAGI startup flow keep the service running and visible in the console while allowing users to finish project-local Claude configuration in the web UI and immediately start testing without relying on any global Claude profile.

**Architecture:** Keep `start.bat` focused on launching the web service and leaving the window attached to Flask request logs. Move Claude readiness gating to backend preflight validation executed by `/api/test/start`, and keep all persisted Claude settings under `config/agent_home/.claude/`. Ship only the project-local Claude skeleton and template files, never real secrets or runtime telemetry.

**Tech Stack:** Windows batch script, Flask routes/services, Python file/JSON validation, existing Claude CLI subprocess wrapper, frontend fetch/toast flow, pytest.

---

## File structure

**Create:**
- `F:/PrimeIceAGI/tests/test_claude_preflight.py` — backend preflight tests for project-local Claude readiness checks.

**Modify:**
- `F:/PrimeIceAGI/start.bat` — keep service startup non-blocking for missing Claude config, update prompts to match the isolated project-local setup.
- `F:/PrimeIceAGI/backend/routes/health.py` — expose project-local Claude config status/readiness summary for UI use.
- `F:/PrimeIceAGI/backend/routes/test.py` — return backend validation errors from `/api/test/start` before background task creation.
- `F:/PrimeIceAGI/backend/services/test_service.py` — add Claude preflight validation before creating a task thread.
- `F:/PrimeIceAGI/backend/schemas.py` — keep request schema validation focused on payload shape only.
- `F:/PrimeIceAGI/engine/claude_agent.py` — add reusable project-local Claude readiness helpers and minimal `claude -p` preflight probe.
- `F:/PrimeIceAGI/static/js/app.js` — show clearer frontend feedback when start is blocked by missing project-local Claude setup.
- `F:/PrimeIceAGI/tests/test_start_bat.py` — lock in the new non-blocking startup messaging.
- `F:/PrimeIceAGI/tests/test_api_routes.py` — cover config status/readiness endpoints and `/api/test/start` validation behavior.
- `F:/PrimeIceAGI/.gitignore` — keep secrets/runtime telemetry ignored while allowing the required local Claude skeleton/template files into Git.

**Keep tracked in repo (after `.gitignore` adjustment):**
- `F:/PrimeIceAGI/config/agent_home/.claude/CLAUDE.md`
- `F:/PrimeIceAGI/config/agent_home/.claude/skills/prompt-skill/SKILL.md`
- `F:/PrimeIceAGI/config/agent_home/.claude/skills/prompt-skill/evals/evals.json`
- `F:/PrimeIceAGI/config/agent_home/.claude/settings.json.example`

**Must remain ignored:**
- `F:/PrimeIceAGI/config/agent_home/.claude/settings.json`
- `F:/PrimeIceAGI/config/agent_home/.claude/projects/`
- `F:/PrimeIceAGI/config/agent_home/.claude/tasks/`
- `F:/PrimeIceAGI/config/agent_home/.claude/telemetry/`
- `F:/PrimeIceAGI/config/agent_home/.claude/.last-cleanup`
- any other secret-bearing runtime state.

---

### Task 1: Make `start.bat` launch the service even when Claude is not configured

**Files:**
- Modify: `F:/PrimeIceAGI/start.bat`
- Test: `F:/PrimeIceAGI/tests/test_start_bat.py`

- [ ] **Step 1: Write the failing test**

```python
def test_start_bat_treats_missing_agent_settings_as_non_blocking_notice():
    content = START_BAT.read_text(encoding="utf-8")

    assert "Project-local Claude config not found yet." in content
    assert "Open the web UI, fill Agent URL / Key / Model, then start testing." in content
    assert "goto :fail" not in content.split('if not exist "config\\agent_home\\.claude\\settings.json" (', 1)[1].split(") else (", 1)[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest F:/PrimeIceAGI/tests/test_start_bat.py::test_start_bat_treats_missing_agent_settings_as_non_blocking_notice -v`
Expected: FAIL because the new notice strings do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Update the missing-settings branch in `start.bat` to print a project-local notice and continue launching the service:

```bat
if not exist "config\agent_home\.claude\settings.json" (
    echo         INFO: Project-local Claude config not found yet.
    echo         Open the web UI, fill Agent URL / Key / Model, then start testing.
    echo         Config will be written into config\agent_home\.claude\settings.json.
) else (
    echo         OK: Project-local Claude config file detected
)
```

Also update the existing success line so it says `Project-local Claude config file detected` instead of the older generic wording.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest F:/PrimeIceAGI/tests/test_start_bat.py::test_start_bat_treats_missing_agent_settings_as_non_blocking_notice -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/start.bat F:/PrimeIceAGI/tests/test_start_bat.py
git commit -m "fix: keep startup non-blocking for Claude setup"
```

### Task 2: Track the project-local Claude skeleton while keeping secrets ignored

**Files:**
- Modify: `F:/PrimeIceAGI/.gitignore`

- [ ] **Step 1: Write the failing test**

There is no existing `.gitignore` test harness, so use an assertion in `tests/test_start_bat.py` to pin the required ignore policy:

```python
def test_gitignore_keeps_local_claude_template_but_ignores_runtime_state():
    content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "config/agent_home/.claude/settings.json" in content
    assert "!config/agent_home/.claude/settings.json.example" in content
    assert "!config/agent_home/.claude/CLAUDE.md" in content
    assert "!config/agent_home/.claude/skills/prompt-skill/SKILL.md" in content
    assert "config/agent_home/.claude/telemetry/" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest F:/PrimeIceAGI/tests/test_start_bat.py::test_gitignore_keeps_local_claude_template_but_ignores_runtime_state -v`
Expected: FAIL because the allowlist lines do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add explicit unignore rules below the existing `config/agent_home/.claude/` runtime ignores:

```gitignore
config/agent_home/.claude/settings.json
config/agent_home/.claude/backups/
config/agent_home/.claude/projects/
config/agent_home/.claude/tasks/
config/agent_home/.claude/telemetry/
config/agent_home/.claude/.last-cleanup
config/agent_home/.claude.json

!config/agent_home/.claude/CLAUDE.md
!config/agent_home/.claude/settings.json.example
!config/agent_home/.claude/skills/
!config/agent_home/.claude/skills/prompt-skill/
!config/agent_home/.claude/skills/prompt-skill/SKILL.md
!config/agent_home/.claude/skills/prompt-skill/evals/
!config/agent_home/.claude/skills/prompt-skill/evals/evals.json
```

Do not unignore `settings.json`, `projects/`, `tasks/`, `telemetry/`, backups, or `.last-cleanup`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest F:/PrimeIceAGI/tests/test_start_bat.py::test_gitignore_keeps_local_claude_template_but_ignores_runtime_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/.gitignore F:/PrimeIceAGI/tests/test_start_bat.py F:/PrimeIceAGI/config/agent_home/.claude/CLAUDE.md F:/PrimeIceAGI/config/agent_home/.claude/settings.json.example F:/PrimeIceAGI/config/agent_home/.claude/skills/prompt-skill/SKILL.md F:/PrimeIceAGI/config/agent_home/.claude/skills/prompt-skill/evals/evals.json
git commit -m "chore: track isolated Claude skeleton"
```

### Task 3: Add backend Claude preflight helpers for project-local validation

**Files:**
- Modify: `F:/PrimeIceAGI/engine/claude_agent.py`
- Create: `F:/PrimeIceAGI/tests/test_claude_preflight.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from engine import claude_agent


def test_get_project_local_claude_status_reports_missing_settings(tmp_path: Path, monkeypatch):
    agent_home = tmp_path / "agent_home"
    skill_file = agent_home / ".claude" / "skills" / "prompt-skill" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# prompt skill", encoding="utf-8")

    monkeypatch.setattr(claude_agent, "AGENT_HOME", str(agent_home))

    status = claude_agent.get_project_local_claude_status()

    assert status["cli_available"] in (True, False)
    assert status["settings_exists"] is False
    assert status["prompt_skill_exists"] is True
    assert status["ready"] is False
    assert "URL / Key / Model" in status["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest F:/PrimeIceAGI/tests/test_claude_preflight.py::test_get_project_local_claude_status_reports_missing_settings -v`
Expected: FAIL because `get_project_local_claude_status` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add helpers in `engine/claude_agent.py`:

```python
from pathlib import Path


def _agent_claude_dir() -> Path:
    return Path(AGENT_HOME) / ".claude"


def _agent_settings_path() -> Path:
    return _agent_claude_dir() / "settings.json"


def _prompt_skill_path() -> Path:
    return _agent_claude_dir() / "skills" / "prompt-skill" / "SKILL.md"


def _claude_cli_available() -> bool:
    try:
        completed = subprocess.run(
            ["claude", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            shell=True,
        )
        return completed.returncode == 0
    except OSError:
        return False


def get_project_local_claude_status() -> dict:
    settings_path = _agent_settings_path()
    prompt_skill_path = _prompt_skill_path()
    settings_exists = settings_path.exists()
    prompt_skill_exists = prompt_skill_path.exists()
    cli_available = _claude_cli_available()

    if not cli_available:
        message = "Claude Code CLI 不可用，请先安装项目要求的 Claude CLI。"
    elif not prompt_skill_exists:
        message = "项目内 prompt-skill 缺失，请重新获取完整发布包。"
    elif not settings_exists:
        message = "项目内 Claude 尚未配置，请先在前端填写并保存 URL / Key / Model。"
    else:
        message = "项目内 Claude 基础配置已就绪。"

    return {
        "cli_available": cli_available,
        "settings_exists": settings_exists,
        "prompt_skill_exists": prompt_skill_exists,
        "settings_path": str(settings_path),
        "ready": bool(cli_available and prompt_skill_exists and settings_exists),
        "message": message,
    }
```

Do not run `claude -p` yet in this task; this task is only structural status.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest F:/PrimeIceAGI/tests/test_claude_preflight.py::test_get_project_local_claude_status_reports_missing_settings -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/engine/claude_agent.py F:/PrimeIceAGI/tests/test_claude_preflight.py
git commit -m "feat: add project-local Claude status helpers"
```

### Task 4: Add a minimal backend preflight probe before test start

**Files:**
- Modify: `F:/PrimeIceAGI/engine/claude_agent.py`
- Modify: `F:/PrimeIceAGI/backend/services/test_service.py`
- Modify: `F:/PrimeIceAGI/backend/routes/test.py`
- Modify: `F:/PrimeIceAGI/tests/test_api_routes.py`
- Modify: `F:/PrimeIceAGI/tests/test_claude_preflight.py`

- [ ] **Step 1: Write the failing test**

```python
def test_start_test_returns_400_when_project_local_claude_not_ready(client, monkeypatch):
    monkeypatch.setattr(
        "backend.services.test_service.validate_claude_ready_for_start",
        lambda config: {"ok": False, "message": "项目内 Claude 尚未配置，请先在前端填写并保存 URL / Key / Model。"},
    )

    r = client.post(
        "/api/test/start",
        json={
            "target_api_url": "https://example.com",
            "target_api_key": "secret",
        },
    )

    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "项目内 Claude 尚未配置" in payload["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest F:/PrimeIceAGI/tests/test_api_routes.py::test_start_test_returns_400_when_project_local_claude_not_ready -v`
Expected: FAIL because no Claude preflight is executed before task creation.

- [ ] **Step 3: Write minimal implementation**

In `engine/claude_agent.py`, add a reusable start preflight:

```python
def validate_claude_ready_for_start(config: dict) -> dict:
    status = get_project_local_claude_status()
    if not status["cli_available"]:
        return {"ok": False, "message": status["message"]}
    if not status["prompt_skill_exists"]:
        return {"ok": False, "message": status["message"]}
    if not status["settings_exists"]:
        return {"ok": False, "message": status["message"]}
    return {"ok": True, "message": "ok"}
```

In `backend/services/test_service.py`, call it before creating the task:

```python
from engine.claude_agent import validate_claude_ready_for_start
from backend.schemas import ValidationError


def start_test(config: dict) -> str:
    config = validate_test_config(config)
    preflight = validate_claude_ready_for_start(config)
    if not preflight["ok"]:
        raise ValidationError(preflight["message"])
    task_id = _tm.create_task(config)
    ...
```

No background thread should be created when preflight fails.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest F:/PrimeIceAGI/tests/test_api_routes.py::test_start_test_returns_400_when_project_local_claude_not_ready -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/engine/claude_agent.py F:/PrimeIceAGI/backend/services/test_service.py F:/PrimeIceAGI/backend/routes/test.py F:/PrimeIceAGI/tests/test_api_routes.py F:/PrimeIceAGI/tests/test_claude_preflight.py
git commit -m "fix: block test start when isolated Claude is not ready"
```

### Task 5: Expose Claude config status to the frontend

**Files:**
- Modify: `F:/PrimeIceAGI/backend/routes/health.py`
- Modify: `F:/PrimeIceAGI/tests/test_api_routes.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_claude_agent_config_includes_status_summary(client, monkeypatch):
    monkeypatch.setattr(
        "backend.routes.health.get_project_local_claude_status",
        lambda: {
            "cli_available": True,
            "settings_exists": False,
            "prompt_skill_exists": True,
            "settings_path": "config/agent_home/.claude/settings.json",
            "ready": False,
            "message": "项目内 Claude 尚未配置，请先在前端填写并保存 URL / Key / Model。",
        },
    )

    r = client.get("/api/claude-agent/config")
    payload = r.get_json()

    assert payload["ok"] is True
    assert payload["data"]["status"]["ready"] is False
    assert "URL / Key / Model" in payload["data"]["status"]["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest F:/PrimeIceAGI/tests/test_api_routes.py::test_get_claude_agent_config_includes_status_summary -v`
Expected: FAIL because the route only returns url/key/model today.

- [ ] **Step 3: Write minimal implementation**

In `backend/routes/health.py`, import the helper and include the status object in both file-present and file-missing branches:

```python
from engine.claude_agent import AGENT_HOME, get_project_local_claude_status

...
status = get_project_local_claude_status()
return jsonify({
    "ok": True,
    "data": {
        "url": env.get("ANTHROPIC_BASE_URL", ""),
        "key": env.get("ANTHROPIC_AUTH_TOKEN", ""),
        "model": env.get("ANTHROPIC_MODEL", ""),
        "status": status,
    }
})
```

For the `FileNotFoundError` branch, return empty fields plus the same `status` object.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest F:/PrimeIceAGI/tests/test_api_routes.py::test_get_claude_agent_config_includes_status_summary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/backend/routes/health.py F:/PrimeIceAGI/tests/test_api_routes.py
git commit -m "feat: expose isolated Claude status in config API"
```

### Task 6: Surface backend Claude readiness feedback in the UI

**Files:**
- Modify: `F:/PrimeIceAGI/static/js/app.js`

- [ ] **Step 1: Write the failing test**

Use an inline DOM-oriented assertion pattern already used in the repo’s frontend tests, or add a tiny JS unit if that is the established pattern. The behavior to lock is:

```javascript
// Pseudocode expectation for existing frontend harness
loadClaudeCfg();
// mocked payload includes status.ready=false and status.message
// expected: #claude-cfg-status shows the backend message
```

If there is no JS test harness for this file, document the failure manually in the task branch by reproducing with browser devtools and then add the minimal automated coverage to the closest existing test file.

- [ ] **Step 2: Run test to verify it fails**

Run the closest existing frontend/static asset test covering `static/js/app.js` behavior.
Expected: FAIL or missing coverage showing the status text is not surfaced yet.

- [ ] **Step 3: Write minimal implementation**

In `loadClaudeCfg()` inside `static/js/app.js`, after filling `url/key/model`, surface the backend status message:

```javascript
var status = data.status || {};
var st = document.getElementById('claude-cfg-status');
if (st) {
  st.textContent = status.message || '';
  st.style.color = status.ready ? 'var(--success)' : 'var(--warning)';
}
```

Also keep the existing save success/failure text, but after a successful save call `loadClaudeCfg()` again so the refreshed readiness state is shown immediately.

- [ ] **Step 4: Run test to verify it passes**

Run the chosen frontend/static asset test.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add F:/PrimeIceAGI/static/js/app.js
git commit -m "feat: show isolated Claude readiness in UI"
```

### Task 7: Run the focused and full verification suites

**Files:**
- Modify: any files touched by prior tasks only if verification reveals breakage.

- [ ] **Step 1: Run focused tests for startup and Claude validation**

Run: `pytest F:/PrimeIceAGI/tests/test_start_bat.py F:/PrimeIceAGI/tests/test_claude_preflight.py F:/PrimeIceAGI/tests/test_api_routes.py -v`
Expected: PASS

- [ ] **Step 2: Run the full regression suite**

Run: `pytest F:/PrimeIceAGI -q`
Expected: PASS with the full suite green.

- [ ] **Step 3: Verify tracked files match the delivery intent**

Run:

```bash
git status --short
git ls-files F:/PrimeIceAGI/config/agent_home/.claude
```

Expected:
- tracked: `CLAUDE.md`, `settings.json.example`, `skills/prompt-skill/SKILL.md`, `skills/prompt-skill/evals/evals.json`
- untracked/ignored only for runtime files such as `settings.json`, `projects/`, `tasks/`, `telemetry/`

- [ ] **Step 4: Commit final verification fixes if needed**

```bash
git add <only files changed during verification>
git commit -m "test: finalize isolated Claude startup verification"
```

Only create this commit if verification required code changes. If no files changed, skip committing.

---

## Self-review

- Spec coverage: covers non-blocking service startup, project-local Claude skeleton tracking, backend start-time preflight, frontend config feedback, and regression verification.
- Placeholder scan: the only intentionally flexible spot is choosing the closest existing frontend/static test harness for `app.js`; if none exists, implementation should add the smallest viable automated coverage before claiming completion.
- Type consistency: `get_project_local_claude_status()` and `validate_claude_ready_for_start()` are named consistently across route/service/test tasks.

---

Plan complete and saved to `docs/superpowers/plans/2026-06-16-claude-isolated-startup.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
