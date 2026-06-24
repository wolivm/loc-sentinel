# LIMITATIONS — where this is fragile, and how we'd harden it

> Judging criterion (d): *"I appreciate when people are self-aware and know where the system or
> their code is fragile or vulnerable and inform us unprompted."* So here it is, volunteered.
> Everything below is a conscious hackathon trade-off, with the production fix named.

Legend: 🟢 mitigated now · 🟡 partially mitigated · 🔴 known gap (hackathon scope).

---

### Webhook replay / idempotency — 🟢
Webhooks retry; a duplicate must not double-translate or crash. **Now:** signature-verified, and
events are deduped by id (processed-event table) so replays are no-ops. **Harden:** persist the
dedupe set in Postgres/Redis with a TTL instead of SQLite, and make the worker fully transactional.

### Crowdin rate limits + transient failures — 🟡
The Crowdin API rate-limits and can 5xx. **Now:** the client uses retry with exponential backoff +
jitter and honors `Retry-After`. **Gap:** no global token-bucket across concurrent workers, so a
big upload could still hit limits. **Harden:** a shared rate limiter + a real job queue with retry
DLQ.

### Model hallucination / format breakage — 🟢 (this is the core mitigation)
LLMs invent text and break placeholders. **Now:** every output passes the deterministic QA linter
(placeholder-set equality, punctuation rules) **before** it can reach Crowdin or Slack; failures
are blocked and escalated to a human, not shipped. Glossary coverage is verified post-generation.
**Residual risk:** a *semantically* wrong but format-clean translation can pass the linter — which
is exactly why there is always one human review.

### Secret handling on a public repo — 🟢
Repo is public + integrations are real. **Now:** all secrets live only in `.env` (gitignored);
`.env.example` ships placeholders; tokens are redacted in logs; a `slack_manifest.yaml` contains
no secrets. **Harden:** move to a secret manager (Doppler / AWS SM) and short-lived tokens; add a
pre-commit secret scanner (gitleaks) to CI.

### Concurrent approvals / race conditions — 🟡
Two reviewers could click Approve on the same card at once, or Approve while an Edit modal is open.
**Now:** ticket state transitions are guarded (a unit already `approved` ignores a second approve),
and the audit log records the actor. **Gap:** no row-level lock; the Slack card isn't disabled the
instant someone starts acting. **Harden:** optimistic locking on the unit row + immediately disable
the card's buttons on first interaction.

### Single-language / small-scale demo scope — 🟡
The hero demo runs a handful of strings in a couple of markets. **Now:** the engine is stateless
and config-driven, so N markets / thousands of strings is an architecture we *describe* and the
code supports. **Gap:** we haven't load-tested thousands of concurrent strings; no batching digest
in the demo path by default. **Harden:** batch into a per-language digest card + a worker pool.

### TM is a CSV (system of record) — 🟡
Great for transparency and Crowdin TM seeding; not great under concurrent writes. **Now:** appends
are serialized through a single writer and the file is the seed/export, with SQLite holding live
ticket state. **Gap:** CSV has no transactions; a crash mid-append could in theory corrupt a row.
**Harden:** promote the TM to a Postgres table with the CSV as an import/export format only.

### Demo-mode translation cache — 🟡 (disclosed by design)
The public, key-less demo serves a **committed cache** for the sample strings (see DECISIONS #11).
**Implications, stated plainly:** (1) offline you're seeing cached output, not a fresh model call —
brand-new strings need a bring-your-own key; (2) two cached entries deliberately preserve common raw
model mistakes (an ellipsis, a Title-cased button) so the QA gates visibly fire — these are real
failure modes, labelled, not staged bugs. `scripts/build_cache.py` regenerates the cache from the
live model when a key is present.

### Console is multi-user with a shared TM — 🟡
Approve/Edit on the hosted Console append to the TM so visitors *see it learn* — but that TM is
shared, so one visitor's edit affects the next visitor's reuse, and a careless edit could seed a poor
TM entry. **Now:** a **Reset demo TM** button restores the pristine seed (snapshot taken at startup),
the hosted filesystem is ephemeral (redeploy resets), and a per-IP rate limit blunts abuse. **Harden:**
per-session TM overlays so each visitor's learning is isolated.

### Confidence score is heuristic — 🟡
"High/medium/low" comes from QA + glossary coverage, not a calibrated probability. **Now:** it only
*modulates how the review is framed* and routing — it never auto-approves, so a miscalibrated score
can't ship a bad string on its own. **Harden:** calibrate against human accept/edit/reject outcomes
over time (the audit log already captures the signal).

### Webhook tunnel for the demo (ngrok/cloudflared) — 🔴 (hackathon-grade)
Crowdin needs a public URL; we use a dev tunnel. **Gap:** tunnels drop and URLs rotate on the free
tier. **Mitigation:** `scripts/simulate_event.py` fires the exact same pipeline offline, so the
demo never depends on a live tunnel. **Harden:** deploy the receiver behind a stable HTTPS endpoint.

### What is production-hardened vs. hackathon-grade
- **Production-ready in spirit:** the deterministic engine (TM/QA/confidence), config-as-data,
  signature verification, idempotency, audit logging, the stateless boundary.
- **Hackathon-grade:** the tunnel, single-process worker (no distributed queue yet), CSV-as-TM,
  SQLite, no auth on the playground beyond rate limiting, no automated tests beyond the engine core.
