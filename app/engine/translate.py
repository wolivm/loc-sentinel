"""Grounded translation via the Anthropic API (DECISIONS #5, #6).

The SoT (guidelines + glossary) is sent as a STABLE, cached system prefix; only
the per-string user turn varies. Output is constrained with structured outputs
so it's deterministically parseable, then handed to qa.py for verification —
the model proposes, the linter disposes.

Demo mode (DECISIONS #11): a committed cache of REAL translations lets the
playground run with NO API key. Brand-new strings need a (bring-your-own) key.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import CACHE_DIR, get_settings
from app.engine.normalize import normalize_source
from app.engine.sot import SoT

CACHE_FILE = CACHE_DIR / "translations.json"

def _clean_target(text: str) -> str:
    """Strip whitespace, a leading 'Translation:'-style label, and one layer of
    surrounding quotes — defensive parsing of a plain-text model reply."""
    t = (text or "").strip()
    for label in ("translation:", "target:", "output:"):
        if t.lower().startswith(label):
            t = t[len(label):].strip()
    if len(t) >= 2 and t[0] in "\"'“”«»" and t[-1] in "\"'“”«»":
        t = t[1:-1].strip()
    return t


# --------------------------------------------------------------------------- #
# Response cache (committed; powers the key-less demo + reproducible re-runs)
# --------------------------------------------------------------------------- #
def _load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def cache_get(source_en: str, lang: str) -> str | None:
    return _load_cache().get(lang, {}).get(normalize_source(source_en))


def cache_put(source_en: str, lang: str, target: str) -> None:
    cache = _load_cache()
    cache.setdefault(lang, {})[normalize_source(source_en)] = target
    _save_cache(cache)


# --------------------------------------------------------------------------- #
# Translator
# --------------------------------------------------------------------------- #
class TranslationUnavailable(RuntimeError):
    """Raised when a string is uncached and no API key is available."""


def _user_turn(source_en: str, key: str, context: str, is_error_hint: bool) -> str:
    from app.engine.normalize import extract_placeholders
    ph = list(extract_placeholders(source_en).elements())
    ph_line = (", ".join(sorted(set(ph))) if ph else "(none)")
    return (
        "Translate this English UI string into the target language. Output ONLY the translated "
        "string itself — no quotes, no label, no notes, no explanation.\n"
        f"key: {key or '(none)'}\n"
        f"context: {context or '(none)'}\n"
        f"placeholders that MUST appear verbatim: {ph_line}\n"
        f"this is an error/failure string: {'yes' if is_error_hint else 'no'}\n"
        f"source (English): {source_en}"
    )


def translate(source_en: str, lang: str, sot: SoT, *, key: str = "", context: str = "",
              is_error_hint: bool = False, prefer_cache: bool = True,
              api_key: str | None = None) -> dict:
    """Return {target, origin} where origin ∈ {cache, model}.

    prefer_cache=True (default) keeps the demo reproducible & offline. A
    per-request `api_key` (bring-your-own) overrides the env key for the
    playground without ever persisting it.
    """
    if prefer_cache:
        cached = cache_get(source_en, lang)
        if cached is not None:
            return {"target": cached, "origin": "cache"}

    settings = get_settings()
    effective_key = api_key or settings.anthropic_api_key
    if not effective_key:
        raise TranslationUnavailable(
            "This string isn't in the demo cache and no Anthropic API key is set. "
            "Add ANTHROPIC_API_KEY to .env, or paste a key in the playground (bring-your-own)."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=effective_key)
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        system=[{
            "type": "text",
            "text": sot.system_prefix(),
            "cache_control": {"type": "ephemeral"},   # cache the SoT prefix
        }],
        messages=[{"role": "user", "content": _user_turn(source_en, key, context, is_error_hint)}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    target = _clean_target(text)
    if prefer_cache and target:
        cache_put(source_en, lang, target)   # learn it for next time
    return {"target": target, "origin": "model"}
