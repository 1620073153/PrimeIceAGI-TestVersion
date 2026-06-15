from pathlib import Path


START_BAT = Path(__file__).resolve().parents[1] / "start.bat"


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
