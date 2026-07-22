"""Batch evaluation routes — thin layer delegating to batch_eval_service."""

import json
from pathlib import Path
from flask import Blueprint, Response, request, send_file

from backend.response import ok, err
from backend.services import batch_eval_service

batch_eval_bp = Blueprint("batch_eval", __name__)


@batch_eval_bp.route("/api/batch-eval/start", methods=["POST"])
def start_batch_eval():
    try:
        config = request.get_json(force=True)
        task_id = batch_eval_service.start_batch_eval(config)
        return ok({"task_id": task_id})
    except ValueError as exc:
        return err(str(exc), 400)


@batch_eval_bp.route("/api/batch-eval/<task_id>/stream")
def stream(task_id: str):
    events = batch_eval_service.subscribe_events(task_id)
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


@batch_eval_bp.route("/api/batch-eval/<task_id>/status")
def task_status(task_id: str):
    status = batch_eval_service.get_status(task_id)
    if not status:
        return err("任务不存在", 404)
    return ok(status)


@batch_eval_bp.route("/api/batch-eval/history")
def history():
    limit = request.args.get("limit", default=20, type=int) or 20
    limit = max(1, min(limit, 100))
    return ok(batch_eval_service.list_batch_eval_tasks(limit=limit))


@batch_eval_bp.route("/api/batch-eval/<task_id>/stop", methods=["POST"])
def stop_batch_eval(task_id: str):
    if not batch_eval_service.stop_batch_eval(task_id):
        return err("任务不存在", 404)
    return ok({"status": "stopped"})


@batch_eval_bp.route("/api/batch-eval/<task_id>/resume", methods=["POST"])
def resume_batch_eval(task_id: str):
    try:
        credentials = request.get_json(force=True) or {}
        result_task_id = batch_eval_service.resume_batch_eval(task_id, credentials)
        return ok({"task_id": result_task_id})
    except ValueError as exc:
        return err(str(exc), 400)


@batch_eval_bp.route("/api/batch-eval/<task_id>/report")
def get_report(task_id: str):
    report = batch_eval_service.get_report(task_id)
    if report is None:
        return err("任务不存在", 404)
    if "error" in report:
        return err(report["error"], 400)
    return ok(report)


@batch_eval_bp.route("/api/batch-eval/<task_id>/export-current", methods=["POST"])
def export_current_report(task_id: str):
    try:
        result = batch_eval_service.export_current_report(task_id)
        if result is None:
            return err("任务不存在或无已完成结果", 404)
        return ok(result)
    except ValueError as exc:
        return err(str(exc), 400)


@batch_eval_bp.route("/api/batch-eval/<task_id>/download/<filename>")
def download_report_file(task_id: str, filename: str):
    file_path = batch_eval_service.resolve_download_file(task_id, filename)
    if file_path is None:
        return err("文件不存在", 404)
    return send_file(file_path, as_attachment=True, download_name=filename)
