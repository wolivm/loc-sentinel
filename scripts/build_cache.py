#!/usr/bin/env python3
"""Regenerate the demo translation cache from the LIVE model.

Calls the real Anthropic API for every non-TM sample string and overwrites
data/cache/translations.json with genuine model output. Needs ANTHROPIC_API_KEY.

Usage:  python scripts/build_cache.py [--lang de]

This is how the committed cache stays "real": run it with a key and commit the
result. Without a key, the curated seed (scripts/seed.py) keeps the demo working.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings, redact  # noqa: E402
from app.engine import tm, translate  # noqa: E402
from app.engine.sot import available_langs, load_sot  # noqa: E402
from app.sample_data import load_strings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", help="only this language")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.has_anthropic():
        print("✗ ANTHROPIC_API_KEY not set — cannot call the live model.")
        print("  The committed cache (scripts/seed.py) keeps the demo working without a key.")
        return 1
    print(f"Using Anthropic key {redact(settings.anthropic_api_key)}, model {settings.anthropic_model}")

    langs = [args.lang] if args.lang else available_langs()
    strings = load_strings()
    for lang in langs:
        sot = load_sot(lang)
        n = 0
        for s in strings:
            if tm.lookup(s["source_en"], lang):
                continue  # TM hit — never re-translated
            from app.engine.qa import _is_error_string
            out = translate.translate(
                s["source_en"], lang, sot, key=s["key"], context=s["context"],
                is_error_hint=_is_error_string(s["key"], s["context"]),
                prefer_cache=False,  # force live call
            )
            translate.cache_put(s["source_en"], lang, out["target"])
            n += 1
            print(f"  [{lang}] {s['key']:<20} → {out['target']!r}")
        print(f"✓ {lang}: {n} strings translated and cached\n")
    print(f"Cache written to {translate.CACHE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
