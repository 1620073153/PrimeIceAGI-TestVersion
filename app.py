"""
PrimeIceAGI — 大模型内容安全红队自动化测试平台
====================================================
Flask 后端: SSE 实时推送 + 多轮调度 + 引擎驱动
无外部依赖 (无需 n8n / Docker)，一键启动即用
"""

import sys
import os
import uuid
import logging
from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

from backend.response import err

from data.kb_store import ensure_seed_files
from backend.routes import register_blueprints
from backend.middleware import init_security


def _setup_logging():
    """配置根日志：控制台 + 文件输出"""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.join(log_dir, "primeice.log"), encoding="utf-8"
            ),
        ],
    )


def create_app() -> Flask:
    """工厂函数：创建并配置 Flask app"""
    _setup_logging()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = str(uuid.uuid4())

    # 安全中间件（Token 认证 + 频率限制）
    init_security(app)

    # 注册所有路由 Blueprint
    register_blueprints(app)

    # 全局错误处理器
    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            return err(e.description, e.code)
        return err(f"服务器内部错误: {str(e)[:200]}", 500)

    # 页面路由（保留在 app.py，因为依赖 templates/ 目录）
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/batch")
    def batch_eval_page():
        return render_template("batch.html")

    return app


app = create_app()


if __name__ == "__main__":
    ensure_seed_files()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5020

    # 将 PID 写入文件，供 start.bat 精确终止本进程
    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".app_pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    print(f"\n  ◆ PrimeIceAGI v2 — 大模型内容安全红队自动化测试平台")
    print(f"  ◆ 前端页面: http://localhost:{port}")
    print(f"  ◆ API 端点: http://localhost:{port}/api/health\n")
    try:
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    finally:
        try:
            os.remove(pid_file)
        except OSError:
            pass
