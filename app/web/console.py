"""Loc Sentinel Console — a self-serve, account-free web playground.

Renders the Slack review card in the browser and runs the REAL deterministic
pipeline: TM reuse, glossary enforcement, QA ERROR/WARN gates, confidence, and
the two-market side-by-side. Approve/Edit mutate the TM so visitors SEE it learn.

Demo mode (no key): sample strings use the committed translation cache.
Bring-your-own key: translate arbitrary new strings live.
"""

from __future__ import annotations

import shutil
import time
from collections import defaultdict, deque
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import CACHE_DIR, SOT_DIR, get_settings
from app.engine import tm
from app.engine.pipeline import run_string
from app.engine.sot import available_langs, load_sot
from app.sample_data import load_strings

HERE = Path(__file__).resolve().parent
INDEX = HERE / "static" / "index.html"
SNAPSHOT = CACHE_DIR / "runtime" / "tm_snapshot"


@asynccontextmanager
async def lifespan(app: FastAPI):
    _snapshot_tms()
    yield


app = FastAPI(title="Loc Sentinel Console", lifespan=lifespan)

# Tiny per-IP rate limit (protects the hosted demo / our key).
_HITS: dict[str, deque] = defaultdict(deque)


def _snapshot_tms() -> None:
    """Back up the pristine seed TMs once so /api/reset can restore them."""
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    for lang in available_langs():
        src = SOT_DIR / lang / f"TM_{lang}.csv"
        dst = SNAPSHOT / f"TM_{lang}.csv"
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)


def _restore_tms() -> int:
    n = 0
    for lang in available_langs():
        snap = SNAPSHOT / f"TM_{lang}.csv"
        if snap.exists():
            shutil.copy2(snap, SOT_DIR / lang / f"TM_{lang}.csv")
            n += 1
    return n


def _rate_ok(ip: str, limit: int) -> bool:
    now = time.monotonic()
    q = _HITS[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def _market_meta(lang: str) -> dict:
    sot = load_sot(lang)
    c = sot.conventions
    return {"lang": lang, "name": sot.market_name, "flag": sot.flag,
            "formality": sot.formality, "pronoun": sot.formality_pronoun,
            "inverted": bool(c.get("inverted_punctuation"))}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX.read_text(encoding="utf-8")


@app.get("/api/config")
def config() -> dict:
    s = get_settings()
    langs = [l for l in s.langs if l in available_langs()] or available_langs()
    return {
        "langs": langs,
        "markets": [_market_meta(l) for l in langs],
        "demo_mode": s.demo_mode,
        "has_key": s.has_anthropic(),
    }


@app.get("/api/samples")
def samples() -> dict:
    return {"strings": load_strings()}


@app.post("/api/translate")
async def translate_endpoint(request: Request) -> JSONResponse:
    s = get_settings()
    ip = request.client.host if request.client else "?"
    if not _rate_ok(ip, s.demo_rate_limit_per_min):
        return JSONResponse({"error": "Rate limit — slow down a moment."}, status_code=429)

    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "Enter an English string."}, status_code=400)
    if len(text) > 280:
        return JSONResponse({"error": "For the hosted demo, keep strings under 280 characters."}, status_code=400)
    key = body.get("key", "")
    context = body.get("context", "")
    byo = (body.get("byo_key") or "").strip() or None
    langs = body.get("langs") or [m["lang"] for m in (config()["markets"])]

    results = []
    for lang in langs:
        if lang not in available_langs():
            continue
        r = run_string(text, lang, key=key, context=context,
                       prefer_cache=(byo is None), api_key=byo)
        d = r.to_dict()
        d["market"] = _market_meta(lang)
        results.append(d)
    return JSONResponse({"source": text, "results": results})


@app.post("/api/resolve")
async def resolve_endpoint(request: Request) -> JSONResponse:
    """Approve/Edit append to the TM (the system learns); re-run shows TM reuse."""
    body = await request.json()
    lang = body.get("lang")
    source_en = body.get("source_en", "")
    status = body.get("status")
    final_target = (body.get("final_target") or "").strip()
    if lang not in available_langs() or not source_en:
        return JSONResponse({"error": "bad request"}, status_code=400)

    learned = None
    if status in ("approved", "edited") and final_target:
        from datetime import date
        action = tm.append(source_en, final_target, lang, date.today().isoformat())
        # Re-run to prove it now reuses verbatim from TM.
        after = run_string(source_en, lang)
        learned = {"tm_action": action, "after": after.to_dict()}
    return JSONResponse({"ok": True, "status": status, "learned": learned})


@app.post("/api/reset")
def reset_endpoint() -> dict:
    n = _restore_tms()
    return {"ok": True, "restored": n}
