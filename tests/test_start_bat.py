from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_BAT = PROJECT_ROOT / "start.bat"
GITATTRIBUTES = PROJECT_ROOT / ".gitattributes"


def test_start_bat_opens_existing_healthy_service_when_port_is_in_use():
    content = START_BAT.read_text(encoding="utf-8")

    assert "call :probe_existing_service" in content
    assert "goto :open_browser" in content
    assert "端口 %APP_PORT% 已有可用的 PrimeIceAGI 服务" in content
    assert "Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%'" in content


def test_start_bat_calls_windows_cmd_wrappers_explicitly():
    content = START_BAT.read_text(encoding="utf-8")

    assert "call npm --version >nul 2>&1" in content
    assert "for /f \"delims=\" %%v in ('call npm --version 2^>^&1')" in content
    assert "call claude --version >nul 2>&1" in content
    assert "for /f \"delims=\" %%v in ('call claude --version 2^>^&1')" in content


def test_start_bat_uses_windows_crlf_line_endings():
    raw = START_BAT.read_bytes()

    assert b"\r\n" in raw
    assert raw.count(b"\r\n") >= raw.count(b"\n") - 1


def test_start_bat_requires_python_3_10_or_newer():
    content = START_BAT.read_text(encoding="utf-8")

    assert "sys.version_info >= (3, 10)" in content
    assert "Python 3.10+" in content


def test_start_bat_uses_ascii_fallback_hint_for_missing_agent_settings():
    content = START_BAT.read_text(encoding="utf-8")

    assert "Configure Agent URL / Key / Model in the web UI after launch." in content
    assert "请在 Web 界面" not in content


def test_gitattributes_forces_crlf_for_bat_files():
    content = GITATTRIBUTES.read_text(encoding="utf-8")

    assert "*.bat text eol=crlf" in content
