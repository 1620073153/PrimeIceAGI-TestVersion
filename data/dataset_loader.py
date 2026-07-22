from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Sequence

from engine.batch_models import BatchEvalCase

COLUMN_ALIASES: dict[str, list[str]] = {
    "case_id": ["case_id", "id", "用例编号", "编号", "序号"],
    "prompt_text": ["prompt_text", "prompt", "测试内容", "输入", "攻击样本", "text", "content"],
    "category": ["category", "类别", "分类", "category_id", "类别编号"],
    "category_name": ["category_name", "类别名称", "分类名称"],
    "subcategory": ["subcategory", "子类别", "子分类", "subcategory_name", "子类型"],
    "expected_label": ["expected_label", "label", "预期标签", "预期", "expected"],
    "bypass_technique": ["bypass_technique", "绕过技术", "攻击技术", "technique", "绕过手法"],
}


def _resolve_columns(headers: list[str]) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {}
    normalized_headers = [h.strip().lower() for h in headers]
    for canonical, aliases in COLUMN_ALIASES.items():
        found = None
        for alias in aliases:
            if alias.lower() in normalized_headers:
                found = headers[normalized_headers.index(alias.lower())]
                break
        mapping[canonical] = found
    return mapping


def _load_csv(path: Path, default_expected_label: str, exclude_categories: set[str]) -> list[BatchEvalCase]:
    cases: list[BatchEvalCase] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return cases
        col_map = _resolve_columns(list(reader.fieldnames))
        if col_map["prompt_text"] is None:
            raise ValueError(f"CSV 缺少必填列 prompt_text: {path}")

        for row in reader:
            category = row.get(col_map["category"] or "", "").strip() or None
            category_name_val = row.get(col_map["category_name"] or "", "").strip() or None
            if not category and category_name_val:
                category = category_name_val
            if category and category in exclude_categories:
                continue


            case_id = row.get(col_map["case_id"] or "", "").strip()
            if not case_id:
                case_id = uuid.uuid4().hex[:12]

            prompt_text = row.get(col_map["prompt_text"] or "", "").strip()
            if not prompt_text:
                continue

            expected_label = row.get(col_map["expected_label"] or "", "").strip().lower()
            if expected_label not in ("block", "allow"):
                expected_label = default_expected_label

            meta: dict = {}
            bypass_col = col_map.get("bypass_technique")
            if bypass_col and row.get(bypass_col):
                meta["bypass_technique"] = row[bypass_col].strip()

            cases.append(BatchEvalCase(
                case_id=case_id,
                prompt_text=prompt_text,
                category=category,
                category_name=category_name_val,
                subcategory=row.get(col_map["subcategory"] or "", "").strip() or None,
                expected_label=expected_label,
                source_file=str(path),
                meta=meta,
            ))
    return cases


def _load_xlsx(path: Path, default_expected_label: str, exclude_categories: set[str]) -> list[BatchEvalCase]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        return []

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(c).strip() if c else "" for c in rows[0]]
    col_map = _resolve_columns(headers)
    if col_map["prompt_text"] is None:
        raise ValueError(f"XLSX 缺少必填列 prompt_text: {path}")

    header_idx: dict[str, int] = {h: i for i, h in enumerate(headers) if h}
    cases: list[BatchEvalCase] = []

    def get_cell(row: tuple, canonical: str) -> str:
        col_name = col_map.get(canonical)
        if col_name is None or col_name not in header_idx:
            return ""
        val = row[header_idx[col_name]]
        return str(val).strip() if val is not None else ""


    for row in rows[1:]:
        category = get_cell(row, "category") or None
        category_name_val = get_cell(row, "category_name") or None
        if not category and category_name_val:
            category = category_name_val
        if category and category in exclude_categories:
            continue

        prompt_text = get_cell(row, "prompt_text")
        if not prompt_text:
            continue

        case_id = get_cell(row, "case_id") or uuid.uuid4().hex[:12]
        expected_label = get_cell(row, "expected_label").lower()
        if expected_label not in ("block", "allow"):
            expected_label = default_expected_label

        meta: dict = {}
        bypass = get_cell(row, "bypass_technique")
        if bypass:
            meta["bypass_technique"] = bypass

        cases.append(BatchEvalCase(
            case_id=case_id,
            prompt_text=prompt_text,
            category=category,
            category_name=category_name_val,
            subcategory=get_cell(row, "subcategory") or None,
            expected_label=expected_label,
            source_file=str(path),
            meta=meta,
        ))

    wb.close()
    return cases


def load_datasets(
    paths: Sequence[str],
    default_expected_label: str = "block",
    exclude_categories: Sequence[str] | None = None,
) -> list[BatchEvalCase]:
    exclude_set = set(exclude_categories) if exclude_categories else set()
    all_cases: list[BatchEvalCase] = []

    for p in paths:
        path = Path(p)
        if not path.exists():
            raise FileNotFoundError(f"数据集文件不存在: {path}")
        suffix = path.suffix.lower()
        if suffix == ".csv":
            all_cases.extend(_load_csv(path, default_expected_label, exclude_set))
        elif suffix in (".xlsx", ".xls"):
            all_cases.extend(_load_xlsx(path, default_expected_label, exclude_set))
        else:
            raise ValueError(f"不支持的文件格式: {suffix} ({path})")

    return all_cases
