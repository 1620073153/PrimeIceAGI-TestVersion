from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_BAT = PROJECT_ROOT / "start.bat"
GITATTRIBUTES = PROJECT_ROOT / ".gitattributes"


def test_start_bat_opens_existing_healthy_service_when_port_is_in_use():
    content = START_BAT.read_text(encoding="utf-8")

    assert "call :probe_existing_service" in content
    assert "goto :open_browser" in content
    assert "Found running PrimeIceAGI service" in content
    assert "Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%'" in content


def test_start_bat_checks_embedded_runtime():
    content = START_BAT.read_text(encoding="utf-8")

    assert "runtime\\python\\python.exe" in content
    assert "import flask, requests" in content


def test_start_bat_uses_windows_crlf_line_endings():
    raw = START_BAT.read_bytes()

    assert b"\r\n" in raw
    assert raw.count(b"\r\n") >= raw.count(b"\n") - 1


def test_start_bat_probes_port_before_starting():
    content = START_BAT.read_text(encoding="utf-8")

    assert "call :check_port" in content
    assert ":port_maybe_existing" in content
    assert "Get-NetTCPConnection" in content


def test_gitattributes_forces_crlf_for_bat_files():
    content = GITATTRIBUTES.read_text(encoding="utf-8")

    assert "*.bat text eol=crlf" in content
