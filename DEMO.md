# 🎬 Demo script (3–5 min) — tuned to the judging criteria

> Goal: make a PM think "I want this," show the model is *steered not steering*, and be honest about
> fragility — unprompted. Have two terminals + Slack #localization + the Console open.
> **Backup:** every live step has an offline equivalent (`simulate_event.py`, the Console).

**Pre-flight**
```bash
source .venv/bin/activate
python scripts/seed.py          # cache ready, no key needed
./run slack                     # terminal 1 (Socket Mode bot)
# (optional live) ./run webhook + ngrok, webhook registered in Crowdin
```

---

### 1 · The problem (20s) — *practicality + buy-in (a,b)*
"Loc teams re-translate the same strings every release — inconsistency, glossary drift, endless review
cycles. Pure MT is fast but untrustworthy, so humans re-check everything and the speed is lost.
**Loc Sentinel** automates ~99% and leaves **one** human action: a rubber-stamp in Slack."

### 2 · Trigger the hero flow (45s) — *real, end-to-end (a)*
- **Live:** add a source string in Crowdin → webhook fires.
- **Backup:** `python scripts/simulate_event.py --lang pt-BR --post`

"A ticket opened, the engine ran every string, wrote proposals back to Crowdin (not approved), and
posted review cards." → switch to **#localization**.

### 3 · The review card (40s) — *deliberate choices (c)*
Point at one card: "Confidence badge, the **deterministic QA** result, which **glossary** terms were
enforced, and **TM provenance** — reused verbatim vs new. The model proposed; *rules disposed*."

### 4 · The three actions (60s) — *human-in-the-loop + it learns*
- **Approve** a 🟢 high-confidence one: "rubber-stamp → Crowdin approved + appended to the TM."
- **Edit** the 🟡 `save_button` (`Salvar Sua Nota` → `Salvar sua nota`): "the QA *warned* Title Case; I
  fix it, and the **edited** pair is learned — next time it's instant TM reuse."
- **Reject** the 🔴 `loading_notes` (es `Cargando tus notas…`): "the model added an ellipsis — a super
  common habit. The **ERROR gate blocked it** before it could ship; it routes to a human with a reason.
  *This is the whole thesis: the model is on a leash.*"

### 5 · Market fit (40s) — *our headline strength (f)* — in the **Console**
Open the hosted Console, click `reminders_today`:
"Same English, fit for each market — 🇩🇪 German uses **Sie** (formal): *Sie haben heute {count}…*; 🇧🇷
Brazil uses **Você** (informal): *Você tem {count}…*. Placeholders preserved, conventions per market.
Each market is just a **data folder**."

### 6 · Scale & flexibility (30s) — *choice + scalability (e)*
"Adding a market = drop a `data/sot/<lang>/` folder. Adding a request type = one row in
`config/request_types.yaml`." Show the YAML; in Slack run `/loc request we need Polish for the new market`
→ "unknown type → it knows to loop in a human." Then `python -m app.analytics`: **98% auto-handled,
0.92 avg confidence, 2% escalation.**

### 7 · Honest moment (20s) — *self-awareness (d)*
Open **LIMITATIONS.md**: "Here's where it's fragile — webhook replay (we made it idempotent), Crowdin
rate limits (backoff), the demo tunnel (we ship an offline fallback), and the shared-TM Console (reset +
per-session overlays to harden). We tell you before you ask."

### 8 · Try it yourself (15s) — *peer appeal (g)*
"Don't take my word — **here's a link, no login**: paste any English string, watch the gates fire, see
it render per market." → the hosted **Console** URL. "Approved strings are marked ready in Crowdin →
trigger a build = in production."

---
**One-liners to land:** *"The determinism is the point."* · *"The model proposes, the rules dispose."*
· *"Add a market by adding data, not code."*
