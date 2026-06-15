from app import create_app
import pytest


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_batch_eval_start_returns_task_id(client, monkeypatch):
    monkeypatch.setattr("backend.routes.batch_eval.batch_eval_service.start_batch_eval", lambda config: "batch123")

    response = client.post("/api/batch-eval/start", json={"dataset_paths": ["cases.csv"]})

    assert response.status_code == 200
    assert response.get_json()["data"]["task_id"] == "batch123"


def test_batch_eval_status_returns_404_for_missing_task(client, monkeypatch):
    monkeypatch.setattr("backend.routes.batch_eval.batch_eval_service.get_status", lambda task_id: None)

    response = client.get("/api/batch-eval/missing/status")

    assert response.status_code == 404


def test_batch_eval_status_returns_progress_payload(client, monkeypatch):
    monkeypatch.setattr(
        "backend.routes.batch_eval.batch_eval_service.get_status",
        lambda task_id: {
            "task_id": task_id,
            "finished": False,
            "stopped": False,
            "report": None,
            "progress": {"status": "running", "result_count": 2},
        },
    )

    response = client.get("/api/batch-eval/task-1/status")

    assert response.status_code == 200
    assert response.get_json()["data"]["progress"]["status"] == "running"
    assert response.get_json()["data"]["progress"]["result_count"] == 2


def test_batch_eval_report_returns_service_payload(client, monkeypatch):
    monkeypatch.setattr(
        "backend.routes.batch_eval.batch_eval_service.get_report",
        lambda task_id: {"summary": {"processed_cases": 2}, "report_file": "reports/batch.xlsx"},
    )

    response = client.get("/api/batch-eval/task-1/report")

    assert response.status_code == 200
    assert response.get_json()["data"]["summary"]["processed_cases"] == 2


def test_batch_eval_history_returns_service_payload(client, monkeypatch):
    monkeypatch.setattr(
        "backend.routes.batch_eval.batch_eval_service.list_batch_eval_tasks",
        lambda limit=20: [{
            "task_id": "task-1",
            "status": "completed",
            "created_at": 1710000000.0,
            "report_file": "reports/batch/task-1/report.xlsx",
            "summary": {"processed_cases": 2},
            "progress": {"total_cases": 5, "current_case_id": None},
            "dataset_paths": ["F:/datasets/a.csv"],
        }],
    )

    response = client.get("/api/batch-eval/history?limit=5")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data[0]["task_id"] == "task-1"
    assert data[0]["summary"]["processed_cases"] == 2
    assert data[0]["progress"]["total_cases"] == 5


def test_batch_eval_download_returns_file(client, monkeypatch, tmp_path):
    report_file = tmp_path / "report.xlsx"
    report_file.write_bytes(b"fake-xlsx")
    monkeypatch.setattr(
        "backend.routes.batch_eval.batch_eval_service.resolve_download_file",
        lambda task_id, filename: report_file,
    )

    response = client.get("/api/batch-eval/task-1/download/report.xlsx")

    assert response.status_code == 200
    assert response.data == b"fake-xlsx"
