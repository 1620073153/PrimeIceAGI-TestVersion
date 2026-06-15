from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InterceptType(str, Enum):
    MODEL_REFUSAL = "model_refusal"
    GUARDRAIL_BLOCK = "guardrail_block"
    NOT_BLOCKED = "not_blocked"
    UNCERTAIN = "uncertain"


@dataclass(slots=True)
class BatchEvalCase:
    case_id: str
    prompt_text: str
    category: str | None = None
    subcategory: str | None = None
    expected_label: str | None = None
    source_file: str | None = None
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BatchEvalConfig:
    dataset_paths: list[str]
    exclude_categories: list[str]
    workers: int
    repeat: int
    sleep_seconds: float
    retries: int
    resume_from_progress: bool
    output_dir: str
    output_file: str
    enable_llm_judge: bool = True


@dataclass(slots=True)
class BatchEvalResult:
    case_id: str
    prompt_text: str
    response_text: str
    category: str | None
    subcategory: str | None
    source_file: str | None
    regex_labels: list[str]
    intercept_type: InterceptType
    judge_reason: str
    judge_confidence: float | None
    success: bool
    retry_count: int
    latency_ms: int | None
    raw_error: str | None = None
    review_required: bool = False
