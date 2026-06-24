# 🚀 Deploy the Loc Sentinel Console (hosted "try it" link)

The Console runs in **demo mode** — it serves the committed translation cache and
needs **no secrets**, so it's safe to host publicly. Pick one:

## Option A — Render (free, one click)
1. Push this repo to GitHub (already done).
2. Go to **https://render.com** → **New → Blueprint** → connect this repo.
3. Render reads `render.yaml`, builds the `Dockerfile`, and deploys. **Apply.**
4. You get a public URL like `https://loc-sentinel-console.onrender.com`.
   Put it at the top of `README.md` and in your demo.

## Option B — Railway / Fly.io
- **Railway:** New Project → Deploy from repo → it detects the `Dockerfile` (or the `Procfile`). Set `DEMO_MODE=true`.
- **Fly.io:** `fly launch` (uses the `Dockerfile`) → `fly deploy`. The app listens on `$PORT`.

## Option C — Local (no Docker needed)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed.py      # build the offline cache
./run web                   # → http://localhost:8000
```

## Notes
- **No API key required** for sample strings (committed cache). A visitor can paste
  their own `ANTHROPIC_API_KEY` in the UI to translate brand-new strings live.
- The Console rate-limits per IP (`DEMO_RATE_LIMIT_PER_MIN`, default 20/min).
- Approve/Edit mutate the TM so visitors see it *learn*; **Reset demo TM** restores
  the pristine seed (snapshot taken at startup). The hosted filesystem is ephemeral,
  so a redeploy also resets it.
- This deploys the **Console only**. The Slack bot + Crowdin webhook are run locally
  for the live demo (Slack uses Socket Mode → no public URL; Crowdin needs a tunnel —
  see README → Live setup).
