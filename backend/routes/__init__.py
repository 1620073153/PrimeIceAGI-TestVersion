"""Blueprint 注册中心"""

from flask import Flask

from backend.routes.batch_eval import batch_eval_bp
from backend.routes.health import health_bp
from backend.routes.kb import kb_bp
from backend.routes.sessions import sessions_bp
from backend.routes.test import test_bp


def register_blueprints(app: Flask):
    """注册所有 Blueprint 到 Flask app"""
    app.register_blueprint(health_bp)
    app.register_blueprint(kb_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(batch_eval_bp)
