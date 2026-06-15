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

    def test_index_page_links_to_batch_eval(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"/batch" in r.data

    def test_batch_page_renders(self, client):
        r = client.get("/batch")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert "批量评估" in html
        assert "最近结果" in html
        assert "需人工复核" in html
        assert "支持 CSV / XLSX" in html
        assert "测试内容（必填）" in html
        assert "历史任务" in html
        assert "查看摘要" in html
        assert "运行时间" in html
        assert "支持 CSV / XLSX" in html
        assert "每行一个具体文件路径" in html
        assert "不支持只填目录" in html
        assert "用例编号/类别名称/子类型/测试内容（必填）" in html
        assert "历史任务" in html
        assert "batch-history-list" in html
        assert "完成进度" in html
        assert "当前样本" in html
        assert "最近结论" in html
        assert "最近理由" in html


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
