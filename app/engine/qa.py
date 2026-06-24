"""Deterministic QA linter — what creates trust (DECISIONS #4, #5).

Every model output passes this BEFORE it can reach Crowdin or Slack. Rules are
code, not model judgement.

  ERROR (must fix or escalate): placeholder set mismatch · "!" in an error string
    · more than one "!" · em dash · ellipsis.
  WARN (surface for the human, never auto-"fix"): single/multi-sentence period
    heuristic · ALL-CAPS / Title Case · glossary "Avoid" term · locked term missing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.engine.normalize import placeholder_diff
from app.engine.sot import SoT

ERROR = "ERROR"
WARN = "WARN"


@dataclass
class Flag:
    severity: str   # ERROR | WARN
    code: str
    message: str


def _is_error_string(key: str, context: str) -> bool:
    """Heuristic: is this an error/failure string? (No '!' allowed if so.)"""
    blob = f"{key} {context}".lower()
    return any(w in blob for w in ("error", "fail", "failure", "couldn't", "could not", "cannot", "can't"))


def _sentence_count(text: str) -> int:
    # Count terminal punctuation groups; treat the string as >=1 sentence.
    parts = [p for p in re.split(r"[.!?¿¡]+", text) if p.strip()]
    return max(1, len(parts))


def _glossary_applied(source_en: str, target: str, sot: SoT):
    """Which locked terms were expected (source term present in EN) and whether
    the target term appears. Returns (applied, missing) lists of GlossaryTerm."""
    applied, missing = [], []
    low_src = source_en.lower()
    low_tgt = target.lower()
    for term in sot.locked:
        if not term.source or not term.target:
            continue
        # Only consider locked terms whose ENGLISH form is in the source string.
        if re.search(rf"(?<!\w){re.escape(term.source.lower())}(?!\w)", low_src):
            if term.target.lower() in low_tgt:
                applied.append(term)
            else:
                missing.append(term)
    return applied, missing


def lint(source_en: str, target: str, sot: SoT, key: str = "", context: str = ""):
    """Run all gates. Returns (flags, info) where info carries glossary provenance."""
    flags: list[Flag] = []
    is_error = _is_error_string(key, context)

    # --- ERROR gates -------------------------------------------------------
    missing_ph, extra_ph = placeholder_diff(source_en, target)
    if missing_ph or extra_ph:
        bits = []
        if missing_ph:
            bits.append("missing " + ", ".join(sorted(set(missing_ph))))
        if extra_ph:
            bits.append("extra " + ", ".join(sorted(set(extra_ph))))
        flags.append(Flag(ERROR, "placeholder_mismatch",
                          "Placeholder set differs from source: " + "; ".join(bits)))

    excl = target.count("!")
    if is_error and excl:
        flags.append(Flag(ERROR, "exclamation_in_error",
                          "Error/failure strings must not contain “!”."))
    elif excl > 1:
        flags.append(Flag(ERROR, "multiple_exclamations",
                          f"At most one “!” allowed; found {excl}."))

    if "—" in target:
        flags.append(Flag(ERROR, "em_dash", "Em dash (—) is not allowed; rephrase or use a hyphen."))
    if "…" in target:
        flags.append(Flag(ERROR, "ellipsis", "Ellipsis (…) is not allowed."))

    # --- WARN gates --------------------------------------------------------
    n_sent = _sentence_count(target)
    stripped = target.rstrip()
    if n_sent == 1 and stripped.endswith("."):
        flags.append(Flag(WARN, "single_sentence_period",
                          "Single standalone sentence should not end with a period."))
    if n_sent > 1 and not re.search(r"[.!?]\s*$", stripped):
        flags.append(Flag(WARN, "multi_sentence_period",
                          "Multi-sentence string: each sentence should end with a period."))

    letters = [c for c in target if c.isalpha()]
    if letters and target.upper() == target:
        flags.append(Flag(WARN, "all_caps", "Target is ALL CAPS; use sentence case."))
    elif sot.lang != "de":
        # Title-Case heuristic (skipped for German, which capitalizes all nouns).
        words = [w for w in re.findall(r"[^\W\d_]+", target) if w]
        if len(words) >= 3 and sum(1 for w in words[1:] if w[:1].isupper()) >= 2:
            flags.append(Flag(WARN, "title_case", "Looks like Title Case; use sentence case."))

    low_tgt = target.lower()
    for term in sot.avoid:
        if term.source and re.search(rf"(?<!\w){re.escape(term.source.lower())}(?!\w)", low_tgt):
            sugg = f" — prefer “{term.target}”" if term.target else ""
            flags.append(Flag(WARN, "avoid_term",
                              f"Avoid-list term “{term.source}” present{sugg}."))

    applied, missing = _glossary_applied(source_en, target, sot)
    for term in missing:
        flags.append(Flag(WARN, "glossary_missing",
                          f"Locked term “{term.source}” → “{term.target}” expected but not found."))

    info = {
        "is_error_string": is_error,
        "glossary_applied": [{"source": t.source, "target": t.target} for t in applied],
        "glossary_missing": [{"source": t.source, "target": t.target} for t in missing],
        "n_sentences": n_sent,
    }
    return flags, info


def has_errors(flags: list[Flag]) -> bool:
    return any(f.severity == ERROR for f in flags)


def has_warnings(flags: list[Flag]) -> bool:
    return any(f.severity == WARN for f in flags)
