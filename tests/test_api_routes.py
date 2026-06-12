"""API 路由测试 — 验证各端点基本行为"""

from app import create_app
import pytest


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestHealth:
    def test_health_endpoint(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"

    def test_index_page_renders(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"PrimeIceAGI" in r.data


class TestProbe:
    def test_probe_missing_params(self, client):
        r = client.post("/api/probe", json={})
        data = r.get_json()
        assert data["reachable"] is False
        assert "缺少" in data["error"]

    def test_probe_unreachable_host(self, client):
        r = client.post("/api/probe", json={
            "api_url": "http://127.0.0.1:1",
            "api_key": "test-key",
            "model": "test",
        })
        data = r.get_json()
        assert data["reachable"] is False


class TestClaudeAgentConfig:
    def test_get_config_no_file(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "backend.routes.health.AGENT_SETTINGS_PATH",
            str(tmp_path / "nonexistent.json")
        )
        r = client.get("/api/claude-agent/config")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["data"]["url"] == ""

    def test_save_config_missing_fields(self, client):
        r = client.post("/api/claude-agent/config", json={"url": "", "key": "", "model": ""})
        assert r.status_code == 400


class TestKbRoutes:
    def test_get_kb1_data(self, client):
        r = client.get("/api/kb/kb1/data")
        assert r.status_code == 200
        data = r.get_json()
        assert "data" in data or "categories" in data.get("data", data)

    def test_get_kb_invalid_id(self, client):
        r = client.get("/api/kb/kb99/data")
        assert r.status_code in (200, 400, 404)
