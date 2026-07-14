"""报告生成路由 — 下载 Markdown/DOCX 格式测试报告"""

from flask import Blueprint, Response, send_file
from backend.services import session_service
from backend.services.report_service import generate_markdown_report
from backend.response import err

report_bp = Blueprint("report", __name__)


@report_bp.route("/api/sessions/<session_id>/report")
def download_report(session_id: str):
    data = session_service.get_detail(session_id)
    if data is None:
        return err("会话不存在", 404)

    md_content = generate_markdown_report(data)
    filename = f"report_{session_id}.md"

    return Response(
        md_content,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@report_bp.route("/api/sessions/<session_id>/report-docx")
def download_report_docx(session_id: str):
    data = session_service.get_detail(session_id)
    if data is None:
        return err("会话不存在", 404)

    from backend.services.report_docx_service import generate_docx_report

    buffer = generate_docx_report(data)
    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        download_name=f'report_{session_id}.docx',
    )
