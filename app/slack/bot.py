"""Slack Bolt app (Socket Mode) — interactivity needs no public URL.

Review-card actions (Approve / Edit / Reject) + slash commands for stakeholders:
  /loc request <text>   open a localization request (auto-triaged)
  /loc status [Tn]      status of a ticket / your requests
  /loc queue [lang]     open tickets by language / assignee (capacity view)

Run:  python -m app.slack.bot   (or ./run slack)
"""

from __future__ import annotations

import json
import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import get_settings
from app.planner import tickets
from app.planner.db import init_db
from app.slack.actions import finalize_unit
from app.slack.cards import build_review_blocks

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("slack.bot")

_settings = get_settings()
# Placeholder token lets this module import without Slack configured (handlers
# still register); main() refuses to actually start unless has_slack() is true.
app = App(
    token=_settings.slack_bot_token or "xoxb-not-configured",
    signing_secret=_settings.slack_signing_secret or None,
    token_verification_enabled=False,
)


def _actor(body: dict) -> str:
    u = body.get("user", {})
    return "@" + (u.get("username") or u.get("name") or u.get("id", "user"))


def _update_card(client, channel: str, ts: str, ticket: dict, unit: dict, resolved: dict) -> None:
    client.chat_update(
        channel=channel, ts=ts,
        text=f"{resolved['status']} {unit['key']}",
        blocks=build_review_blocks(ticket, unit, resolved=resolved),
    )


# --------------------------------------------------------------------------- #
# Approve
# --------------------------------------------------------------------------- #
@app.action("loc_approve")
def on_approve(ack, body, client):
    ack()
    v = json.loads(body["actions"][0]["value"])
    unit = tickets.get_unit(v["u"])
    out = finalize_unit(v["u"], status="approved",
                        final_target=unit["proposed_target"], actor=_actor(body))
    _update_card(client, body["channel"]["id"], body["message"]["ts"],
                 out["ticket"], out["unit"], out["resolved"])


# --------------------------------------------------------------------------- #
# Edit (modal → save edited → learn)
# --------------------------------------------------------------------------- #
@app.action("loc_edit")
def on_edit(ack, body, client):
    ack()
    v = json.loads(body["actions"][0]["value"])
    unit = tickets.get_unit(v["u"])
    meta = json.dumps({"u": v["u"], "t": v["t"],
                       "channel": body["channel"]["id"], "ts": body["message"]["ts"]})
    client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "loc_edit_submit", "private_metadata": meta,
        "title": {"type": "plain_text", "text": "Edit translation"},
        "submit": {"type": "plain_text", "text": "Save & approve"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*EN*  `{unit['source_en']}`"}},
            {"type": "input", "block_id": "tgt", "label": {"type": "plain_text", "text": "Target"},
             "element": {"type": "plain_text_input", "action_id": "val", "multiline": True,
                         "initial_value": unit["proposed_target"]}},
        ],
    })


@app.view("loc_edit_submit")
def on_edit_submit(ack, body, client, view):
    ack()
    meta = json.loads(view["private_metadata"])
    new_text = view["state"]["values"]["tgt"]["val"]["value"].strip()
    out = finalize_unit(meta["u"], status="edited", final_target=new_text, actor=_actor(body))
    _update_card(client, meta["channel"], meta["ts"], out["ticket"], out["unit"], out["resolved"])


# --------------------------------------------------------------------------- #
# Reject (modal → reason → route to human)
# --------------------------------------------------------------------------- #
@app.action("loc_reject")
def on_reject(ack, body, client):
    ack()
    v = json.loads(body["actions"][0]["value"])
    meta = json.dumps({"u": v["u"], "t": v["t"],
                       "channel": body["channel"]["id"], "ts": body["message"]["ts"]})
    client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "loc_reject_submit", "private_metadata": meta,
        "title": {"type": "plain_text", "text": "Reject translation"},
        "submit": {"type": "plain_text", "text": "Reject & route"},
        "blocks": [
            {"type": "input", "block_id": "reason", "label": {"type": "plain_text", "text": "Reason"},
             "element": {"type": "plain_text_input", "action_id": "val", "multiline": True}},
        ],
    })


