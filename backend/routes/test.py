"""Test control routes — thin layer delegating to test_service."""

import json
from flask import Blueprint, request, Response
from backend.services import test_service
from backend.response import ok, err
from backend.schemas import ValidationError

test_bp = Blueprint("test", __name__)


@test_bp.route("/api/test/start", methods=["POST"])
def start_test():
    try:
        config = request.get_json(force=True)
        task_id = test_service.start_test(config)
        return ok({"task_id": task_id})
    except ValidationError as e:
        return err(e.message, 400)


@test_bp.route("/api/test/<task_id>/stream")
def stream(task_id: str):
    events = test_service.subscribe_events(task_id)
    if events is None:
        return err("任务不存在或已过期", 404)

    def generate():
        for event in events:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("event") in ("complete", "aborted", "error"):
                break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@test_bp.route("/api/test/<task_id>/status")
def task_status(task_id: str):
    status = test_service.get_status(task_id)
    if not status:
        return err("任务不存在", 404)
    return ok(status)


@test_bp.route("/api/test/<task_id>/stop", methods=["POST"])
def stop_test(task_id: str):
    if not test_service.stop_test(task_id):
        return err("任务不存在", 404)
    return ok({"status": "stopped"})


@test_bp.route("/api/test/<task_id>/report")
def get_report(task_id: str):
    report = test_service.get_report(task_id)
    if report is None:
        return err("任务不存在", 404)
    if "error" in report:
        return err(report["error"], 400)
    return ok(report)
