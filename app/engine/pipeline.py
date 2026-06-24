"""The per-string engine pipeline (§5 of the brief), in order:

  a. SoT      load the market's guidelines + glossary
  b. TM-first exact match → reuse verbatim (confidence 1.0, no model call)
  c. translate the miss, grounded + cached SoT prefix
  d. QA lint  deterministic ERROR/WARN gates
  e. score    confidence + routing
  f. (write-back happens on human approval, in the planner)

This module is STATELESS and the single source of truth for "translate one
string." CLI, webhook orchestrator, and the web playground all call run_string().
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.engine import confidence, qa, tm, translate
from app.engine.sot import SoT, load_sot


@dataclass
class StringResult:
    source_en: str
    lang: str
    key: str
    context: str
    proposed_target: str
    tm_origin: str               # reused | new
    translation_origin: str      # tm | cache | model
    confidence_band: str
    confidence_score: float
    confidence_badge: str
    confidence_color: str
    confidence_summary: str
    route_to_human: bool
    escalate: bool
    qa_flags: list = field(default_factory=list)        # [{severity, code, message}]
    glossary_applied: list = field(default_factory=list)
    glossary_missing: list = field(default_factory=list)
    tm_alt_targets: list = field(default_factory=list)
    available: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def run_string(source_en: str, lang: str, *, key: str = "", context: str = "",
               prefer_cache: bool = True, api_key: str | None = None,
               sot: SoT | None = None) -> StringResult:
    sot = sot or load_sot(lang)

    # (b) TM-first — exact match reused verbatim, no model call, confidence 1.0
    hit = tm.lookup(source_en, lang)
    if hit:
        flags, info = qa.lint(source_en, hit.target, sot, key=key, context=context)
        conf = confidence.score("reused", flags)
        return StringResult(
            source_en=source_en, lang=lang, key=key, context=context,
            proposed_target=hit.target, tm_origin="reused", translation_origin="tm",
            confidence_band=conf.band, confidence_score=conf.score,
            confidence_badge=conf.badge, confidence_color=conf.color,
            confidence_summary=conf.summary, route_to_human=conf.route_to_human,
            escalate=conf.escalate,
            qa_flags=[vars(f) for f in flags],
            glossary_applied=info["glossary_applied"], glossary_missing=info["glossary_missing"],
            tm_alt_targets=hit.alt_targets,
        )

    # (c) translate the miss, grounded
    is_error_hint = qa._is_error_string(key, context)
    try:
        out = translate.translate(
            source_en, lang, sot, key=key, context=context,
            is_error_hint=is_error_hint, prefer_cache=prefer_cache, api_key=api_key,
        )
    except translate.TranslationUnavailable as e:
        return StringResult(
            source_en=source_en, lang=lang, key=key, context=context,
            proposed_target="", tm_origin="new", translation_origin="unavailable",
            confidence_band="low", confidence_score=0.0, confidence_badge="🔴",
            confidence_color="red", confidence_summary=str(e),
            route_to_human=True, escalate=True, available=False, error=str(e),
        )

    # (d) QA lint  +  (e) confidence
    flags, info = qa.lint(source_en, out["target"], sot, key=key, context=context)
    conf = confidence.score("new", flags)
    return StringResult(
        source_en=source_en, lang=lang, key=key, context=context,
        proposed_target=out["target"], tm_origin="new", translation_origin=out["origin"],
        confidence_band=conf.band, confidence_score=conf.score,
        confidence_badge=conf.badge, confidence_color=conf.color,
        confidence_summary=conf.summary, route_to_human=conf.route_to_human,
        escalate=conf.escalate,
        qa_flags=[vars(f) for f in flags],
        glossary_applied=info["glossary_applied"], glossary_missing=info["glossary_missing"],
    )
