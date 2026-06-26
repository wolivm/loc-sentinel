"""FastAPI app — the Crowdin webhook receiver (the hero-flow entry point).

POST /webhooks/crowdin
  1. verify the signature (HMAC or shared secret)
  2. dedupe by body fingerprint (idempotent — a replay is a no-op)
  3. pull the new/changed source strings
  4. for each TARGET lang: run the engine, open a ticket, write the proposal back
     to Crowdin (NOT approved), and post a Slack review card
A duplicate or malformed event must NEVER crash the demo.
"""

from __future__ import annotations

import logging
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.crowdin import webhook
from app.crowdin.client import get_client
from app.engine.sot import available_langs, load_sot
from app.orchestrator import open_translation_ticket
from app.planner import tickets
from app.planner.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("webhook")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    s = get_settings()
    log.info("Loc Sentinel up. langs=%s crowdin=%s slack=%s",
             s.langs, s.has_crowdin(), s.has_slack())
    yield


app = FastAPI(title="Loc Sentinel", version="0.1.0", lifespan=lifespan)


@app.get("/")
def root() -> dict:
    s = get_settings()
    return {
        "service": "loc-sentinel",
        "webhook": "/webhooks/crowdin",
        "langs": s.langs,
        "crowdin_configured": s.has_crowdin(),
        "slack_configured": s.has_slack(),
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _strings_from_events(events: list[dict], client) -> list[dict]:
    """Extract source strings from a Crowdin events payload (tolerant of shape).

    We act on PER-STRING events only (string.added / string.updated). A Crowdin
    sync also fires a file.* event for the same change; acting on that too would
    re-list and re-translate the whole file (bulk duplicates). With the GitHub
    continuous-localization integration, the per-string events are authoritative,
    so the file event is intentionally ignored. Deduped by string id within the
    payload; cross-delivery dedup is handled by tickets.already_proposed().
    (File-based fallback via client.list_strings() is available but disabled here.)"""
    out: list[dict] = []
    seen: set = set()
    for e in events:
        name = (e.get("event") or "").lower()
        if not name.startswith("string."):
            continue
        s = e.get("string") or {}
        sid = s.get("id")
        if not s.get("text") or (sid is not None and sid in seen):
            continue
        # Demo strings injected by /addstrings are held back from the auto-pipeline
        # so a human can clear them via /loc untranslated → [Localize now].
        if tickets.is_webhook_held(sid):
            log.info("string %s is held (demo) — skipping auto-translate", sid)
            continue
        if sid is not None:
            seen.add(sid)
        out.append({
            "source_en": s.get("text", ""),
            "key": s.get("identifier", "") or str(sid or ""),
            "context": s.get("context", "") or "",
            "crowdin_string_id": sid or "",
        })
    return out


def process_strings(strings: list[dict], langs: list[str], *, source: str,
                    event_name: str) -> list[dict]:
    """Run the engine per language, write proposals to Crowdin, route review cards
    to the per-language channels, and post a platform digest to #localization."""
    client = get_client()
    results = []
    per_lang_summary = []
    for lang in langs:
        if lang not in available_langs():
            log.warning("no SoT for lang %s — skipping", lang)
            continue
        # Idempotency across multiple webhook deliveries for one sync: skip
        # strings already proposed for this lang+source (changed source re-runs).
        fresh = [s for s in strings
                 if not tickets.already_proposed(s.get("crowdin_string_id"), lang, s["source_en"])]
        if not fresh:
            log.info("all %d strings already proposed for %s — skipping", len(strings), lang)
            results.append({"lang": lang, "skipped": "already proposed"})
            continue
        out = open_translation_ticket(
            strings=fresh, lang=lang, source=source, event_name=event_name,
        )
        if not out["auto"]:
            results.append({"lang": lang, "ticket": out["ticket"]["id"], "auto": False})
            continue

        sot = load_sot(lang)
        crowdin_locale = sot.conventions.get("crowdin_locale", lang)

        # Write proposals back to Crowdin (NOT approved). Never crash on failure.
        if client is not None:
            for u in out["units"]:
                sid = u.get("crowdin_string_id")
                if sid and u["proposed_target"]:
                    try:
                        client.add_translation(int(sid), crowdin_locale, u["proposed_target"])
                    except Exception as ex:  # noqa: BLE001
                        log.warning("Crowdin add_translation failed for U%s: %s", u["id"], ex)

        # Route review cards to the per-language channel.
        try:
            from app.slack.cards import post_review_cards
            post_review_cards(out["ticket"], out["units"])
        except Exception as ex:  # noqa: BLE001
            log.info("Slack post skipped for %s: %s", lang, ex)

        bands = Counter(u["confidence"] for u in out["units"])
        per_lang_summary.append({
            "lang": lang, "name": sot.market_name, "flag": sot.flag,
            "count": len(out["units"]), "bands": bands,
            "channel": get_settings().channel_for(lang),
        })
        results.append({"lang": lang, "ticket": out["ticket"]["id"], "auto": True,
                        "units": len(out["units"]), "summary": out["ticket"]["confidence_summary"]})

    # Platform digest → #localization.
    if per_lang_summary:
        try:
            from app.slack.cards import post_summary
            post_summary(n_strings=len(strings), per_lang=per_lang_summary,
                         platform=get_settings().platform_label,
                         string_keys=[s.get("key", "") for s in strings])
        except Exception as ex:  # noqa: BLE001
            log.info("Slack summary skipped: %s", ex)
    return results


@app.post("/webhooks/crowdin")
async def crowdin_webhook(request: Request) -> JSONResponse:
    s = get_settings()
    body = await request.body()

    ok, reason = webhook.verify(body, dict(request.headers), s.crowdin_webhook_secret)
    if not ok:
        log.warning("rejected webhook: %s", reason)
        return JSONResponse({"ok": False, "error": "signature"}, status_code=401)

    # Idempotency: a duplicate delivery is a no-op (never double-translate/crash).
    fp = webhook.event_fingerprint(body)
    if tickets.already_processed(fp):
        log.info("duplicate webhook %s — ignored", fp)
        return JSONResponse({"ok": True, "duplicate": True})

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}
    events = payload.get("events") or ([payload] if payload.get("event") else [])

    # ?lang= overrides; otherwise translate into all configured target languages.
    qlang = request.query_params.get("lang")
    langs = [qlang] if qlang else s.langs

    client = get_client()
    strings = _strings_from_events(events, client)
    if not strings:
        tickets.mark_processed(fp)
        return JSONResponse({"ok": True, "note": "no translatable strings in payload"})

    results = process_strings(strings, langs, source="crowdin_webhook",
                              event_name=(events[0].get("event") if events else "string.added"))
    tickets.mark_processed(fp)
    return JSONResponse({"ok": True, "verified": reason, "strings": len(strings), "results": results})
