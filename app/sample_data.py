"""Loader for the fictional Nimbus sample strings (data/sample_strings)."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import SAMPLE_DIR

DEFAULT_FILE = SAMPLE_DIR / "nimbus_en.json"


def load_strings(path: Path | None = None) -> list[dict]:
    """Return [{source_en, key, context, crowdin_string_id}] from a sample file."""
    data = json.loads((path or DEFAULT_FILE).read_text(encoding="utf-8"))
    out = []
    for s in data.get("strings", []):
        out.append({
            "source_en": s["text"],
            "key": s.get("key", ""),
            "context": s.get("context", ""),
            "crowdin_string_id": s.get("id", ""),
        })
    return out
