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

    Deduped by Crowdin string id: a single import often fires BOTH a file.* event
    and string.* events for the same strings, so we'd otherwise process each twice
    (the second add_translation 400s as a duplicate). One string → one unit."""
    out: list[dict] = []
    seen: set = set()

    def _add(s: dict) -> None:
        sid = s.get("id")
        if not s.get("text") or (sid is not None and sid in seen):
            return
        if sid is not None:
            seen.add(sid)
        out.append({
            "source_en": s.get("text", ""),
            "key": s.get("identifier", "") or str(s.get("id", "")),
            "context": s.get("context", "") or "",
            "crowdin_string_id": s.get("id", ""),
        })

    for e in events:
        name = (e.get("event") or "").lower()
        if name.startswith("string."):
            _add(e.get("string") or {})
        elif name.startswith("file.") and client is not None:
            file_id = (e.get("file") or {}).get("id")
            if file_id:
                for s in client.list_strings(file_id=int(file_id)):
                    _add(s)
    return out


def process_strings(strings: list[dict], langs: list[str], *, source: str,
                    event_name: str) -> list[dict]:
    """Run the engine per language, write proposals to Crowdin, post Slack cards."""
    client = get_client()
    results = []
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

        # Post Slack review cards.
        try:
            from app.slack.cards import post_review_cards
            post_review_cards(out["ticket"], out["units"])
        except Exception as ex:  # noqa: BLE001
            log.info("Slack post skipped: %s", ex)

        results.append({"lang": lang, "ticket": out["ticket"]["id"], "auto": True,
                        "units": len(out["units"]), "summary": out["ticket"]["confidence_summary"]})
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
