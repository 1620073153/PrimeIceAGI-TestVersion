"""Session history routes — thin layer delegating to session_service."""

from flask import Blueprint
from backend.services import session_service
from backend.response import ok, err

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.route("/api/sessions")
def sessions_list():
    return ok({"sessions": session_service.list_all()})


@sessions_bp.route("/api/sessions/<session_id>")
def sessions_detail(session_id: str):
    data = session_service.get_detail(session_id)
    if data is None:
        return err("会话不存在", 404)
    return ok(data)


@sessions_bp.route("/api/sessions/<session_id>", methods=["DELETE"])
def sessions_delete(session_id: str):
    if not session_service.delete(session_id):
        return err("删除失败", 500)
    return ok()
