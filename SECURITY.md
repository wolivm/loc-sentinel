# Security

Loc Sentinel is a **public** repo that talks to **real** services (Anthropic, Crowdin, Slack), so
secret hygiene is a first-class concern. This document is the security model + the result of an
audit, and what you must do before deploying anywhere public.

## Secret-handling model
- **All secrets live only in `.env`**, which is gitignored and **was never committed** (verified
  against the full git history). Only `.env.example` — placeholders only — is tracked.
- Tokens are **redacted in logs** (`app/config.py:redact`); the Crowdin client logs `181d…826b`,
  never the full token. No code logs raw keys, request bodies, or the bring-your-own key.
- The hosted Console reads its Anthropic key from a **Render dashboard secret** (`sync: false` in
  `render.yaml`), never from the repo.
- SQL is fully **parameterized** (`?` placeholders); no string-interpolated queries.

## Audit summary (run it yourself)
```bash
# 1. Confirm .env was never tracked
git log --all --full-history -- .env            # expect: empty
# 2. Scan all tracked files + history for live secrets
git ls-files -z | xargs -0 grep -nIE 'sk-ant-api[0-9]|xoxb-[0-9]|xapp-1-|whsec_[A-Za-z0-9]{10}'
git log --all -p | grep -aE 'sk-ant-api[0-9]|xoxb-[0-9]{3,}|xapp-1-[0-9]'   # expect: empty
```
Findings: no secrets in files or history; parameterized SQL; redacted token logging; BYO key never
persisted; container runs as a non-root user.

## Before you deploy publicly — required
- **Webhook secret is mandatory.** The webhook handler verifies an HMAC / shared-secret signature,
  but if `CROWDIN_WEBHOOK_SECRET` is **unset** it falls back to "allow (dev mode)". For any
  internet-reachable webhook receiver, **set `CROWDIN_WEBHOOK_SECRET`** (and the matching Crowdin
  header) so unsigned requests are rejected.
- **Set an Anthropic spend cap** (console.anthropic.com → Limits) if you expose live translation on
  a public Console. The Console also enforces a per-IP rate limit (`DEMO_RATE_LIMIT_PER_MIN`) and a
  280-char input cap, but the spend cap is the hard backstop.
- **Rotate any secret that ever appears in a log or screenshot.** They're real.

## Known, accepted considerations (hackathon scope)
- **The Console has no authentication** — by design; it's a public, read-mostly demo (no DB writes;
  translations are stateless). Don't put private content behind it.
- **Bring-your-own key is transmitted to the host.** If a user pastes their Anthropic key into the
  hosted Console, it is sent (over HTTPS) to the server to make the call. Only paste a key into a
  host you trust; for full control, run the Console locally.
- **Per-IP rate limiting** uses the connecting IP; behind a proxy/LB this may be coarser. It's a
  speed bump, not a hard guarantee — the Anthropic spend cap is the real limit.
- See **[LIMITATIONS.md](LIMITATIONS.md)** for the broader production-hardening list (idempotency,
  rate-limit backoff, race conditions, CSV-as-TM, etc.).

## Reporting
This is a hackathon project; for a real deployment, add a pre-commit secret scanner (e.g. gitleaks)
to CI and a `SECURITY.md` contact. Found something? Open a private advisory on the repo.
