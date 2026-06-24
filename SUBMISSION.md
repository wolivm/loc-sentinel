# 📦 Hackathon submission

| Requirement | Status | Where |
|---|---|---|
| ✅ Completed application | **Done** | This repo — runs live against Crowdin + Slack; offline demo with zero setup. |
| 🎥 Short demo video (recommended) | Follow **[DEMO.md](DEMO.md)** | Record the 8-beat, 3–5 min script. |
| 🧪 Optional test data so others can try it | **Done — and then some** | See "Try our solution" below. |
| 🏷️ Team name & logo (optional) | Team **Loc Sentinel** · 🛡️ shield mark | Easy to swap. |

---

## Try our solution (this is our differentiator)

We didn't just attach test data — we made the whole product **clickable with no accounts and no keys**.

### 1. Hosted Console (zero setup) — *recommended for judges*
> 🎮 **Live link:** _add after deploying — see [DEPLOY.md](DEPLOY.md) (one click on Render)_

Paste any English UI string (or click a sample) and watch the **real** deterministic pipeline run:
TM reuse, glossary enforcement, the QA ERROR/WARN gates, confidence scoring, and the **same string
rendered correctly for two different markets** (formal 🇩🇪 vs informal 🇧🇷). Approve/Edit and see it
**learn**. Optionally paste your own Anthropic key to translate brand-new strings live.

### 2. Run it yourself in 3 commands
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python scripts/seed.py                 # builds the offline cache — no key needed
./run web                              # → http://localhost:8000  (the Console)
# or the CLI:  ./run cli data/sample_strings/nimbus_en.json
# or post real Slack cards:  python scripts/simulate_event.py --lang pt-BR --post
```

### 3. The test data itself (fictional "Nimbus")
- `data/sot/<de|pt-BR|es>/` — guidelines + glossary + TM per market (the Source of Truth).
- `data/sample_strings/nimbus_en.json` — 22 English strings seeded with a Title-Case trap, error
  strings, placeholders, an ellipsis trap, multi-sentence strings, and several TM exact-matches, so
  every gate and TM reuse visibly fire.
- `config/request_types.yaml` — the request-type registry (add a use case by adding a row).

Everything is **fictional and public-safe** — no proprietary content, no secrets committed.

## What to look at first
1. **[PITCH.md](PITCH.md)** — the one-screen business case.
2. The **Console** (link above) — try it in 30 seconds.
3. **[DECISIONS.md](DECISIONS.md)** / **[LIMITATIONS.md](LIMITATIONS.md)** — deliberate choices + honest fragility.
