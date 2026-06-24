#!/usr/bin/env python3
"""Fire a fake Crowdin event locally — the on-stage demo safety net.

Three modes:
  (default) offline : run the orchestrator directly and print a text preview of
                      each Slack review card. No server, no network.
  --post            : also post REAL Slack review cards (needs Slack configured).
  --webhook         : POST a signed Crowdin-style payload to the running FastAPI
                      receiver (exercises the full live path end-to-end).

Examples:
  python scripts/simulate_event.py --lang pt-BR
  python scripts/simulate_event.py --lang es --keys loading_notes,sync_now,streak_safe
  python scripts/simulate_event.py --lang de --post
  python scripts/simulate_event.py --lang de --webhook
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import orchestrator  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.planner import tickets  # noqa: E402
from app.planner.db import init_db  # noqa: E402
from app.sample_data import load_strings  # noqa: E402

BADGE_LINE = {"green": "🟢", "amber": "🟡", "red": "🔴"}


def render_card_text(unit: dict) -> str:
    prov = unit["provenance"]
    lines = [
        "┌─────────────────────────────────────────────",
        f"│ {prov.get('confidence_badge','')} Review · {unit['key']}  ({unit['confidence'].upper()})",
        f"│ EN:  {unit['source_en']!r}",
        f"│ →    {unit['proposed_target']!r}",
        f"│ origin: {'TM reuse' if unit['tm_origin']=='reused' else 'new ('+prov.get('translation_origin','')+')'}",
    ]
    if unit["qa_flags"]:
        for f in unit["qa_flags"]:
            lines.append(f"│   {f['severity']}: {f['message']}")
    else:
        lines.append("│   ✓ all QA gates passed")
    if prov.get("glossary_applied"):
        terms = ", ".join(f"{t['source']}→{t['target']}" for t in prov["glossary_applied"])
        lines.append(f"│   glossary: {terms}")
    lines.append("│ [ Approve ]  [ Edit ]  [ Reject ]")
    lines.append("└─────────────────────────────────────────────")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default=None, help="target language (default: first TARGET_LANG)")
    ap.add_argument("--keys", default="", help="comma-separated sample string keys (default: all)")
    ap.add_argument("--post", action="store_true", help="post real Slack cards (needs Slack)")
    ap.add_argument("--webhook", action="store_true", help="POST a signed payload to the receiver")
    args = ap.parse_args()

    init_db()
    settings = get_settings()
    lang = args.lang or (settings.langs[0] if settings.langs else "de")

    all_strings = load_strings()
    if args.keys:
        wanted = {k.strip() for k in args.keys.split(",")}
        strings = [s for s in all_strings if s["key"] in wanted]
    else:
        strings = all_strings

    if args.webhook:
        return _post_webhook(strings, lang, settings)

    print(f"\n⚡ Simulating Crowdin string.added → {lang}  ({len(strings)} strings)\n")
    out = orchestrator.open_translation_ticket(
        strings=strings, lang=lang, source="simulate_event", event_name="string.added",
    )
    t = out["ticket"]
    print(f"🎫 Ticket T{t['id']}  type={t['type']}  status={t['status']}  lang={t['target_lang']}")
    print(f"   confidence: {t['confidence_summary']}\n")
    for u in out["units"]:
        print(render_card_text(u))
        print()

    if args.post:
        try:
            from app.slack.cards import post_review_cards
            posted = post_review_cards(out["ticket"], out["units"])
            print(f"📨 Posted {posted} Slack review card(s) to #{settings.slack_loc_channel_id}")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Slack post skipped: {e}")

    # Audit trail for the demo narrative
    print("\n📜 Audit log:")
    for a in tickets.audit_for(f"ticket:T{t['id']}"):
        print(f"   {a['at']}  {a['from_state']} → {a['to_state']}  by {a['actor']}  {a['detail']}")
    return 0


def _post_webhook(strings: list[dict], lang: str, settings) -> int:
    import json
    import httpx
    from app.crowdin.webhook import sign_payload

    events = [{
        "event": "string.added",
        "string": {"id": s["crowdin_string_id"], "identifier": s["key"],
                   "text": s["source_en"], "context": s["context"]},
    } for s in strings]
    body = json.dumps({"events": events}).encode()
    sig = sign_payload(body, settings.crowdin_webhook_secret)
    url = (settings.public_base_url or f"http://localhost:{settings.webhook_port}").rstrip("/")
    url += f"/webhooks/crowdin?lang={lang}"
    print(f"POST {url}  ({len(events)} events, signed)")
    r = httpx.post(url, content=body, headers={
        "Content-Type": "application/json", "X-Crowdin-Signature": sig,
    }, timeout=30)
    print(f"← {r.status_code}  {r.text[:300]}")
    return 0 if r.status_code < 400 else 1


if __name__ == "__main__":
    sys.exit(main())
