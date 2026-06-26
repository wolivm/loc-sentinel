# 🛠️ Setup guide (run it on your machine)

This walks a teammate from a fresh clone to a fully working system — offline first, then each live
integration. You can stop after any section; everything degrades gracefully.

> TL;DR — the offline demo needs **no keys**:
> ```bash
> git clone https://github.com/wolivm/loc-sentinel && cd loc-sentinel
> python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> cp .env.example .env
> python scripts/seed.py
> ./run web          # → http://localhost:8000  (the interactive Console)
> ./run cli          # the engine over the sample strings, in your terminal
> ```

---

## 0. Prerequisites
- **Python 3.11+** (3.12 recommended) and **git**.
- Optional: the **GitHub CLI** (`gh`) if you'll recreate the repo; a tunnel (**cloudflared** or
  **ngrok**) only if you wire the Crowdin webhook locally.
- Accounts (only for the live pieces): **Anthropic**, **Crowdin**, **Slack** (a workspace you admin).

## 1. Clone, virtualenv, install
```bash
git clone https://github.com/wolivm/loc-sentinel && cd loc-sentinel
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in as needed (next section)
```

## 2. Configure `.env`
`.env` is **gitignored** — never commit it. Every key, what it's for, and where to get it:

| Key | Needed for | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | translating **new** strings (TM hits + QA need no key) | console.anthropic.com → API keys (`sk-ant-…`) |
| `ANTHROPIC_MODEL` | — | leave `claude-opus-4-8` |
| `CROWDIN_API_TOKEN` | pulling strings + writing translations back | Crowdin → Settings → API → New Token (scopes: Projects, Translations) |
| `CROWDIN_PROJECT_ID` | which project | the number in the project URL / Tools → API |
| `CROWDIN_BASE_URL` | **only** Crowdin Enterprise | `https://<org>.api.crowdin.com` — else leave blank |
| `CROWDIN_WEBHOOK_SECRET` | verifying webhooks | invent a long random string (`python3 -c "import secrets;print(secrets.token_urlsafe(32))"`) |
| `SLACK_BOT_TOKEN` `SLACK_APP_TOKEN` `SLACK_SIGNING_SECRET` | the Slack bot (Socket Mode) | see **[SLACK_SETUP.md](SLACK_SETUP.md)** (click-by-click) |
| `SLACK_LOC_CHANNEL_ID` | the **digest** channel (#localization) | right-click the channel → View details → Channel ID (`C0…`) |
| `SLACK_CHANNEL_DE` `SLACK_CHANNEL_PT_BR` `SLACK_CHANNEL_ES` | per-language review channels | same — one per `#xx-l10n` channel |
| `PLATFORM_LABEL` | label in the digest (App / Web / iOS…) | any string, default `App` |
| `PUBLIC_BASE_URL` | the webhook tunnel URL | set after you start a tunnel (§5) |
| `TARGET_LANGS` | which markets | `de,pt-BR,es` (must match your `data/sot/<lang>/` folders) |
| `DEMO_MODE` `DEMO_RATE_LIMIT_PER_MIN` | the Console | leave defaults |

Raw values, no quotes: `KEY=value`. `has_*()` in `app/config.py` decides which features turn on.

## 3. Seed the offline demo (no keys)
```bash
python scripts/seed.py        # builds the committed translation cache + inits SQLite
./run cli                     # prints proposals + QA flags + confidence for the sample strings
./run web                     # the interactive Console at http://localhost:8000
```

## 4. Slack (Socket Mode — no public URL)
Follow **[SLACK_SETUP.md](SLACK_SETUP.md)** to create the app from `slack_manifest.yaml`, get the four
tokens, create the channels, and **invite the bot to each** (`/invite @loc-sentinel`). Then:
```bash
./run slack
python scripts/simulate_event.py --lang pt-BR --post   # posts real cards, no Crowdin needed
```

## 5. Crowdin — two ways to feed strings in
**(a) GitHub continuous-localization integration (recommended — what we demo):**
1. Put your source strings in `i18n/en.json`; the repo's `crowdin.yml` maps them to
   `/i18n/%locale%.json` and sets `export_only_approved: true`.
2. In Crowdin: **Sources → Set Up Integration → GitHub → Source and translation files mode →**
   authorize, pick the repo + `main` branch. Crowdin reads `crowdin.yml`.
3. Add a **project webhook** (Tools → Webhooks) → URL `https://<your-tunnel>/webhooks/crowdin`,
   events **String added/updated**, custom header `X-Webhook-Secret: <CROWDIN_WEBHOOK_SECRET>`.
4. Start the receiver + a tunnel:
   ```bash
   ./run webhook                       # FastAPI on :8000 (or set WEBHOOK_PORT)
   cloudflared tunnel --url http://localhost:8000   # or: ngrok http 8000
   ```
   Put the printed HTTPS URL into `PUBLIC_BASE_URL` and the webhook URL.
5. Edit `i18n/en.json`, push, **Sync Now** in Crowdin → cards appear in Slack → Approve → Crowdin
   approves → translations PR back to GitHub.

**(b) Offline (no Crowdin):** `python scripts/simulate_event.py --lang de --post` runs the identical
pipeline and posts real Slack cards. This is the on-stage safety net.

## 6. The Source of Truth (the guidelines translations run against)
This is the heart — **how to add/edit a market's guidelines, glossary, and TM** lives in its own
guide: **[data/sot/README.md](data/sot/README.md)**. Short version: a market is a folder under
`data/sot/<lang>/`; adding one needs **no code change**.

## 7. Run modes (recap)
```bash
./run web        # interactive Console (http://localhost:8000)
./run cli FILE   # engine over a sample strings file
./run slack      # Slack Socket Mode bot
./run webhook    # FastAPI Crowdin webhook receiver
python -m app.analytics      # business metrics (% auto-handled, TM hit rate, …)
python -m pytest -q          # the test suite (27 tests, all offline)
```

## Troubleshooting
- **Slack `not_in_channel`** → `/invite @loc-sentinel` into that channel.
- **Crowdin 401** → wrong token/host; Enterprise needs `CROWDIN_BASE_URL`.
- **Webhook 401** → `CROWDIN_WEBHOOK_SECRET` must match the Crowdin header value.
- **Free play "needs a live translation"** → that string isn't cached and no `ANTHROPIC_API_KEY` is
  set; add one to `.env` (or paste one in the Console).
- **Tunnel URL changed** → update `PUBLIC_BASE_URL` and the Crowdin webhook URL (quick tunnels rotate).
- Editing a guideline/glossary? **Restart** the process — the SoT is cached per-process.
