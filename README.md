# 🛡️ Loc Sentinel

**A ~99%-automated localization pipeline with exactly one human touchpoint — a single
rubber-stamp in Slack.** The model is kept *on a leash*: every translation is grounded in a
per-market Source of Truth and verified by deterministic checks before a human ever sees it.

> Built for the Localization hackathon. Standalone, fictional sample product ("Nimbus").
> The repo is public — no proprietary content, no secrets committed.

---

## The problem (and who it helps)

Localization managers drown in repetitive, low-judgement work:

- The **same English strings** get re-translated slightly differently every release →
  inconsistency, glossary drift, and endless review cycles.
- **Stakeholders** (PMs, marketers) have no self-serve way to ask "translate this" or "what's
  the status" without pinging a human and waiting.
- Pure machine translation is fast but **untrustworthy** — it mirrors English punctuation,
  ignores locked terminology, breaks placeholders like `%@` / `{name}`, and gets the market's
  formality wrong. So humans re-check *everything*, and the speed is lost.

**Loc Sentinel** removes the repetitive 99% and concentrates human attention on the 1% that
actually needs judgement. A loc manager's day becomes: glance at a Slack card, see a green
confidence badge and clean QA, click **Approve**. Done.

| Who | What they get |
|---|---|
| **Loc team** | One Slack card per string with confidence + QA flags + provenance. Approve = shipped. Edits *teach* the system. |
| **Requesters (PMs)** | `/loc request` to submit work, `/loc status` to track it — no human ping needed. |
| **Management** | `/loc queue` capacity view; analytics on % auto-handled, TM hit rate, edits learned. |

---

## How it works (the hero flow)

**Continuous localization — no spreadsheets, no manual uploads.** A developer commits an
English string; it flows all the way to shipped, reviewed translations with one human click.

```
  dev edits i18n/en.json ── git push ──▶ Crowdin (GitHub integration) ── webhook ──▶
        │
        ▼
  FastAPI (verify signature, idempotent per string+lang) ──▶ open Ticket
        │
        ▼
  Deterministic RAG engine, per string:
    1. SoT      load this market's Guidelines + Glossary
    2. TM-first exact match? → reuse VERBATIM, confidence 1.0 (no model call)
    3. Translate misses, grounded (glossary + guidelines as a cached prompt prefix)
    4. QA lint  ERROR gates (placeholders, punctuation) block; WARN gates surface
    5. Score    confidence → how the review is framed (green vs amber)
        │
        ▼
  Write proposal back to Crowdin (NOT approved)
        │
        ▼
  Review cards route to per-language channels:   #de-l10n   #pt-l10n   #es-l10n
  Platform digest ("App · N strings localized")  ──▶          #localization
        │
        ▼
  ONE human: Approve → Crowdin approve + append to TM · Edit → save + learn · Reject → route to human
        │
        ▼
  Crowdin pushes ONLY approved translations back to GitHub as a PR ──▶ merge ──▶ in production
```

The confidence score changes **how** the review is presented (green = rubber-stamp, amber =
"check these flags"), but there is **always exactly one human review** — and `crowdin.yml`'s
`export_only_approved` guarantees nothing unreviewed ever reaches the repo.

---

## Why it's different: deterministic, not vibes

The headline isn't "we call an LLM." It's that **the LLM is constrained and then verified**:

- **TM-first**: identical English source → identical target, *always*, with no model call.
- **Glossary enforcement**: locked terms are checked, not hoped for.
- **Deterministic QA linter**: placeholder preservation, punctuation rules, `!`-in-error-string
  bans — these are code, not model judgement. Bad output is *blocked*, not shipped.
- **Confidence scoring** decides routing; low confidence escalates to a human automatically.

See **[DECISIONS.md](DECISIONS.md)** for every deliberate choice + the alternative we rejected,
and **[LIMITATIONS.md](LIMITATIONS.md)** for where it's fragile and how we'd harden it.

---

## Market fit is the point

Each language is a **data folder** encoding *that market's* conventions — register/formality,
punctuation, number/date formats, locked terminology. The same English string renders correctly
and *differently* per market:

| EN source | 🇩🇪 German (formal *Sie*) | 🇧🇷 pt-BR (informal *você*) |
|---|---|---|
| `Save your note` | *Speichern Sie Ihre Notiz* | *Salve sua nota* |

Adding a market = **drop a SoT folder**. Adding a request type = **edit one YAML file**. No code
change. (That's the hackathon's "flexible / scalable" requirement, satisfied by *data*.)

---

## Try it yourself (no accounts, no keys)

> 🎮 **Hosted demo — try it now, no login:** **https://loc-sentinel-console.onrender.com**
> _(free tier — first load may take ~30–60s to wake)_
>
> Or run the self-serve console locally — see [Setup](#setup). The deterministic half (TM, QA,
> glossary, market rules) runs with **no API key**; sample strings use a committed cache of real
> translations so you can play immediately. Bring your own Anthropic key to translate new strings.

