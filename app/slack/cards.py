"""Slack review-card Block Kit + poster.

The card is the SINGLE human touchpoint (§7). It shows source, proposal,
confidence badge, QA flags, and glossary/TM provenance, with Approve / Edit /
Reject. Confidence modulates the framing (green rubber-stamp vs amber "check
these flags") — but there is always exactly one review.
"""

from __future__ import annotations

import json

from app.config import get_settings

_SEV = {"ERROR": "🔴", "WARN": "🟡"}


def _btn(text: str, action_id: str, value: str, style: str | None = None) -> dict:
    b = {"type": "button", "text": {"type": "plain_text", "text": text}, "action_id": action_id, "value": value}
    if style:
        b["style"] = style
    return b


def build_review_blocks(ticket: dict, unit: dict, resolved: dict | None = None) -> list[dict]:
    prov = unit.get("provenance", {})
    badge = prov.get("confidence_badge", "")
    band = unit["confidence"].upper()
    src = unit["source_en"].replace("\n", "⏎")
    tgt = (unit.get("final_target") or unit["proposed_target"] or "—").replace("\n", "⏎")
    value = json.dumps({"u": unit["id"], "t": ticket["id"]})

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{badge} Review · {unit['key']}", "emoji": True}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Market*\n{ticket['target_lang']}"},
            {"type": "mrkdwn", "text": f"*Confidence*\n{band}  ({unit.get('confidence_score', 0):.2f})"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*EN*  `{src}`\n*→*  *{tgt}*"}},
    ]

    origin = "♻️ TM reuse (verbatim)" if unit["tm_origin"] == "reused" \
        else f"🆕 new · {prov.get('translation_origin', 'model')}"
    ctx = [origin]
    if prov.get("glossary_applied"):
        ctx.append("glossary: " + ", ".join(f"{t['source']}→{t['target']}" for t in prov["glossary_applied"]))
    if prov.get("tm_alt_targets"):
        ctx.append("⚠️ TM conflict: " + ", ".join(prov["tm_alt_targets"]))
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(ctx)}]})

    flags = unit.get("qa_flags", [])
    if flags:
        lines = "\n".join(f"{_SEV.get(f['severity'], '•')} *{f['severity']}* {f['message']}" for f in flags)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": lines}})
    else:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "✅ all QA gates passed"}]})

    if resolved:
        emoji = {"approved": "✅", "edited": "✏️", "rejected": "🚫"}.get(resolved["status"], "•")
        line = f"{emoji} *{resolved['status'].upper()}* by {resolved.get('actor', 'someone')}"
        if resolved.get("note"):
            line += f" — {resolved['note']}"
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": line}]})
    else:
        blocks.append({"type": "actions", "elements": [
            _btn("Approve", "loc_approve", value, style="primary"),
            _btn("Edit", "loc_edit", value),
            _btn("Reject", "loc_reject", value, style="danger"),
        ]})
    return blocks


def post_review_cards(ticket: dict, units: list[dict]) -> int:
    """Post one review card per unit to the #localization channel. Returns count."""
    from slack_sdk import WebClient

    s = get_settings()
    if not (s.slack_bot_token and s.slack_loc_channel_id):
        raise RuntimeError("Slack not configured (SLACK_BOT_TOKEN / SLACK_LOC_CHANNEL_ID).")
    web = WebClient(token=s.slack_bot_token)

    header = (f"📥 *Ticket T{ticket['id']}* · {ticket['type']} · {ticket['target_lang']}\n"
              f"Confidence: {ticket['confidence_summary']}")
    web.chat_postMessage(channel=s.slack_loc_channel_id, text=header)
    for u in units:
        web.chat_postMessage(
            channel=s.slack_loc_channel_id,
            text=f"Review {u['key']} → {u['proposed_target']}",  # fallback/notification text
            blocks=build_review_blocks(ticket, u),
        )
    return len(units)
