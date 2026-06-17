import json
from pathlib import Path


def load_json(path: str | Path) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))
