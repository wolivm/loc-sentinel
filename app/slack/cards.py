"""Slack review-card Block Kit + poster.

Information architecture (§7, extended):
  • Per-language review channels (#de-l10n / #pt-l10n / #es-l10n) get the cards —
    each card is the SINGLE human touchpoint for one string in one market.
  • The #localization channel is a PLATFORM DIGEST: "what happened" — N strings
    pushed for which platform, into which languages, how many auto-handled.

Visual design (grounded in Slack guidance):
  • The confidence COLOR BAR is rendered by wrapping blocks in an attachment with
    a `color` field (the only way to get the colored left rail).
  • Color is never the only signal — every card also carries an emoji badge
    (🟢/🟡/🔴), a 5-square confidence meter, and explicit text.
Refs: https://docs.slack.dev/messaging/migrating-outmoded-message-compositions-to-blocks/
      https://docs.slack.dev/block-kit/designing-with-block-kit/
"""

from __future__ import annotations

import json

from app.config import get_settings
from app.engine.sot import load_sot

# Confidence color bar (left rail) + meter squares.
HEX = {"green": "#2EA043", "amber": "#D29922", "red": "#DA3633"}
_SQUARE = {"green": "🟩", "amber": "🟨", "red": "🟥"}


def _market(lang: str):
    try:
        s = load_sot(lang)
        return s.flag, s.market_name, s.formality, s.formality_pronoun
    except Exception:  # noqa: BLE001
        return "", lang, "", ""


def _meter(score: float, color: str) -> str:
    filled = max(0, min(5, int(score * 5 + 0.5)))
    return _SQUARE.get(color, "🟩") * filled + "⬜" * (5 - filled)


def _mrkdwn_escape(text: str) -> str:
    return text.replace("\n", " ⏎ ").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _btn(text: str, action_id: str, value: str, style: str | None = None) -> dict:
    b = {"type": "button", "text": {"type": "plain_text", "text": text}, "action_id": action_id, "value": value}
    if style:
        b["style"] = style
    return b


def build_card(ticket: dict, unit: dict, resolved: dict | None = None) -> dict:
    """Return chat_postMessage/chat_update kwargs: {text, attachments:[{color, blocks}]}."""
    lang = ticket["target_lang"]
    flag, market, formality, pronoun = _market(lang)
    prov = unit.get("provenance", {})
    color = prov.get("confidence_color", "green")
    band = unit["confidence"].upper()
    score = float(unit.get("confidence_score", 0) or 0)
    badge = prov.get("confidence_badge", "")
    src = _mrkdwn_escape(unit["source_en"])
    tgt = _mrkdwn_escape(unit.get("final_target") or unit["proposed_target"] or "—")
    value = json.dumps({"u": unit["id"], "t": ticket["id"]})

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{badge} {unit['key']}", "emoji": True}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Market*\n{flag} {market}"},
            {"type": "mrkdwn", "text": f"*Confidence*\n{_meter(score, color)}  {band} · {score:.2f}"},
        ]},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*English source*\n> {src}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{market} translation*\n*{tgt}*"}},
    ]

    origin = ("♻️  Reused verbatim from Translation Memory" if unit["tm_origin"] == "reused"
              else "🆕  Machine-translated, grounded in the guidelines")
    prov_line = origin + (f"   ·   register: {formality} ({pronoun})" if formality else "")
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": prov_line}]})
    if prov.get("glossary_applied"):
        terms = ", ".join(f"{t['source']}→{t['target']}" for t in prov["glossary_applied"])
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"🔒  Glossary enforced: {terms}"}]})
    if prov.get("tm_alt_targets"):
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": "⚠️  TM conflict — alternatives: " + ", ".join(prov["tm_alt_targets"])}]})

    flags = unit.get("qa_flags", [])
    if flags:
        lines = "\n".join(f"{'🔴' if f['severity'] == 'ERROR' else '🟡'}  *{f['severity']}*  {f['message']}" for f in flags)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Deterministic QA*\n{lines}"}})
    else:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "✅  All deterministic QA gates passed"}]})

    if prov.get("escalate"):
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": "⚠️  *Low confidence* — a deterministic gate failed. Recommend Reject → route to a human."}]})

    if resolved:
        emoji = {"approved": "✅", "edited": "✏️", "rejected": "🚫"}.get(resolved["status"], "•")
        line = f"{emoji}  *{resolved['status'].upper()}*  by {resolved.get('actor', 'someone')}"
        if resolved.get("note"):
            line += f"\n_{resolved['note']}_"
        blocks += [{"type": "divider"}, {"type": "section", "text": {"type": "mrkdwn", "text": line}}]
    else:
        blocks += [{"type": "divider"}, {"type": "actions", "elements": [
            _btn("Approve", "loc_approve", value, style="primary"),
            _btn("Edit", "loc_edit", value),
            _btn("Reject", "loc_reject", value, style="danger"),
        ]}]

    return {"text": f"{badge} {unit['key']} → {tgt}",
            "attachments": [{"color": HEX.get(color, "#4C8DFF"), "blocks": blocks}]}


