"""Confidence scoring + routing (DECISIONS #7).

Confidence modulates HOW the review is framed (green vs amber) and whether a
string is escalated — but it NEVER removes the single human review.

  TM exact reuse                                  → 1.0  (band: reuse, green)
  new, all ERROR gates pass, no WARN, full cover  → high (0.9, green)
  any WARN                                        → medium (0.6, amber)
  any unresolved ERROR                            → low (0.2, red) → escalate
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine import qa
from app.engine.qa import Flag


@dataclass
class Confidence:
    band: str          # reuse | high | medium | low
    score: float
    badge: str         # 🟢 / 🟡 / 🔴
    color: str         # green | amber | red
    route_to_human: bool   # always True (one review), but low = escalate prominently
    escalate: bool         # low confidence / unresolved error → flag loudly
    summary: str


_BADGE = {"reuse": "🟢", "high": "🟢", "medium": "🟡", "low": "🔴"}
_COLOR = {"reuse": "green", "high": "green", "medium": "amber", "low": "red"}


def score(tm_origin: str, flags: list[Flag]) -> Confidence:
    """tm_origin: 'reused' for a verbatim TM hit, else 'new'."""
    if tm_origin == "reused":
        return Confidence(
            band="reuse", score=1.0, badge=_BADGE["reuse"], color="green",
            route_to_human=True, escalate=False,
            summary="Exact TM match — reused verbatim. Rubber-stamp.",
        )

    if qa.has_errors(flags):
        band = "low"
        summary = "Failed a deterministic QA gate — needs a human fix or reject."
    elif qa.has_warnings(flags):
        band = "medium"
        summary = "Passed all hard gates; some soft flags to check."
    else:
        band = "high"
        summary = "Clean: all gates passed, glossary covered. Rubber-stamp."

    scores = {"high": 0.9, "medium": 0.6, "low": 0.2}
    return Confidence(
        band=band, score=scores[band], badge=_BADGE[band], color=_COLOR[band],
        route_to_human=True, escalate=(band == "low"), summary=summary,
    )