---

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in keys as needed (none required for the offline demo)
python scripts/seed.py          # load the Nimbus Source of Truth + TM
```

**Run the self-serve playground (zero keys needed):**
```bash
./run web                       # → http://localhost:8000
```

**Run the CLI over the sample strings:**
```bash
./run cli data/sample_strings/nimbus_en.json
```

**Go live** (real Crowdin + Slack): see [`SLACK_SETUP.md`](SLACK_SETUP.md) and the
[Live setup](#live-setup) section below.

> 👥 **Running it on your own machine / sharing with the team?** The full step-by-step (every `.env`
> key + where to get it, Slack, Crowdin's GitHub integration, tunnels, troubleshooting) is in
> **[SETUP.md](SETUP.md)**. How to manage the **guidelines / Source of Truth** is in
> **[data/sot/README.md](data/sot/README.md)**. Security model + audit: **[SECURITY.md](SECURITY.md)**.

---

## Repository layout

```
app/engine/        deterministic RAG engine (sot, tm, qa, translate, confidence)
app/planner/       tickets state machine, triage, request-type registry
app/crowdin/       API v2 client + signature-verified webhook
app/slack/         Bolt app (Socket Mode): review cards, actions, slash commands
app/web/           self-serve "Loc Sentinel Console" playground
data/sot/<lang>/   guidelines.md + glossary.csv + TM_<lang>.csv  (a market = a folder)
config/            request_types.yaml  (a request type = a row)
scripts/           seed.py, simulate_event.py (offline demo fallback)
```

---

## Documents for judges

- **[PITCH.md](PITCH.md)** — one-screen business case.
- **[DECISIONS.md](DECISIONS.md)** — deliberate engineering choices + rejected alternatives.
- **[LIMITATIONS.md](LIMITATIONS.md)** — honest fragility list + mitigations.
- **[DEMO.md](DEMO.md)** — the 3–5 minute demo script.
- **[SLACK_SETUP.md](SLACK_SETUP.md)** — click-by-click Slack tokens. **[DEPLOY.md](DEPLOY.md)** — host the Console.
- **[SUBMISSION.md](SUBMISSION.md)** — hackathon submission checklist + how to try our solution.

### For developers / your team
- **[SETUP.md](SETUP.md)** — full setup from a fresh clone (every `.env` key, all integrations, troubleshooting).
- **[data/sot/README.md](data/sot/README.md)** — manage the guidelines / glossary / TM (add a market by adding data).
- **[SECURITY.md](SECURITY.md)** — secret-handling model + audit + what to do before a public deploy.

---

## Live setup

Everything above runs offline. To go fully live against **real Crowdin + Slack**:

1. **Slack** (Socket Mode → no tunnel): follow **[SLACK_SETUP.md](SLACK_SETUP.md)**, fill the four
   `SLACK_*` values in `.env`, then `./run slack`.
2. **Crowdin**: put `CROWDIN_API_TOKEN`, `CROWDIN_PROJECT_ID`, and a `CROWDIN_WEBHOOK_SECRET` in `.env`.
3. **Expose the webhook receiver** (Crowdin needs a public URL):
   ```bash
   ./run webhook                       # FastAPI on :8000
   ngrok http 8000                     # or: cloudflared tunnel --url http://localhost:8000
   ```
   Copy the public HTTPS URL into `PUBLIC_BASE_URL`.
4. **Register the webhook in Crowdin**: Project → **Tools → Webhooks → Add Webhook**
   - URL: `https://<your-tunnel>/webhooks/crowdin`
   - Events: **String added**, **String updated** (and/or **File added/updated**)
   - Add a secret header `X-Webhook-Secret: <your CROWDIN_WEBHOOK_SECRET>` (or use a Crowdin App for
     HMAC `X-Crowdin-Signature` — both are verified).
5. **Demo it**: add a source string in Crowdin → a ticket opens, the engine runs, the proposal is
   written back to Crowdin (not approved), and a review card appears in **#localization**. Approve →
   Crowdin marks it approved + the pair is appended to the TM. Then `POST /projects/{id}/translations/builds`
   (the Approve path can trigger a build) = "in production."

**On-stage safety net** — if the tunnel or Crowdin is flaky, `scripts/simulate_event.py` fires the
*exact same pipeline* offline and (with `--post`) posts real Slack cards. The demo never depends on a
live tunnel.

---

## Scalability

Architected so growth is **data and infrastructure, not rewrites**:

- **Config-driven, add-by-data:** a new market = drop a `data/sot/<lang>/` folder; a new request type
  = a row in `config/request_types.yaml`. No code change, no deploy.
- **Stateless engine:** `run_string()` holds no per-request state → scale horizontally behind a queue.
- **Prompt caching of the Source of Truth:** the large guidelines+glossary block is a cached system
  prefix, so per-string cost/latency stays low as volume grows.
- **TM-first:** every exact match is free and instant (no model call), so cost *falls* as the TM grows.
- **Idempotent, signature-verified webhook workers:** safe to run many in parallel; duplicate events
  are no-ops.
- **SQLite now, Postgres-ready:** all ticket state goes through a thin repository boundary; the TM is a
  CSV (the system of record + a Crowdin TM seed) that promotes to a Postgres table unchanged.
- **Scale ceilings we haven't crossed** (and how we'd cross them) are listed honestly in
  **[LIMITATIONS.md](LIMITATIONS.md)** — batching into per-language digests, a real job queue with a
  DLQ, a shared rate limiter, and per-session TM overlays for the multi-user Console.

## Analytics

`python -m app.analytics` prints business-impact metrics over the live ticket store: **% auto-handled
(reuse+high)**, **TM hit rate**, **avg confidence**, **edits learned**, and **escalation rate** — the
numbers a PM cares about (see [PITCH.md](PITCH.md)).
