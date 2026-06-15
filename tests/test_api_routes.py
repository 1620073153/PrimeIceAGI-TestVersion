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

    def test_get_kb5_state_endpoint(self, client, tmp_path, monkeypatch):
        kb5_file = tmp_path / "kb5.json"
        kb5_file.write_text('{"inferences": []}', encoding="utf-8")
        monkeypatch.setattr("data.kb_store.get_data_dir", lambda: str(tmp_path))
        monkeypatch.setattr("backend.services.kb_service.find_running_kb5_task_id", lambda: None)

        r = client.get("/api/kb/kb5")
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["ok"] is True
        assert payload["data"]["kb_code"] == "KB5"
        assert payload["data"]["exists"] is True
        assert payload["data"]["in_use"] is False

    def test_get_kb5_state_marks_in_use_when_task_running(self, client, monkeypatch, tmp_path):
        kb5_file = tmp_path / "kb5.json"
        kb5_file.write_text('{"inferences": []}', encoding="utf-8")
        monkeypatch.setattr("data.kb_store.get_data_dir", lambda: str(tmp_path))
        monkeypatch.setattr("backend.services.kb_service.find_running_kb5_task_id", lambda: "task-001")

        r = client.get("/api/kb/kb5")
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["data"]["in_use"] is True
        assert payload["data"]["task_id"] == "task-001"

    def test_delete_kb5_is_blocked_when_task_is_using_it(self, client, tmp_path, monkeypatch):
        kb5_file = tmp_path / "kb5.json"
        kb5_file.write_text('{"inferences": [{"round": 2, "summary": "边界"}]}', encoding="utf-8")
        monkeypatch.setattr("data.kb_store.get_data_dir", lambda: str(tmp_path))
        monkeypatch.setattr("backend.services.kb_service.find_running_kb5_task_id", lambda: "task-001")

        r = client.delete("/api/kb/kb5")

        assert r.status_code == 409
        payload = r.get_json()
        assert payload["ok"] is False
        assert payload["error"]["code"] == "KB5_IN_USE"
        assert payload["error"]["task_id"] == "task-001"
        assert "先停止任务或等待完成" in payload["error"]["message"]

    def test_delete_kb5_returns_deleted_when_idle(self, client, tmp_path, monkeypatch):
        legacy = tmp_path / "kb5_inferred_boundaries.json"
        canonical = tmp_path / "kb5.json"
        legacy.write_text('{"inferences": []}', encoding="utf-8")
        canonical.write_text('{"inferences": []}', encoding="utf-8")
        monkeypatch.setattr("data.kb_store.get_data_dir", lambda: str(tmp_path))
        monkeypatch.setattr("backend.services.kb_service.find_running_kb5_task_id", lambda: None)

        r = client.delete("/api/kb/kb5")

        assert r.status_code == 200
        payload = r.get_json()
        assert payload["ok"] is True
        assert payload["data"]["status"] == "deleted"
        assert payload["data"]["kb_code"] == "KB5"
        assert not legacy.exists()
        assert not canonical.exists()

    def test_delete_kb5_inference_is_blocked_when_task_is_using_it(self, client, tmp_path, monkeypatch):
        kb5_file = tmp_path / "kb5.json"
        kb5_file.write_text('{"inferences": [{"inference_id": "inf-001", "summary": "边界"}]}', encoding="utf-8")
        monkeypatch.setattr("data.kb_store.get_data_dir", lambda: str(tmp_path))
        monkeypatch.setattr("backend.services.kb_service.find_running_kb5_task_id", lambda: "task-001")

        r = client.delete("/api/kb/kb5/inferences/inf-001")

        assert r.status_code == 409
        payload = r.get_json()
        assert payload["ok"] is False
        assert payload["error"]["code"] == "KB5_IN_USE"
        assert payload["error"]["task_id"] == "task-001"
        assert kb5_file.exists()

    def test_delete_kb5_inference_returns_deleted_when_idle(self, client, tmp_path, monkeypatch):
        legacy = tmp_path / "kb5_inferred_boundaries.json"
        legacy.write_text('{"inferences": [{"inference_id": "inf-001", "summary": "边界"}, {"inference_id": "inf-002", "summary": "保留"}]}', encoding="utf-8")
        monkeypatch.setattr("data.kb_store.get_data_dir", lambda: str(tmp_path))
        monkeypatch.setattr("backend.services.kb_service.find_running_kb5_task_id", lambda: None)

        r = client.delete("/api/kb/kb5/inferences/inf-001")

        assert r.status_code == 200
        payload = r.get_json()
        assert payload["ok"] is True
        canonical = tmp_path / "kb5.json"
        assert canonical.exists()
        assert not legacy.exists()
        content = canonical.read_text(encoding="utf-8")
        assert "inf-001" not in content
        assert "inf-002" in content

    def test_delete_kb5_is_idempotent_when_missing(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("data.kb_store.get_data_dir", lambda: str(tmp_path))
        monkeypatch.setattr("backend.services.kb_service.find_running_kb5_task_id", lambda: None)

        r = client.delete("/api/kb/kb5")

        assert r.status_code == 200
        payload = r.get_json()
        assert payload["ok"] is True
        assert payload["data"]["status"] == "already_deleted"

    def test_index_page_contains_kb5_cleanup_entry_points(self, client):
        r = client.get("/")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert 'id="kb5-delete-btn"' in html
        assert '确认删除 KB5？' in html
        assert 'id="kb5-cleanup-actions"' in html
        assert '清理本次 KB5' in html
        assert '本次测试已完成，是否清理 KB5？' in html
