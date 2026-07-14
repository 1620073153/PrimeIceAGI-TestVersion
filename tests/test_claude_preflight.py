from pathlib import Path

from engine import prompt_generator


def test_get_generator_status_reports_missing_settings(tmp_path: Path, monkeypatch):
    agent_home = tmp_path / "agent_home"
    (agent_home / ".claude").mkdir(parents=True)

    monkeypatch.setattr(prompt_generator, "AGENT_HOME", str(agent_home))

    status = prompt_generator.get_generator_status()

    assert status["settings_exists"] is False
    assert status["ready"] is False
    assert "URL / Key / Model" in status["message"]


def test_get_generator_status_rejects_placeholder_settings(tmp_path: Path, monkeypatch):
    agent_home = tmp_path / "agent_home"
    claude_dir = agent_home / ".claude"
    settings_file = claude_dir / "settings.json"
    claude_dir.mkdir(parents=True)
    settings_file.write_text(
        '{"env":{"ANTHROPIC_AUTH_TOKEN":"your-api-key-here","ANTHROPIC_BASE_URL":"https://api.deepseek.com/anthropic","ANTHROPIC_MODEL":"deepseek-v4-flash"}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(prompt_generator, "AGENT_HOME", str(agent_home))

    status = prompt_generator.get_generator_status()

    assert status["settings_exists"] is True
    assert status["settings_valid"] is False
    assert status["ready"] is False
    assert "尚未完成" in status["message"]


def test_get_generator_status_reports_invalid_json(tmp_path: Path, monkeypatch):
    agent_home = tmp_path / "agent_home"
    claude_dir = agent_home / ".claude"
    settings_file = claude_dir / "settings.json"
    claude_dir.mkdir(parents=True)
    settings_file.write_text("{bad json", encoding="utf-8")

    monkeypatch.setattr(prompt_generator, "AGENT_HOME", str(agent_home))

    status = prompt_generator.get_generator_status()

    assert status["settings_exists"] is True
    assert status["settings_valid"] is False
    assert status["ready"] is False
    assert "配置文件损坏" in status["message"]


def test_validate_generator_ready_requires_settings(monkeypatch):
    monkeypatch.setattr(
        prompt_generator,
        "get_generator_status",
        lambda: {
            "settings_exists": False,
            "settings_valid": False,
            "settings_path": "config/agent_home/.claude/settings.json",
            "ready": False,
            "message": "提示词生成尚未配置，请先在前端填写并保存 URL / Key / Model。",
        },
    )

    result = prompt_generator.validate_generator_ready({})

    assert result["ok"] is False
    assert "URL / Key / Model" in result["message"]


def test_validate_generator_ready_rejects_placeholder_settings(monkeypatch):
    monkeypatch.setattr(
        prompt_generator,
        "get_generator_status",
        lambda: {
            "settings_exists": True,
            "settings_valid": False,
            "settings_path": "config/agent_home/.claude/settings.json",
            "ready": False,
            "message": "提示词生成配置尚未完成，请在前端填写有效的 URL / Key / Model。",
        },
    )

    result = prompt_generator.validate_generator_ready({})

    assert result["ok"] is False
    assert "尚未完成" in result["message"]