@app.view("loc_reject_submit")
def on_reject_submit(ack, body, client, view):
    ack()
    meta = json.loads(view["private_metadata"])
    reason = view["state"]["values"]["reason"]["val"]["value"].strip()
    unit = tickets.get_unit(meta["u"])
    out = finalize_unit(meta["u"], status="rejected",
                        final_target=unit["proposed_target"], actor=_actor(body), reason=reason)
    _update_card(client, meta["channel"], meta["ts"], out["ticket"], out["unit"], out["resolved"])


# --------------------------------------------------------------------------- #
# Slash command: /loc request | status | queue
# --------------------------------------------------------------------------- #
@app.command("/loc")
def on_loc(ack, respond, command):
    ack()
    text = (command.get("text") or "").strip()
    sub, _, rest = text.partition(" ")
    sub = sub.lower()
    user = "@" + (command.get("user_name") or command.get("user_id", "user"))

    if sub == "request":
        from app.orchestrator import open_human_ticket
        out = open_human_ticket(text=rest, requester=user, source="slack")
        rt = out["request_type"]
        t = out["ticket"]
        handled = "🤖 auto-handled by the engine" if rt.handler == "auto" \
            else f"👤 routed to *{rt.default_assignee}* (SLA {rt.sla_hours}h)"
        respond(f"📝 Opened *T{t['id']}* · _{rt.name}_ · {handled}\n> {rest}")
    elif sub == "status":
        respond(_status_text(rest.strip(), user))
    elif sub == "queue":
        respond(_queue_text(rest.strip()))
    else:
        respond("Usage:\n• `/loc request <what you need>`\n• `/loc status [T12]`\n• `/loc queue [de|pt-BR|es]`")


def _status_text(arg: str, user: str) -> str:
    if arg.upper().startswith("T") and arg[1:].isdigit():
        t = tickets.get_ticket(int(arg[1:]))
        if not t:
            return f"No ticket {arg}."
        units = tickets.list_units(t["id"])
        done = sum(1 for u in units if u["status"] != "proposed")
        return (f"*T{t['id']}* · {t['type']} · {t['target_lang']} · *{t['status']}*\n"
                f"Reviews: {done}/{len(units)} resolved · {t['confidence_summary']}")
    mine = tickets.list_tickets(open_only=True)
    if not mine:
        return "No open tickets. 🎉"
    return "*Open tickets:*\n" + "\n".join(
        f"• T{t['id']} · {t['type']} · {t['target_lang'] or '—'} · {t['status']}" for t in mine[:15])


def _queue_text(lang: str) -> str:
    tix = tickets.list_tickets(open_only=True, lang=lang or None)
    if not tix:
        return f"Queue empty{(' for ' + lang) if lang else ''}. 🎉"
    by_assignee: dict[str, list] = {}
    for t in tix:
        by_assignee.setdefault(t["assignee"] or "unassigned", []).append(t)
    out = [f"*Open queue{(' · ' + lang) if lang else ''}* ({len(tix)} tickets)"]
    for who, ts in by_assignee.items():
        out.append(f"\n*{who}* ({len(ts)})")
        for t in ts[:10]:
            out.append(f"  • T{t['id']} · {t['type']} · {t['target_lang'] or '—'} · {t['status']}")
    return "\n".join(out)


def main() -> None:
    init_db()
    s = get_settings()
    if not s.has_slack():
        raise SystemExit("Slack not configured. See SLACK_SETUP.md and fill SLACK_* in .env.")
    log.info("Starting Loc Sentinel Slack bot (Socket Mode)…")
    SocketModeHandler(app, s.slack_app_token).start()


if __name__ == "__main__":
    main()
