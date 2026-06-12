"""Unified JSON response helpers."""

from flask import jsonify


def ok(data=None):
    body = {"ok": True}
    if data is not None:
        body["data"] = data
    return jsonify(body)


def err(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code
