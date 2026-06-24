"""Loc Sentinel CLI — run the engine over a sample strings file.

  python -m app.cli data/sample_strings/nimbus_en.json [--lang de] [--no-cache]

Prints, per string: TM origin, proposed target, confidence badge, QA flags, and
glossary/TM provenance. This is the "solid, tested core" before any live
integration (Day 1) and a great offline demo fallback.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from app.config import get_settings
from app.engine.pipeline import run_string
from app.engine.sot import available_langs, load_sot
from app.sample_data import DEFAULT_FILE, load_strings

# ANSI colors
G, Y, R, DIM, B, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
COLORMAP = {"green": G, "amber": Y, "red": R}


def _print_result(r, idx: int) -> None:
    c = COLORMAP.get(r.confidence_color, "")
    origin = "TM reuse" if r.tm_origin == "reused" else f"new · {r.translation_origin}"
    print(f"\n{B}[{idx}] {r.key}{RESET}  {DIM}({origin}){RESET}")
    print(f"    EN  {r.source_en!r}")
    print(f"    →   {c}{r.proposed_target!r}{RESET}")
    print(f"    {r.confidence_badge} {c}{r.confidence_band.upper()}{RESET} "
          f"({r.confidence_score:.2f})  {DIM}{r.confidence_summary}{RESET}")
    if r.qa_flags:
        for f in r.qa_flags:
            tag = f"{R}ERROR{RESET}" if f["severity"] == "ERROR" else f"{Y}WARN{RESET}"
            print(f"      • {tag} [{f['code']}] {f['message']}")
    else:
        print(f"      {G}• all QA gates passed{RESET}")
    if r.glossary_applied:
        terms = ", ".join(f"{t['source']}→{t['target']}" for t in r.glossary_applied)
        print(f"      {DIM}glossary: {terms}{RESET}")
    if r.tm_alt_targets:
        print(f"      {DIM}TM conflict alts: {', '.join(r.tm_alt_targets)}{RESET}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the Loc Sentinel engine over a sample file.")
    ap.add_argument("file", nargs="?", default=str(DEFAULT_FILE), help="sample strings JSON")
    ap.add_argument("--lang", help="target language (default: all configured TARGET_LANGS)")
    ap.add_argument("--no-cache", action="store_true",
                    help="bypass the demo cache and call the live model (needs ANTHROPIC_API_KEY)")
    args = ap.parse_args(argv)

    from pathlib import Path
    strings = load_strings(Path(args.file))
    settings = get_settings()
    langs = [args.lang] if args.lang else settings.langs
    langs = [l for l in langs if l in available_langs()] or available_langs()

    for lang in langs:
        sot = load_sot(lang)
        print(f"\n{B}══════ {sot.flag} {sot.market_name} ({lang}) — {len(strings)} strings ══════{RESET}")
        bands: Counter = Counter()
        for i, s in enumerate(strings, 1):
            r = run_string(s["source_en"], lang, key=s["key"], context=s["context"],
                           prefer_cache=not args.no_cache, sot=sot)
            bands[r.confidence_band] += 1
            _print_result(r, i)
        total = sum(bands.values())
        auto = bands["reuse"] + bands["high"]
        print(f"\n{B}Summary {lang}:{RESET} "
              f"{G}{bands['reuse']} reuse{RESET}, {G}{bands['high']} high{RESET}, "
              f"{Y}{bands['medium']} medium{RESET}, {R}{bands['low']} low{RESET}  "
              f"→ {auto}/{total} ({auto/total*100:.0f}%) rubber-stampable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
