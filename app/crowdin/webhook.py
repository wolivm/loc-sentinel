"""Crowdin webhook signature verification + idempotency helpers.

Crowdin secures webhooks two ways depending on setup:
  • Crowdin Apps sign the body with HMAC-SHA256 using the app secret, sent in
    an `X-Crowdin-Signature` header (hex).
  • Project-level webhooks commonly use a custom secret header you configure.

We accept BOTH and fall back gracefully, so the handler verifies what it can and
never crashes on shape (LIMITATIONS: signature on a public repo + tunnel).
"""

from __future__ import annotations

import hashlib
import hmac


def sign_payload(body: bytes, secret: str) -> str:
    """HMAC-SHA256 hex signature of the raw body (used by simulate_event + apps)."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _const_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a or "", b or "")


def verify(body: bytes, headers: dict, secret: str) -> tuple[bool, str]:
    """Return (ok, reason). If no secret is configured we allow (dev mode) but say so."""
    if not secret:
        return True, "no secret configured (dev mode — set CROWDIN_WEBHOOK_SECRET)"

    # Normalize header lookup (case-insensitive).
    h = {k.lower(): v for k, v in headers.items()}

    # 1) HMAC signature (Crowdin Apps / our simulate_event)
    sig = h.get("x-crowdin-signature")
    if sig:
        expected = sign_payload(body, secret)
        if _const_eq(sig, expected):
            return True, "hmac ok"
        return False, "hmac mismatch"

    # 2) Shared-secret custom header (project webhooks)
    for header in ("x-webhook-secret", "x-crowdin-secret", "authorization"):
        val = h.get(header, "")
        if header == "authorization":
            val = val.replace("Bearer ", "").replace("bearer ", "")
        if val and _const_eq(val, secret):
            return True, f"shared secret via {header}"

    return False, "no valid signature or secret header present"


def event_fingerprint(body: bytes) -> str:
    """Stable id for idempotency. Crowdin doesn't always send a unique event id,
    so we hash the raw body — a duplicate delivery hashes identically."""
    return hashlib.sha256(body).hexdigest()[:32]
