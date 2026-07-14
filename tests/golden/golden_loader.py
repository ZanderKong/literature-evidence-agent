"""Golden set loader — loads annotations from golden_set.json."""

import json
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).resolve().parent


def load_golden() -> list[dict[str, Any]]:
    path = GOLDEN_DIR / "golden_set.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Golden set not found: {path}")
