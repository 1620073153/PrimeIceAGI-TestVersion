"""Knowledge base routes — thin layer delegating to kb_service."""

from flask import Blueprint, request
from backend.services import kb_service
from backend.response import ok, err
from backend.schemas import ValidationError

kb_bp = Blueprint("kb", __name__)


@kb_bp.route("/api/knowledge/standards")
def get_standards():
    return ok(kb_service.get_standards())


@kb_bp.route("/api/knowledge/concepts")
def get_concepts():
    return ok(kb_service.get_concepts())


@kb_bp.route("/api/knowledge/methods")
def get_methods():
    return ok(kb_service.get_methods())


@kb_bp.route("/api/knowledge/templates")
def get_templates():
    return ok(kb_service.get_templates())


@kb_bp.route("/api/kb/list")
def kb_list():
    return ok({"kbs": kb_service.list_kbs()})


@kb_bp.route("/api/kb/<kb_id>/data")
def kb_data(kb_id: str):
    try:
        return ok(kb_service.get_kb_data(kb_id))
    except ValidationError as e:
        return err(e.message, 400)


@kb_bp.route("/api/kb/<kb_id>/entries", methods=["POST"])
def kb_create_entry(kb_id: str):
    try:
        entry = request.get_json(force=True)
        kb_service.create_entry(kb_id, entry)
        return ok()
    except ValidationError as e:
        return err(e.message, 400)


@kb_bp.route("/api/kb/<kb_id>/entries/<entry_key>", methods=["PUT"])
def kb_update_entry(kb_id: str, entry_key: str):
    try:
        updates = request.get_json(force=True)
        kb_service.update_entry(kb_id, entry_key, updates)
        return ok()
    except ValidationError as e:
        return err(e.message, 400)


@kb_bp.route("/api/kb/<kb_id>/entries/<entry_key>", methods=["DELETE"])
def kb_delete_entry(kb_id: str, entry_key: str):
    try:
        kb_service.delete_entry(kb_id, entry_key)
        return ok()
    except ValidationError as e:
        return err(e.message, 400)


@kb_bp.route("/api/kb/kb5/inferences", methods=["GET"])
def kb5_list_inferences():
    from data.kb_store import load_kb5
    return ok(load_kb5())


@kb_bp.route("/api/kb/kb5/inferences/<inference_id>", methods=["DELETE"])
def kb5_delete_inference(inference_id: str):
    if not kb_service.delete_inference(inference_id):
        return err("删除失败", 500)
    return ok()
