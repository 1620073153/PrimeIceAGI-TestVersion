from pathlib import Path

from openpyxl import Workbook

from engine.batch_models import BatchEvalResult


RESULT_HEADERS = [
    "用例编号",
    "测试内容",
    "模型回复",
    "类别名称",
    "子类型",
    "来源文件",
    "正则标签",
    "拦截结论",
    "裁判理由",
    "裁判置信度",
    "重试次数",
    "耗时(ms)",
    "需人工复核",
]

SUMMARY_LABELS = {
    "total_cases": "总样本数",
    "processed_cases": "已处理样本数",
    "skipped_cases": "跳过样本数",
    "review_required_cases": "需人工复核数",
}


def export_batch_report(results: list[BatchEvalResult], summary: dict, output_file: str | Path) -> Path:
    workbook = Workbook()

    results_sheet = workbook.active
    results_sheet.title = "results"
    _write_results_sheet(results_sheet, results)

    summary_sheet = workbook.create_sheet("summary")
    _write_summary_sheet(summary_sheet, summary, results)

    review_sheet = workbook.create_sheet("review")
    _write_review_sheet(review_sheet, results)

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path


def _result_row(result: BatchEvalResult) -> list:
    return [
        result.case_id,
        result.prompt_text,
        result.response_text,
        result.category,
        result.subcategory,
        result.source_file,
        ", ".join(result.regex_labels),
        result.intercept_type.value,
        result.judge_reason,
        result.judge_confidence,
        result.retry_count,
        result.latency_ms,
        result.review_required,
    ]


def _write_results_sheet(sheet, results: list[BatchEvalResult]) -> None:
    sheet.append(RESULT_HEADERS)

    for result in results:
        sheet.append(_result_row(result))


def _write_summary_sheet(sheet, summary: dict, results: list[BatchEvalResult]) -> None:
    review_required_cases = summary.get(
        "review_required_cases",
        sum(1 for result in results if result.review_required),
    )

    sheet.append(["指标", "值"])
    sheet.append([SUMMARY_LABELS["total_cases"], summary.get("total_cases", 0)])
    sheet.append([SUMMARY_LABELS["processed_cases"], summary.get("processed_cases", 0)])
    sheet.append([SUMMARY_LABELS["skipped_cases"], summary.get("skipped_cases", 0)])
    sheet.append([SUMMARY_LABELS["review_required_cases"], review_required_cases])

    for intercept_type, count in summary.get("intercept_counts", {}).items():
        sheet.append([f"拦截统计-{intercept_type}", count])


def _write_review_sheet(sheet, results: list[BatchEvalResult]) -> None:
    sheet.append(RESULT_HEADERS)

    for result in results:
        if not result.review_required:
            continue
        sheet.append(_result_row(result))
