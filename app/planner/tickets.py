"""Ticket + TranslationUnit store with a small state machine and audit log.

State machine (§6):
  new → triaged → in_progress → awaiting_review → approved | rejected → done

Every transition is logged to audit_log — the "human in the loop" + self-awareness
narrative (and a great demo prop). Concurrent-approval guard lives here too:
a unit already `approved` ignores a second approve (LIMITATIONS: races).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from app.planner.db import get_conn

# Allowed ticket transitions. Kept permissive enough for reopen/close paths.
TRANSITIONS = {
    "new": {"triaged"},
    "triaged": {"in_progress", "rejected"},
    "in_progress": {"awaiting_review", "rejected", "done"},
    "awaiting_review": {"approved", "rejected"},
    "approved": {"done"},
    "rejected": {"in_progress", "done"},
    "done": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_audit(entity: str, from_state: str | None, to_state: str | None,
              actor: str, detail: str = "") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log(entity, from_state, to_state, actor, detail, at) VALUES (?,?,?,?,?,?)",
        (entity, from_state, to_state, actor, detail, _now()),
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #
def create_ticket(*, type: str, source: str, payload: dict | None = None,
                  target_lang: str = "", assignee: str = "", requester: str = "",
                  actor: str = "system") -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO tickets(type, status, source, payload, target_lang, assignee,
                               requester, confidence_summary, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (type, "new", source, json.dumps(payload or {}), target_lang, assignee,
         requester, "", _now()),
    )
    conn.commit()
    tid = cur.lastrowid
    log_audit(f"ticket:T{tid}", None, "new", actor, f"type={type} source={source}")
    return tid


def transition(ticket_id: int, to_state: str, actor: str, detail: str = "") -> str:
    conn = get_conn()
    row = conn.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if row is None:
        raise ValueError(f"ticket T{ticket_id} not found")
    cur_state = row["status"]
    if to_state == cur_state:
        return cur_state  # idempotent no-op
    if to_state not in TRANSITIONS.get(cur_state, set()):
        raise ValueError(f"illegal transition T{ticket_id}: {cur_state} → {to_state}")
    conn.execute("UPDATE tickets SET status=? WHERE id=?", (to_state, ticket_id))
    conn.commit()
    log_audit(f"ticket:T{ticket_id}", cur_state, to_state, actor, detail)
    return to_state


def set_assignee(ticket_id: int, assignee: str, actor: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE tickets SET assignee=? WHERE id=?", (assignee, ticket_id))
    conn.commit()
    log_audit(f"ticket:T{ticket_id}", None, None, actor, f"assignee={assignee}")


def set_confidence_summary(ticket_id: int, summary: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE tickets SET confidence_summary=? WHERE id=?", (summary, ticket_id))
    conn.commit()


def get_ticket(ticket_id: int) -> dict | None:
    row = get_conn().execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def list_tickets(status: str | None = None, lang: str | None = None,
                 assignee: str | None = None, open_only: bool = False) -> list[dict]:
    q = "SELECT * FROM tickets WHERE 1=1"
    args: list = []
    if status:
        q += " AND status=?"; args.append(status)
    if lang:
        q += " AND target_lang=?"; args.append(lang)
    if assignee:
        q += " AND assignee=?"; args.append(assignee)
    if open_only:
        q += " AND status NOT IN ('done')"
    q += " ORDER BY id DESC"
    return [dict(r) for r in get_conn().execute(q, args).fetchall()]


# --------------------------------------------------------------------------- #
# Translation units
# --------------------------------------------------------------------------- #
def add_unit(*, ticket_id: int, source_en: str, key: str = "", context: str = "",
             crowdin_string_id: str = "", proposed_target: str = "",
             confidence: str = "", confidence_score: float = 0.0,
             qa_flags: list | None = None, tm_origin: str = "",
             provenance: dict | None = None, status: str = "proposed") -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO units(ticket_id, crowdin_string_id, key, source_en, context,
                             proposed_target, final_target, status, confidence,
                             confidence_score, qa_flags, tm_origin, provenance)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ticket_id, crowdin_string_id, key, source_en, context, proposed_target, "",
         status, confidence, confidence_score, json.dumps(qa_flags or []),
         tm_origin, json.dumps(provenance or {})),
    )
    conn.commit()
    return cur.lastrowid


def get_unit(unit_id: int) -> dict | None:
    row = get_conn().execute("SELECT * FROM units WHERE id=?", (unit_id,)).fetchone()
    return _hydrate_unit(row) if row else None


def list_units(ticket_id: int) -> list[dict]:
    rows = get_conn().execute("SELECT * FROM units WHERE ticket_id=? ORDER BY id", (ticket_id,)).fetchall()
    return [_hydrate_unit(r) for r in rows]


def _hydrate_unit(row) -> dict:
    d = dict(row)
    d["qa_flags"] = json.loads(d.get("qa_flags") or "[]")
    d["provenance"] = json.loads(d.get("provenance") or "{}")
    return d


def resolve_unit(unit_id: int, *, status: str, final_target: str, actor: str,
                 detail: str = "") -> dict:
    """Approve / edit / reject a unit. Idempotent: a unit already in a terminal
    state ignores a second resolution (concurrent-approval guard)."""
    conn = get_conn()
    row = conn.execute("SELECT status FROM units WHERE id=?", (unit_id,)).fetchone()
    if row is None:
        raise ValueError(f"unit U{unit_id} not found")
    prev = row["status"]
    if prev in ("approved", "edited", "rejected"):
        return {"changed": False, "status": prev, "note": "already resolved"}
    conn.execute("UPDATE units SET status=?, final_target=? WHERE id=?",
                 (status, final_target, unit_id))
    conn.commit()
    log_audit(f"unit:U{unit_id}", prev, status, actor, detail)
    return {"changed": True, "status": status}


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def audit_for(entity_prefix: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM audit_log WHERE entity LIKE ? ORDER BY id", (entity_prefix + "%",)
    ).fetchall()
    return [dict(r) for r in rows]


def recent_audit(limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Idempotency for webhooks
# --------------------------------------------------------------------------- #
def already_processed(event_id: str) -> bool:
    return get_conn().execute(
        "SELECT 1 FROM processed_events WHERE event_id=?", (event_id,)
    ).fetchone() is not None


def already_proposed(crowdin_string_id, lang: str, source_en: str) -> bool:
    """True if this exact (Crowdin string, language, source text) already has a
    unit — so repeated webhook deliveries for one sync don't create duplicate
    cards. A CHANGED source (string.updated) has different source_en → re-processed."""
    if not crowdin_string_id:
        return False
    return get_conn().execute(
        """SELECT 1 FROM units u JOIN tickets t ON u.ticket_id = t.id
           WHERE u.crowdin_string_id = ? AND t.target_lang = ? AND u.source_en = ? LIMIT 1""",
        (str(crowdin_string_id), lang, source_en),
    ).fetchone() is not None


def mark_processed(event_id: str) -> None:
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO processed_events(event_id, at) VALUES (?,?)",
                 (event_id, _now()))
    conn.commit()


def hold_from_webhook(crowdin_string_ids: list) -> None:
    """Tell the auto-webhook to ignore these Crowdin string ids (demo strings)."""
    conn = get_conn()
    conn.executemany("INSERT OR IGNORE INTO webhook_skip(crowdin_string_id, at) VALUES (?,?)",
                     [(str(i), _now()) for i in crowdin_string_ids if i])
    conn.commit()


def is_webhook_held(crowdin_string_id) -> bool:
    if not crowdin_string_id:
        return False
    return get_conn().execute(
        "SELECT 1 FROM webhook_skip WHERE crowdin_string_id=?", (str(crowdin_string_id),)
    ).fetchone() is not None


def release_webhook_hold(crowdin_string_ids: list) -> None:
    conn = get_conn()
    conn.executemany("DELETE FROM webhook_skip WHERE crowdin_string_id=?",
                     [(str(i),) for i in crowdin_string_ids if i])
    conn.commit()