def post_review_cards(ticket: dict, units: list[dict]) -> dict:
    """Post one review card per unit to the target language's channel."""
    from slack_sdk import WebClient

    s = get_settings()
    if not s.slack_bot_token:
        raise RuntimeError("Slack not configured (SLACK_BOT_TOKEN).")
    channel = s.channel_for(ticket["target_lang"])
    if not channel:
        raise RuntimeError(f"No Slack channel for {ticket['target_lang']}.")
    web = WebClient(token=s.slack_bot_token)
    for u in units:
        web.chat_postMessage(channel=channel, **build_card(ticket, u))
    return {"count": len(units), "channel": channel}


def post_summary(*, n_strings: int, per_lang: list[dict], platform: str,
                 pipeline: str = "GitHub → Crowdin → Loc Sentinel") -> None:
    """Post the platform digest to the #localization summary channel."""
    from slack_sdk import WebClient

    s = get_settings()
    if not s.slack_bot_token or not s.summary_channel:
        return
    total = sum(p["count"] for p in per_lang)
    auto = sum(p["bands"].get("reuse", 0) + p["bands"].get("high", 0) for p in per_lang)
    need = total - auto

    fields = []
    for p in per_lang:
        b = p["bands"]
        green = b.get("reuse", 0) + b.get("high", 0)
        mix = [f"🟢 {green}"] if green else []
        if b.get("medium"):
            mix.append(f"🟡 {b['medium']}")
        if b.get("low"):
            mix.append(f"🔴 {b['low']}")
        chan = f" → <#{p['channel']}>" if p.get("channel") else ""
        fields.append({"type": "mrkdwn",
                       "text": f"*{p['flag']} {p['name']}*\n{p['count']} reviews{chan}\n{'  ·  '.join(mix)}"})

    blocks = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": f"📦 {platform} · {n_strings} new string{'s' if n_strings != 1 else ''} localized",
                                    "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn",
                                     "text": f"New source strings pushed to Crowdin and run through the pipeline.\n*Project:* {platform}   ·   *Flow:* {pipeline}"}},
        {"type": "divider"},
        {"type": "section", "fields": fields[:10]},
        {"type": "context", "elements": [{"type": "mrkdwn",
                                          "text": f"✅  *{auto}/{total}* auto-handled (rubber-stamp)   ·   ⚠️  *{need}* need a human   ·   reviews are queued in the language channels above"}]},
    ]
    WebClient(token=s.slack_bot_token).chat_postMessage(
        channel=s.summary_channel,
        text=f"{platform}: {n_strings} new string(s) localized across {len(per_lang)} markets",
        attachments=[{"color": "#4C8DFF", "blocks": blocks}],
    )
