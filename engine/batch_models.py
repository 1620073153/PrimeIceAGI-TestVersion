from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InterceptType(Enum):
    MODEL_REFUSAL = "model_refusal"
    GUARDRAIL_BLOCK = "guardrail_block"
    NOT_BLOCKED = "not_blocked"
    UNCERTAIN = "uncertain"


@dataclass
class GuardrailSignature:
    type: str  # "json_field" | "text_contains" | "regex"
    pattern: str


@dataclass
class BatchEvalConfig:
    mode: str  # "guardrail" | "model_only"
    guardrail_signatures: list[GuardrailSignature] = field(default_factory=list)
    black_dataset_paths: list[str] = field(default_factory=list)
    white_dataset_paths: list[str] = field(default_factory=list)
    workers: int = 4
    repeat: int = 1
    retries: int = 3
    sleep_seconds: float = 1.0
    resume_from_progress: bool = False
    enable_llm_judge: bool = True
    output_file: str = "batch_report.xlsx"

    target_api_base: str = ""
    target_api_key: str = ""
    target_model: str = ""

    judge_api_base: str = ""
    judge_api_key: str = ""
    judge_model: str = ""


@dataclass
class BatchEvalCase:
    case_id: str
    prompt_text: str
    category: str | None = None
    category_name: str | None = None
    subcategory: str | None = None
    expected_label: str = "block"  # "block" | "allow"
    source_file: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchEvalResult:
    case_id: str
    prompt_text: str
    response_text: str
    intercept_type: InterceptType
    confidence: float
    reason: str
    review_required: bool
    expected_label: str
    is_correct: bool
    category: str | None = None
    category_name: str | None = None
    elapsed_ms: int = 0
    error: str | None = None
    repeat_index: int = 1
    subcategory: str | None = None
    bypass_technique: str | None = None
