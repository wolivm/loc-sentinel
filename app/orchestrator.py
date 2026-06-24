"""Orchestration service — turns an inbound event into a triaged ticket with
reviewed translation units. Surface-agnostic: the webhook, the CLI, and the
playground all call this; Slack posting is injected as a callback so this module
has no UI dependency.
"""

from __future__ import annotations

from collections import Counter

from app.engine.pipeline import StringResult, run_string
from app.engine.sot import load_sot
from app.planner import tickets, triage


def _confidence_summary(results: list[StringResult]) -> str:
    c = Counter(r.confidence_band for r in results)
    parts = []
    for band in ("reuse", "high", "medium", "low"):
        if c.get(band):
            parts.append(f"{c[band]} {band}")
    escal = sum(1 for r in results if r.escalate)
    s = ", ".join(parts) if parts else "0 strings"
    if escal:
        s += f"  ⚠️ {escal} need attention"
    return s


def open_translation_ticket(
    *, strings: list[dict], lang: str, source: str, event_name: str = "string.added",
    requester: str = "", event_id: str | None = None, prefer_cache: bool = True,
    api_key: str | None = None,
) -> dict:
    """Run the hero flow for a batch of source strings in one language.

    `strings`: list of {source_en, key, context, crowdin_string_id?}.
    Returns {ticket, units, results, request_type, auto}.
    """
    rt = triage.classify_event(event_name)

    tid = tickets.create_ticket(
        type=rt.name, source=source, payload={"event": event_name, "lang": lang},
        target_lang=lang, assignee=rt.default_assignee, requester=requester,
    )

    if not triage.is_auto(rt):
        # Non-auto request types loop in a human immediately (requirement #2).
        tickets.transition(tid, "triaged", actor="triage", detail=f"routed to {rt.default_assignee}")
        return {"ticket": tickets.get_ticket(tid), "units": [], "results": [],
                "request_type": rt, "auto": False}

    tickets.transition(tid, "triaged", actor="triage", detail=f"auto: {rt.name}")
    tickets.transition(tid, "in_progress", actor="engine")

    sot = load_sot(lang)
    results: list[StringResult] = []
    for s in strings:
        r = run_string(
            s["source_en"], lang, key=s.get("key", ""), context=s.get("context", ""),
            prefer_cache=prefer_cache, api_key=api_key, sot=sot,
        )
        results.append(r)
        tickets.add_unit(
            ticket_id=tid, source_en=r.source_en, key=r.key, context=r.context,
            crowdin_string_id=str(s.get("crowdin_string_id", "")),
            proposed_target=r.proposed_target, confidence=r.confidence_band,
            confidence_score=r.confidence_score, qa_flags=r.qa_flags,
            tm_origin=r.tm_origin,
            provenance={
                "translation_origin": r.translation_origin,
                "glossary_applied": r.glossary_applied,
                "glossary_missing": r.glossary_missing,
                "tm_alt_targets": r.tm_alt_targets,
                "confidence_summary": r.confidence_summary,
                "confidence_badge": r.confidence_badge,
                "confidence_color": r.confidence_color,
                "escalate": r.escalate,
            },
        )

    summary = _confidence_summary(results)
    tickets.set_confidence_summary(tid, summary)
    tickets.transition(tid, "awaiting_review", actor="engine", detail=summary)

    return {"ticket": tickets.get_ticket(tid), "units": tickets.list_units(tid),
            "results": results, "request_type": rt, "auto": True}


def open_human_ticket(*, text: str, requester: str = "", lang: str = "",
                      source: str = "slack") -> dict:
    """Open a ticket for a free-text /loc request, routed by keyword."""
    rt = triage.classify_text(text)
    tid = tickets.create_ticket(
        type=rt.name, source=source, payload={"text": text}, target_lang=lang,
        assignee=rt.default_assignee, requester=requester,
    )
    tickets.transition(tid, "triaged", actor="triage",
                       detail=f"{rt.name} → {rt.handler} ({rt.default_assignee})")
    return {"ticket": tickets.get_ticket(tid), "request_type": rt}
