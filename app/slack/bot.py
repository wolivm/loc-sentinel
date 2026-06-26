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
from app.crowdin.client import get_client
from app.engine.sot import available_langs, load_sot
from app.planner import tickets
from app.planner.db import init_db
from app.slack.actions import finalize_unit
from app.slack.cards import build_card


def _resolve_lang(arg: str):
    """Map a loose lang arg ('de', 'pt', 'es-ES') to one of our SoT langs."""
    a = (arg or "").strip().lower()
    if not a:
        return None
    for l in available_langs():
        if l.lower() == a or l.lower().startswith(a) \
           or load_sot(l).conventions.get("crowdin_locale", "").lower() == a:
            return l
    return None


# Curated demo strings (drawn from the sample pool), ordered so a small N gives
# the full green/amber/red spread: save_button → pt-BR Title-Case WARN,
# loading_notes → es ellipsis ERROR, plus clean ones. For /addstrings & /loc demo.
DEMO_ORDER = ["save_button", "loading_notes", "reminders_today", "streak_safe", "sync_now",
              "welcome_user", "delete_confirm_body", "settings_title", "focus_promo", "habit_done_cheer"]


def _parse_n(text: str, default: int = 5) -> int:
    for tok in (text or "").split():
        if tok.isdigit():
            return max(1, min(int(tok), 10))
    return default


def _run_demo_batch(n: int) -> list[dict]:
    """Synthesize N demo source strings and run the full pipeline (digest + per-lang
    cards). Empty Crowdin id → no Crowdin writes, fully re-runnable."""
    from app.sample_data import load_strings
    samples = {s["key"]: s for s in load_strings()}
    keys = [k for k in DEMO_ORDER if k in samples][:n]
    strings = [{"source_en": samples[k]["source_en"], "key": k,
                "context": samples[k]["context"], "crowdin_string_id": ""} for k in keys]
    from app.main import process_strings
    process_strings(strings, get_settings().langs, source="slack_demo", event_name="string.added")
    return strings


def _demo_respond(respond, n: int) -> None:
    strings = _run_demo_batch(n)
    s = get_settings()
    chans = " ".join(f"<#{s.channel_for(l)}>" for l in s.langs)
    respond(f"🧪 Added *{len(strings)}* demo string(s) to *{s.platform_label}* → "
            f"digest in <#{s.summary_channel}>, *{len(strings)}* review card(s) in each of {chans}.\n"
            f"Go *Approve / Edit / Reject* the cards, then try `/loc coverage`, `/loc pending`, `/loc untranslated`.")


# Real demo strings injected into Crowdin (distinct sources from the GitHub file so
# their translations never collide). First two trip the QA gates (amber / red).
DEMO_STRINGS = [
    ("demo_save_draft", "Save your draft", "Primary button in the editor"),
    ("demo_syncing_data", "Syncing your data", "Loading state"),
    ("demo_streak_safe", "Your streak is safe. Keep it going tomorrow.", "Confirmation after a habit"),
    ("demo_welcome", "Welcome back, %@", "Home greeting; %@ is the user's name"),
    ("demo_focus_promo", "Focus Mode helps you get more done. Try it today!", "Promo card"),
    ("demo_reminder", "Hi {name}, you have a new reminder", "Push notification"),
    ("demo_delete", "Are you sure you want to delete this note? This can't be undone.", "Delete dialog"),
    ("demo_done", "Nice work! You completed today's habit", "Celebration after a habit"),
]
DEMO_FILE = "loc_sentinel_demo.json"


def _addstrings_real(n: int):
    """Inject N real UNtranslated strings into a dedicated Crowdin file, held back
    from the auto-pipeline. Returns (created_ids, error_or_None)."""
    client = get_client()
    if client is None:
        return [], "⚠️ Crowdin isn't configured — can't add strings."
    file_id = client.ensure_file(DEMO_FILE)
    # clean up the previous demo batch (strings + their holds)
    old_ids = [s.get("id") for s in client.list_strings(file_id=int(file_id))]
    for sid in old_ids:
        try:
            client.delete_source_string(sid)
        except Exception as e:  # noqa: BLE001
            log.warning("addstrings cleanup failed for %s: %s", sid, e)
    tickets.release_webhook_hold(old_ids)
    # create the new untranslated batch, holding each id the moment it exists
    created = []
    for ident, text, ctx in DEMO_STRINGS[:n]:
        try:
            s = client.add_source_string(int(file_id), ident, text, ctx)
            sid = s.get("id")
            if sid:
                tickets.hold_from_webhook([sid])   # before the webhook can grab it
                created.append(sid)
        except Exception as e:  # noqa: BLE001
            log.warning("addstrings create failed for %s: %s", ident, e)
    return created, None


