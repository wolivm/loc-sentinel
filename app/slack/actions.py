"""Resolution logic for Approve / Edit / Reject — the single human touchpoint's
side effects. Slack-independent so it can be unit-tested and reused.

  Approve → Crowdin approve + append pair to TM + close
  Edit    → Crowdin approve edited text + append EDITED pair to TM (system learns)
  Reject  → capture reason + route to a human assignee (reopen)
"""

from __future__ import annotations

import logging
from datetime import date

from app.crowdin.client import get_client
from app.engine import tm
from app.engine.sot import load_sot
from app.planner import tickets

log = logging.getLogger("slack.actions")


def _crowdin_writeback(unit: dict, ticket: dict, text: str) -> str:
    """Approve `text` in Crowdin (= ready for production). Demo-safe."""
    client = get_client()
    if client is None:
        return "crowdin not configured (skipped)"
    sid = unit.get("crowdin_string_id")
    if not sid:
        return ""  # demo / non-Crowdin string — nothing to write back
    locale = load_sot(ticket["target_lang"]).conventions.get("crowdin_locale", ticket["target_lang"])
    try:
        client.approve_text(int(sid), locale, text)
        return "approved in Crowdin"
    except Exception as e:  # noqa: BLE001
        log.warning("Crowdin approve failed: %s", e)
        return f"crowdin error: {e}"


def _maybe_close_ticket(ticket_id: int, actor: str) -> None:
    units = tickets.list_units(ticket_id)
    if any(u["status"] == "proposed" for u in units):
        return  # still pending reviews
    if all(u["status"] in ("approved", "edited") for u in units):
        try:
            tickets.transition(ticket_id, "approved", actor=actor, detail="all units approved")
            tickets.transition(ticket_id, "done", actor=actor)
        except ValueError:
            pass
    else:
        try:
            tickets.transition(ticket_id, "rejected", actor=actor, detail="some units rejected → human")
        except ValueError:
            pass


def finalize_unit(unit_id: int, *, status: str, final_target: str, actor: str,
                  reason: str = "") -> dict:
    """Apply a human decision to a unit. Returns {unit, resolved, crowdin, tm}."""
    unit = tickets.get_unit(unit_id)
    if unit is None:
        raise ValueError(f"unit U{unit_id} not found")
    ticket = tickets.get_ticket(unit["ticket_id"])

    res = tickets.resolve_unit(unit_id, status=status, final_target=final_target,
                               actor=actor, detail=reason)
    if not res["changed"]:
        unit = tickets.get_unit(unit_id)
        return {"unit": unit, "ticket": ticket,
                "resolved": {"status": unit["status"], "actor": actor, "note": "already resolved"},
                "crowdin": "", "tm": ""}

    crowdin_note, tm_note = "", ""
    if status in ("approved", "edited"):
        crowdin_note = _crowdin_writeback(unit, ticket, final_target)
        # The system LEARNS: append the approved/edited pair to the TM.
        action = tm.append(unit["source_en"], final_target, ticket["target_lang"],
                           date.today().isoformat())
        tm_note = f"TM {action}"
    elif status == "rejected":
        tickets.set_assignee(ticket["id"], ticket.get("assignee") or "@loc-lead", actor)
        tm_note = "routed to human"

    _maybe_close_ticket(ticket["id"], actor)

    unit = tickets.get_unit(unit_id)
    note = ", ".join(p for p in (crowdin_note, tm_note, reason) if p)
    return {"unit": unit, "ticket": tickets.get_ticket(ticket["id"]),
            "resolved": {"status": status, "actor": actor, "note": note},
            "crowdin": crowdin_note, "tm": tm_note}
