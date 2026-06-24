#!/usr/bin/env python3
"""Seed the demo: init the DB and build the offline translation cache.

The cache is built from data/cache/_curated.json through the engine's own
normalization (translate.cache_put), so cache keys always match what the
pipeline looks up at runtime — the demo works with NO Anthropic key.

Usage:  python scripts/seed.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CACHE_DIR, get_settings  # noqa: E402
from app.engine import translate  # noqa: E402
from app.engine.sot import available_langs  # noqa: E402
from app.planner.db import init_db  # noqa: E402
from app.sample_data import load_strings  # noqa: E402

CURATED = CACHE_DIR / "_curated.json"


def main() -> None:
    init_db()
    print("✓ SQLite initialised")

    langs = available_langs()
    print(f"✓ Source-of-Truth folders: {', '.join(langs)}")

    strings = load_strings()
    by_key = {s["key"]: s["source_en"] for s in strings}
    print(f"✓ Sample strings: {len(strings)}")

    curated = json.loads(CURATED.read_text(encoding="utf-8"))["translations"]
    settings = get_settings()
    count = 0
    for key, per_lang in curated.items():
        source_en = by_key.get(key)
        if not source_en:
            print(f"  ! curated key '{key}' has no matching sample string — skipping")
            continue
        for lang, target in per_lang.items():
            if lang not in langs:
                continue
            translate.cache_put(source_en, lang, target)
            count += 1
    print(f"✓ Demo translation cache built: {count} entries → {translate.CACHE_FILE}")
    print("\nDemo mode is ready (no API key needed). Try:")
    print("  ./run cli data/sample_strings/nimbus_en.json")
    print("  ./run web")


if __name__ == "__main__":
    main()