def _addstrings_respond(respond, n: int) -> None:
    created, err = _addstrings_real(n)
    if err:
        respond(err)
        return
    s = get_settings()
    respond(
        f"🧪 Injected *{len(created)}* untranslated string(s) into *{s.platform_label}* "
        f"(Crowdin file `{DEMO_FILE}`) — held back from the auto-pipeline so *you* drive them.\n\n"
        f"Now test the live numbers:\n"
        f"• `/loc coverage` → translated% just dropped (real)\n"
        f"• `/loc untranslated` → shows the {len(created)} per market, with *Localize now*\n"
        f"• click *Localize now* → review cards appear in the language channels + proposals written to Crowdin\n"
        f"• `/loc pending` → the {len(created)} awaiting review · Approve them → it drops")

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
    card = build_card(ticket, unit, resolved=resolved)
    client.chat_update(channel=channel, ts=ts, text=card["text"], attachments=card["attachments"])


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
@app.command("/addstrings")
def on_addstrings(ack, respond, command):
    ack()
    _addstrings_respond(respond, _parse_n(command.get("text")))


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
    elif sub == "coverage":
        respond(_coverage_text(_resolve_lang(rest)))
    elif sub == "pending":
        respond(_pending_text(_resolve_lang(rest)))
    elif sub == "untranslated":
        respond(_untranslated_blocks(_resolve_lang(rest)))
    elif sub == "addstrings":
        _addstrings_respond(respond, _parse_n(rest))
    elif sub == "demo":
        _demo_respond(respond, _parse_n(rest))
    else:
        respond(
            "*Loc Sentinel — what you can ask:*\n"
            "• `/loc untranslated [lang]` — what's not translated yet, with a *Localize now* button\n"
            "• `/loc coverage [lang]` — translated % / approved % per market (live from Crowdin)\n"
            "• `/loc pending [lang]` — strings awaiting human review\n"
            "• `/loc request <what you need>` — open a request (auto-triaged; looped to a human if complex)\n"
            "• `/loc status [T12]` — track a request\n"
            "• `/loc queue [lang]` — open work by language / assignee")


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _target_langs(resolved):
    return [resolved] if resolved else get_settings().langs


def _coverage_text(resolved) -> str:
    client = get_client()
    if client is None:
        return "⚠️ Crowdin isn't configured — can't read live coverage."
    prog = {p.get("languageId"): p for p in client.language_progress()}
    lines = ["*📊 Translation coverage* _(live from Crowdin)_"]
    for lang in _target_langs(resolved):
        sot = load_sot(lang)
        p = prog.get(sot.conventions.get("crowdin_locale", lang)) or {}
        ph = p.get("phrases") or {}
        lines.append(
            f"{sot.flag} *{sot.market_name}* — {p.get('translationProgress', 0)}% translated · "
            f"{p.get('approvalProgress', 0)}% approved  ({ph.get('translated', '?')}/{ph.get('total', '?')} strings)")
    return "\n".join(lines)


def _pending_text(resolved) -> str:
    client = get_client()
    if client is None:
        return "⚠️ Crowdin isn't configured."
    prog = {p.get("languageId"): p for p in client.language_progress()}
    s = get_settings()
    lines = ["*🕊️ Awaiting human review* _(translated, not yet approved)_"]
    any_pending = False
    for lang in _target_langs(resolved):
        sot = load_sot(lang)
        ph = (prog.get(sot.conventions.get("crowdin_locale", lang)) or {}).get("phrases") or {}
        pend = max(0, (ph.get("translated", 0) or 0) - (ph.get("approved", 0) or 0))
        if pend:
            any_pending = True
            ch = s.channel_for(lang)
            lines.append(f"{sot.flag} *{sot.market_name}* — *{pend}* pending" + (f" → <#{ch}>" if ch else ""))
        else:
            lines.append(f"{sot.flag} *{sot.market_name}* — ✅ none pending")
    if not any_pending:
        lines.append("\n🎉 Nothing waiting — everything's reviewed.")
    return "\n".join(lines)


def _untranslated_blocks(resolved) -> dict:
    client = get_client()
    if client is None:
        return {"text": "⚠️ Crowdin isn't configured."}
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "🌍 Untranslated strings", "emoji": True}}]
    total = 0
    for lang in _target_langs(resolved):
        sot = load_sot(lang)
        un = client.untranslated_source_strings(sot.conventions.get("crowdin_locale", lang))
        total += len(un)
        if un:
            preview = ", ".join(_esc(u["text"][:28]) for u in un[:3])
            blocks.append({"type": "section",
                           "text": {"type": "mrkdwn", "text": f"{sot.flag} *{sot.market_name}* — *{len(un)}* untranslated\n_{preview}…_"}})
            blocks.append({"type": "actions", "elements": [{
                "type": "button", "style": "primary",
                "text": {"type": "plain_text", "text": f"⚡ Localize {sot.market_name} now"},
                "action_id": "loc_localize", "value": json.dumps({"lang": lang})}]})
        else:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"{sot.flag} *{sot.market_name}* — ✅ all caught up"}]})
    if total == 0:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "🎉 Everything is translated — nothing to do."}]})
    return {"blocks": blocks, "response_type": "in_channel", "text": "Untranslated strings"}


# --------------------------------------------------------------------------- #
# [Localize now] — a stakeholder triggers the pipeline from Slack
# --------------------------------------------------------------------------- #
@app.action("loc_localize")
def on_localize(ack, body, respond):
    ack()
    lang = json.loads(body["actions"][0]["value"])["lang"]
    sot = load_sot(lang)
    client = get_client()
    if client is None:
        respond("⚠️ Crowdin isn't configured.")
        return
    un = client.untranslated_source_strings(sot.conventions.get("crowdin_locale", lang))
    if not un:
        respond(f"{sot.flag} {sot.market_name}: already all caught up ✅")
        return
    strings = [{"source_en": u["text"], "key": u["identifier"] or str(u["id"]),
                "context": u["context"], "crowdin_string_id": u["id"]} for u in un]
    from app.main import process_strings
    process_strings(strings, [lang], source="slack_localize", event_name="string.added")
    tickets.release_webhook_hold([u["id"] for u in un])   # now translated — no longer held
    ch = get_settings().channel_for(lang)
    respond(f"⚡ Localizing *{len(strings)}* string(s) into {sot.flag} *{sot.market_name}* — "
            f"proposals written to Crowdin, review cards posted to <#{ch}>. One human approve away from shipped.")


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
