# 🎬 Demo script & shot list (3–5 min) — the REAL live system

> What you'll show: a developer's git commit becomes shipped, reviewed, market-correct
> translations — with exactly one human click — across a live GitHub ↔ Crowdin ↔ Slack pipeline,
> plus a hosted Console anyone can try. Mapped to the judging criteria in `README.md`.

## Pre-flight (have these running / open)
- Local services up: `./run webhook` (+ `cloudflared`/`ngrok` tunnel) and `./run slack`.
- Crowdin **MAD_hackathon** project, GitHub integration connected, `export_only_approved` active.
- Slack open with **#localization**, **#de-l10n**, **#pt-l10n**, **#es-l10n** (cleared of old test cards).
- Hosted Console open: **https://loc-sentinel-console.onrender.com**
- GitHub repo `i18n/en.json` open in a browser tab (for the live edit).
- For a pristine spectrum: optionally delete the test strings in Crowdin + reset the local DB first.

---

### 1 · The problem (20s) — *practicality + buy-in (a,b)*
"Localization is a flood of repetitive, low-judgement work — the same strings re-translated every
release, inconsistency, endless review cycles. Pure MT is fast but untrustworthy, so humans re-check
everything. **Loc Sentinel** automates ~99% and leaves exactly **one** human action: a rubber-stamp
in Slack — and the model is on a leash, verified by deterministic checks."

### 2 · A developer ships a string (45s) — *real, end-to-end (a) + scalability (e)*
- In GitHub, edit **`i18n/en.json`**, add a key (e.g. `"empty_state": "Create your first note"`),
  **Commit to main**. "No spreadsheet. A developer just shipped an English string."
- Crowdin → **Sync Now** (or wait for auto-sync). "Crowdin imports it and fires our webhook."

### 3 · The pipeline fans out to Slack (45s) — *deliberate choices (c) + market fit (f)*
- **#localization** gets the platform **digest**: "📦 App · 1 new string localized · 🟢 ready".
  "One message tells management what happened across every market — App today, but Web/iOS/Android
  scale the same way."
- The **review card** lands in each language channel (#de-l10n / #pt-l10n / #es-l10n). Point at one:
  "Confidence meter, the **deterministic QA** result, which **glossary** terms were enforced, TM
  provenance — reused vs new. The model proposed; *rules disposed*."

### 4 · The one human touchpoint (60s) — *human-in-the-loop + it learns*
- **Approve** a 🟢 card → Crowdin shows it **verified**, card updates to "approved in Crowdin, TM
  reinforced." "Rubber-stamp."
- **Edit** a 🟡 card (fix a Title-Case warning) → save → "the **edited** pair is learned into the TM —
  next identical string is instant reuse."
- **Reject** a 🔴 card (the ellipsis the model added, caught by the ERROR gate) → "blocked before it
  could ship, routed to a human. *This is the whole thesis — the model on a leash.*"

### 5 · Back to production (30s) — *closes the loop (a)*
- Crowdin → **Sync Now** → GitHub **Pull Request** appears (`l10n_main` → `main`) with the translated
  files. "And because `crowdin.yml` says `export_only_approved`, **only human-approved strings are in
  this PR** — the ellipsis one is not here." **Merge it.** "Shipped. One commit → reviewed
  translations in production."

### 6 · Try it yourself + market fit (40s) — *peer appeal (g) + market fit (f)*
- Open the **hosted Console** (no login). Click `reminders_today`:
  "Same English — 🇩🇪 German uses **Sie** (formal): *Sie haben heute {count}…*; 🇧🇷 Brazil uses
  **Você** (informal). Each market is just a **data folder**." Paste *Loading your notes* → the
  **ellipsis ERROR** fires in red. "Judges can try this live — link's in the README."

### 7 · Scale, flexibility & honesty (30s) — *choice/scalability (e) + self-awareness (d)*
- "Add a market = drop a `data/sot/<lang>/` folder. Add a request type = one YAML row." Run
  `python -m app.analytics`: **~98% auto-handled, 0.92 avg confidence.**
- Open **LIMITATIONS.md**: "Here's where it's fragile and how we'd harden it — webhook replay
  (idempotent), rate limits (backoff), the demo tunnel (offline fallback), shared-TM Console (reset).
  We tell you before you ask."

---
**Lines to land:** *"The determinism is the point."* · *"The model proposes, the rules dispose."*
· *"Add a market by adding data, not code."* · *"One commit → reviewed translations in production,
with one human click."*

**On-stage safety net:** if the tunnel or Crowdin is flaky, `python scripts/simulate_event.py
--lang pt-BR --post` fires the identical pipeline and posts real cards; the Console never needs the
tunnel at all.
