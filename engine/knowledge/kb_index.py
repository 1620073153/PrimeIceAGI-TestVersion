from dataclasses import dataclass
from pathlib import Path

from .category_index import CategoryIndex
from .kb_loader import load_json
from .success_pattern_index import SuccessPatternIndex
from .template_index import TemplateIndex


@dataclass(slots=True)
class RuntimeIndexes:
    category_index: CategoryIndex
    template_index: TemplateIndex
    success_pattern_index: SuccessPatternIndex


def build_runtime_indexes(kb_root: str = "F:/PrimeIceAGI/kb_data") -> RuntimeIndexes:
    root = Path(kb_root)
    kb1 = load_json(root / "kb1.json")
    kb4 = load_json(root / "kb4.json")
    success_patterns = load_json(root / "derived" / "success_pattern_map.json")

    category_index = CategoryIndex(kb1)
    return RuntimeIndexes(
        category_index=category_index,
        template_index=TemplateIndex(kb4),
        success_pattern_index=SuccessPatternIndex(success_patterns),
    )
