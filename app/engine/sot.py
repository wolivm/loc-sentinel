"""Source of Truth loader.

A market is a DATA FOLDER under data/sot/<lang>/:
  guidelines.md  – prose rules (loaded verbatim into the grounding prefix)
  glossary.csv   – locked term map + Avoid list
  market.yaml    – machine-readable conventions (formality, number format, ...)
  TM_<lang>.csv  – translation memory (handled by tm.py)

Adding a market = adding a folder. No engine code changes. (DECISIONS #2.)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import SOT_DIR


@dataclass
class GlossaryTerm:
    source: str
    target: str
    note: str = ""


@dataclass
class SoT:
    lang: str
    market_name: str
    formality: str
    formality_pronoun: str
    conventions: dict
    guidelines_md: str
    locked: list[GlossaryTerm] = field(default_factory=list)
    avoid: list[GlossaryTerm] = field(default_factory=list)  # source=word to avoid, target=preferred
    flag: str = ""

    def system_prefix(self) -> str:
        """The stable, cacheable grounding text sent as the system prompt prefix.

        Stable per language → a good prompt-cache prefix (DECISIONS #6). The
        universal engine rules live here too so the model is told them, but they
        are ALSO enforced deterministically by qa.py — prompt + verify."""
        locked_tbl = "\n".join(
            f"  - {t.source}  →  {t.target}" + (f"   ({t.note})" if t.note else "")
            for t in self.locked
        ) or "  (none)"
        avoid_tbl = "\n".join(
            f"  - avoid “{t.source}”" + (f", prefer “{t.target}”" if t.target else "")
            for t in self.avoid
        ) or "  (none)"
        c = self.conventions
        return f"""You are the localization engine for Nimbus, a notes & habit app. You translate
short product UI strings from English into {self.market_name}. You are precise and literal:
you translate exactly what is given, you do not add, embellish, or explain.

# Market: {self.market_name} ({self.lang})
- Register / formality: {self.formality.upper()} — address the user as “{self.formality_pronoun}”.
- Casing: sentence case (NOT Title Case). Capitalize per this language's orthography.
- Decimal separator “{c.get('decimal_separator', '.')}”, thousands separator “{c.get('thousands_separator', ',')}”.
- Quotation marks: {c.get('quotes_open', '"')} … {c.get('quotes_close', '"')}.
- Inverted punctuation (¿ ¡): {"REQUIRED for questions/exclamations" if c.get('inverted_punctuation') else "not used"}.

# Universal punctuation rules (apply to the TARGET, do not mirror English)
- A single standalone sentence takes NO terminal period. Multi-sentence strings get a period on each sentence.
- At most one “!” in a string. NEVER use “!” in an error/failure string.
- No em dash (—) and no ellipsis (…). Rephrase instead.

# Placeholders & markup — preserve VERBATIM
Keep every placeholder/markup token exactly: %@, %lld, %1$@, %d, %s, {{name}}, {{count}}, <tag>, \\n, emojis.
Same token, same count, same spacing. Never translate, reorder, or invent placeholders.

# Locked glossary terms — use the target EXACTLY
{locked_tbl}

# Avoid list — do not use these in the target
{avoid_tbl}

# Content guidelines (authoritative)
{self.guidelines_md}
""".strip()


def _read_glossary(path: Path) -> tuple[list[GlossaryTerm], list[GlossaryTerm]]:
    locked, avoid = [], []
    if not path.exists():
        return locked, avoid
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            term = GlossaryTerm(
                source=(row.get("source") or "").strip(),
                target=(row.get("target") or "").strip(),
                note=(row.get("note") or "").strip(),
            )
            kind = (row.get("kind") or "").strip().lower()
            if kind == "avoid":
                avoid.append(term)
            elif kind == "locked":
                locked.append(term)
    return locked, avoid


@lru_cache
def load_sot(lang: str) -> SoT:
    base = SOT_DIR / lang
    if not base.exists():
        raise FileNotFoundError(
            f"No Source-of-Truth folder for '{lang}' at {base}. "
            f"Adding a market = create data/sot/{lang}/ with guidelines.md, glossary.csv, market.yaml."
        )
    market = yaml.safe_load((base / "market.yaml").read_text(encoding="utf-8"))
    guidelines = (base / "guidelines.md").read_text(encoding="utf-8")
    locked, avoid = _read_glossary(base / "glossary.csv")
    return SoT(
        lang=lang,
        market_name=market.get("name", lang),
        formality=market.get("formality", "neutral"),
        formality_pronoun=market.get("formality_pronoun", ""),
        conventions=market,
        guidelines_md=guidelines,
        locked=locked,
        avoid=avoid,
        flag=market.get("flag", ""),
    )


def available_langs() -> list[str]:
    if not SOT_DIR.exists():
        return []
    return sorted(p.name for p in SOT_DIR.iterdir() if p.is_dir() and (p / "market.yaml").exists())
