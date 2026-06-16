from pathlib import Path

from engine import claude_agent


def test_get_project_local_claude_status_reports_missing_settings(tmp_path: Path, monkeypatch):
    agent_home = tmp_path / "agent_home"
    skill_file = agent_home / ".claude" / "skills" / "prompt-skill" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# prompt skill", encoding="utf-8")

    monkeypatch.setattr(claude_agent, "AGENT_HOME", str(agent_home))
    monkeypatch.setattr(claude_agent, "_claude_cli_available", lambda: True)

    status = claude_agent.get_project_local_claude_status()

    assert status["cli_available"] is True
    assert status["settings_exists"] is False
    assert status["prompt_skill_exists"] is True
    assert status["ready"] is False
    assert "URL / Key / Model" in status["message"]


def test_get_project_local_claude_status_rejects_placeholder_settings(tmp_path: Path, monkeypatch):
    agent_home = tmp_path / "agent_home"
    claude_dir = agent_home / ".claude"
    skill_file = claude_dir / "skills" / "prompt-skill" / "SKILL.md"
    settings_file = claude_dir / "settings.json"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# prompt skill", encoding="utf-8")
    settings_file.write_text(
        '{"env":{"ANTHROPIC_AUTH_TOKEN":"your-api-key-here","ANTHROPIC_BASE_URL":"https://api.deepseek.com/anthropic","ANTHROPIC_MODEL":"deepseek-v4-flash"}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(claude_agent, "AGENT_HOME", str(agent_home))
    monkeypatch.setattr(claude_agent, "_claude_cli_available", lambda: True)

    status = claude_agent.get_project_local_claude_status()

    assert status["settings_exists"] is True
    assert status["settings_valid"] is False
    assert status["ready"] is False
    assert "尚未完成" in status["message"]


def test_get_project_local_claude_status_reports_invalid_json(tmp_path: Path, monkeypatch):
    agent_home = tmp_path / "agent_home"
    claude_dir = agent_home / ".claude"
    skill_file = claude_dir / "skills" / "prompt-skill" / "SKILL.md"
    settings_file = claude_dir / "settings.json"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# prompt skill", encoding="utf-8")
    settings_file.write_text("{bad json", encoding="utf-8")

    monkeypatch.setattr(claude_agent, "AGENT_HOME", str(agent_home))
    monkeypatch.setattr(claude_agent, "_claude_cli_available", lambda: True)

    status = claude_agent.get_project_local_claude_status()

    assert status["settings_exists"] is True
    assert status["settings_valid"] is False
    assert status["ready"] is False
    assert "配置文件损坏" in status["message"]


def test_validate_claude_ready_for_start_requires_settings(monkeypatch):
    monkeypatch.setattr(
        claude_agent,
        "get_project_local_claude_status",
        lambda: {
            "cli_available": True,
            "settings_exists": False,
            "settings_valid": False,
            "prompt_skill_exists": True,
            "settings_path": "config/agent_home/.claude/settings.json",
            "ready": False,
            "message": "项目内 Claude 尚未配置，请先在前端填写并保存 URL / Key / Model。",
        },
    )

    result = claude_agent.validate_claude_ready_for_start({})

    assert result["ok"] is False
    assert "URL / Key / Model" in result["message"]


def test_validate_claude_ready_for_start_rejects_placeholder_settings(monkeypatch):
    monkeypatch.setattr(
        claude_agent,
        "get_project_local_claude_status",
        lambda: {
            "cli_available": True,
            "settings_exists": True,
            "settings_valid": False,
            "prompt_skill_exists": True,
            "settings_path": "config/agent_home/.claude/settings.json",
            "ready": False,
            "message": "项目内 Claude 配置尚未完成，请在前端填写有效的 URL / Key / Model。",
        },
    )

    result = claude_agent.validate_claude_ready_for_start({})

    assert result["ok"] is False
    assert "尚未完成" in result["message"]
