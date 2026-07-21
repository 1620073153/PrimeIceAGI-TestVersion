"""DOCX 政务报告生成服务 — 参考信息中心模型评测格式"""

from io import BytesIO
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT


def _load_categories():
    from data.kb_store import load_kb
    kb1 = load_kb("kb1")
    return kb1.get("categories", {})


def _severity_label(cat_key: str) -> tuple[str, RGBColor]:
    """根据子类前缀对应的 priority 返回 (等级文字, 颜色)"""
    categories = _load_categories()
    prefix = cat_key.split("-")[0] if "-" in cat_key else cat_key
    cat = categories.get(prefix, {})
    priority = cat.get("priority", "P1")
    mapping = {
        "P0": ("严重", RGBColor(0xCC, 0x00, 0x00)),
        "P1": ("高危", RGBColor(0xE6, 0x6A, 0x00)),
        "P2": ("中危", RGBColor(0xCC, 0xA3, 0x00)),
    }
    return mapping.get(priority, ("中危", RGBColor(0xCC, 0xA3, 0x00)))


def _category_cn(cat_key: str) -> str:
    categories = _load_categories()
    prefix = cat_key.split("-")[0] if "-" in cat_key else cat_key
    cat = categories.get(prefix, {})
    if "-" in cat_key:
        return cat.get("subcategories", {}).get(cat_key, cat_key)
    return cat.get("name", cat_key)


def generate_docx_report(session_data: dict) -> BytesIO:
    """生成 DOCX 格式报告，返回 BytesIO 对象"""
    report = session_data.get("report", {})
    config = session_data.get("config", {})
    target_model = config.get("target_model", config.get("model", "未指定"))

    doc = Document()

    # 设置默认字体
    style = doc.styles['Normal']
    font = style.font
    font.name = '宋体'
    font.size = Pt(10.5)

    # === 标题 ===
    title = doc.add_heading('大语言模型内容安全红队评估报告', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # === 一、整体概述 ===
    doc.add_heading('一、整体概述', level=1)

    total_rounds = report.get("total_rounds", 0)
    total_bypassed = report.get("total_bypassed", 0)
    coverage_rate = report.get("coverage_rate", "0%")

    doc.add_paragraph(
        f'本次测试针对目标模型「{target_model}」进行内容安全红队自动化评估，'
        f'共执行 {total_rounds} 轮测试，覆盖率 {coverage_rate}。'
        f'测试发现 {total_bypassed} 个安全风险点。'
    )

    overview_data = [
        ('测试目标', target_model),
        ('测试时间', datetime.now().strftime('%Y年%m月%d日')),
        ('测试轮次', str(total_rounds)),
        ('覆盖率', coverage_rate),
        ('发现风险点', str(total_bypassed)),
    ]
    table = doc.add_table(rows=len(overview_data), cols=2)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(overview_data):
        table.rows[i].cells[0].text = k
        table.rows[i].cells[1].text = v

    # === 二、测试情况 ===
    doc.add_heading('二、测试情况', level=1)

    # 收集 bypass 样本
    samples = []
    for rd in report.get("rounds", []):
        for d in rd.get("detailedResults", []):
            if d.get("jailbreakStatus") == "bypassed":
                samples.append(d)

    if not samples:
        doc.add_paragraph('本次测试未发现有效绕过，模型防护在测试范围内有效。')
    else:
        # 概述
        doc.add_heading('（一）概述', level=2)
        doc.add_paragraph(f'本次测试共发现 {len(samples)} 个安全风险点。')

        # 每个 bypass 一张表
        for idx, d in enumerate(samples[:20], 1):  # 最多20条
            cat = d.get("category", "未知")
            concepts = d.get("concepts", [d.get("concept", "未知概念")])
            concept_str = "、".join(concepts) if concepts else "未知概念"
            methods = d.get("methods", [d.get("method", "未知方法")])
            method_str = "、".join(methods) if methods else "未知方法"
            severity_text, severity_color = _severity_label(cat)

            doc.add_heading(f'测试结果 {idx}', level=2)

            # 策略描述（脱敏：不暴露原始提示词）
            strategy_desc = f'使用「{method_str}」策略，针对「{concept_str}」概念进行测试'

            # 模型响应摘要（与MD报告一致，只取前50字）
            raw_resp = d.get("modelResponse") or ""
            resp_preview = raw_resp[:50].replace('\n', ' ')
            if len(raw_resp) > 50:
                resp_preview += "……"

            # 修复建议（按priority静态模板）
            fix_suggestions = {
                "P0": "建议立即更新安全策略规则，对该攻击维度实施专项防御。",
                "P1": "建议在下一迭代周期中针对性加固该维度的防护逻辑。",
                "P2": "建议持续监控，纳入后续优化计划。",
            }
            categories = _load_categories()
            prefix = cat.split("-")[0] if "-" in cat else cat
            cat_info = categories.get(prefix, {})
            priority = cat_info.get("priority", "P1")
            fix_text = fix_suggestions.get(priority, fix_suggestions["P1"])

            rows_data = [
                ('漏洞名称', _category_cn(cat)),
                ('漏洞位置', f'目标模型: {target_model}'),
                ('测试过程', strategy_desc),
                ('漏洞详情', f'模型响应摘要: {resp_preview}'),
                ('风险等级', severity_text),
                ('漏洞危害', f'模型在「{_category_cn(cat)}」维度的防护存在缺口，可被利用生成违规内容'),
                ('修复建议', fix_text),
            ]

            tbl = doc.add_table(rows=len(rows_data), cols=2)
            tbl.style = 'Table Grid'
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            for i, (k, v) in enumerate(rows_data):
                tbl.rows[i].cells[0].text = k
                cell = tbl.rows[i].cells[1]
                cell.text = v
                # 风险等级行着色
                if k == '风险等级':
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.color.rgb = severity_color
                            run.font.bold = True

    # === 三、评估结论 ===
    doc.add_heading('三、评估结论与建议', level=1)
    if total_bypassed == 0:
        doc.add_paragraph('本次测试未发现有效绕过，模型内容安全防护表现良好。建议持续监控并定期复测。')
    elif total_bypassed <= 3:
        doc.add_paragraph(f'本次测试发现 {total_bypassed} 个风险点，建议针对性加固相关防护维度。')
    else:
        doc.add_paragraph(f'本次测试发现 {total_bypassed} 个风险点，建议立即启动安全防护加固工作。')

    # === 免责声明 ===
    doc.add_heading('免责声明', level=1)
    doc.add_paragraph(
        '本报告由 PrimeIceAGI 自动化红队测试平台生成，仅供授权安全评估使用。'
        '报告中涉及的攻击方法仅用于评估模型安全防护能力，不构成任何攻击指导。'
    )

    # 保存到 BytesIO
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
