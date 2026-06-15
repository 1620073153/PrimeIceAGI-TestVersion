import csv
from pathlib import Path

from openpyxl import load_workbook

from engine.batch_models import BatchEvalCase


_FIELD_ALIASES = {
    "case_id": ("case_id", "id", "样本id", "样本ID", "用例编号"),
    "prompt_text": ("prompt", "prompt_text", "问题", "测试用例", "content", "测试内容"),
    "category": ("category", "类别", "大类", "类别名称"),
    "subcategory": ("subcategory", "子类", "小类", "子类型"),
}
_SUPPORTED_SUFFIXES = {".csv", ".xlsx"}


def _normalize_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _pick(row: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for key in aliases:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _validate_dataset_path(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"数据集文件不存在: {path}")
    if path.is_dir():
        raise ValueError(f"数据集路径不能是目录: {path}")
    if not path.is_file():
        raise ValueError(f"数据集路径不是文件: {path}")
    if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise ValueError(f"当前仅支持 csv/xlsx 数据集: {path.name}")


def _read_csv_rows(path: Path) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [_normalize_value(name) for name in (reader.fieldnames or []) if _normalize_value(name)]
        rows: list[tuple[int, dict[str, str]]] = []
        for index, row in enumerate(reader, start=2):
            normalized_row = {
                _normalize_value(key): _normalize_value(value)
                for key, value in row.items()
                if key is not None and _normalize_value(key)
            }
            if any(normalized_row.values()):
                rows.append((index, normalized_row))
    return headers, rows


def _read_xlsx_rows(path: Path) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        iterator = sheet.iter_rows(values_only=True)
        header_row = next(iterator, None)
        headers = [_normalize_value(value) for value in (header_row or ()) if _normalize_value(value)]
        rows: list[tuple[int, dict[str, str]]] = []
        for index, values in enumerate(iterator, start=2):
            normalized_row: dict[str, str] = {}
            for column_index, header in enumerate(headers):
                value = values[column_index] if column_index < len(values) else None
                normalized_row[header] = _normalize_value(value)
            if any(normalized_row.values()):
                rows.append((index, normalized_row))
        return headers, rows
    finally:
        workbook.close()


def _iter_rows(path: Path) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    if path.suffix.lower() == ".csv":
        return _read_csv_rows(path)
    return _read_xlsx_rows(path)


def _ensure_required_headers(headers: list[str], path: Path) -> None:
    if any(header in _FIELD_ALIASES["prompt_text"] for header in headers):
        return
    raise ValueError(f"数据集缺少必填字段: 测试内容/prompt_text ({path.name})")


def _build_meta(row_number: int, row: dict[str, str]) -> dict[str, str | int | dict[str, str]]:
    meta: dict[str, str | int | dict[str, str]] = {
        "row_number": row_number,
        "raw": dict(row),
    }
    known_columns = {
        alias
        for aliases in _FIELD_ALIASES.values()
        for alias in aliases
    }
    for key, value in row.items():
        if key not in known_columns:
            meta[key] = value
    return meta


def load_batch_cases(dataset_paths: list[str], exclude_categories: list[str] | None = None) -> list[BatchEvalCase]:
    exclude_set = {item.strip() for item in (exclude_categories or []) if item.strip()}
    cases: list[BatchEvalCase] = []

    for dataset_path in dataset_paths:
        path = Path(dataset_path)
        _validate_dataset_path(path)
        headers, rows = _iter_rows(path)
        _ensure_required_headers(headers, path)

        for index, row in rows:
            category = _pick(row, _FIELD_ALIASES["category"])
            if category in exclude_set:
                continue

            prompt_text = _pick(row, _FIELD_ALIASES["prompt_text"])
            if not prompt_text:
                raise ValueError(f"数据集第 {index} 行缺少必填字段: 测试内容/prompt_text ({path.name})")

            case_id = _pick(row, _FIELD_ALIASES["case_id"]) or f"{path.stem}-{index}"
            cases.append(
                BatchEvalCase(
                    case_id=case_id,
                    prompt_text=prompt_text,
                    category=category,
                    subcategory=_pick(row, _FIELD_ALIASES["subcategory"]),
                    source_file=path.name,
                    meta=_build_meta(index, row),
                )
            )

    return cases
