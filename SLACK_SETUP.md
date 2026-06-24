# 🔧 Slack setup — click-by-click (clean workspace)

You need **four** values in `.env`. This guide gets all four with minimal clicking by
using the committed `slack_manifest.yaml` (it pre-fills scopes, Socket Mode, and the
`/loc` command, so you mostly click *Create → Install → copy*).

| `.env` key | What it is | Looks like |
|---|---|---|
| `SLACK_BOT_TOKEN` | Bot token (acts as the bot) | `xoxb-…` |
| `SLACK_APP_TOKEN` | App-level token (Socket Mode) | `xapp-1-…` |
| `SLACK_SIGNING_SECRET` | App signing secret | 32 hex chars |
| `SLACK_LOC_CHANNEL_ID` | The #localization channel id | `C0…` |

---

## 1. Create the app from the manifest (~30 seconds)
1. Go to **https://api.slack.com/apps** → **Create New App**.
2. Choose **From an app manifest**.
3. Pick **your workspace** → **Next**.
4. Delete the placeholder, **paste the entire contents of `slack_manifest.yaml`** (YAML tab) → **Next** → **Create**.

You're now on the app's **Basic Information** page.

## 2. Grab the Signing Secret
1. On **Basic Information**, scroll to **App Credentials**.
2. Under **Signing Secret**, click **Show**, copy it → this is `SLACK_SIGNING_SECRET`.

## 3. Create an App-Level Token (Socket Mode)
1. Still on **Basic Information**, scroll to **App-Level Tokens** → **Generate Token and Scopes**.
2. Token name: `socket` (anything).
3. Click **Add Scope** → choose **`connections:write`**.
4. **Generate** → copy the `xapp-1-…` token → this is `SLACK_APP_TOKEN`.
   *(Socket Mode itself is already enabled by the manifest — verify under **Settings → Socket Mode** that the toggle is ON.)*

## 4. Install the app & get the Bot Token
1. Left sidebar → **Settings → Install App** (or **OAuth & Permissions**).
2. Click **Install to Workspace** → **Allow**.
3. Copy **Bot User OAuth Token** (`xoxb-…`) → this is `SLACK_BOT_TOKEN`.

## 5. Create the channel & get its ID
1. In Slack, create a channel named **#localization** (Public is simplest; Private works too — the manifest includes `groups:read`).
2. **Invite the bot:** in the channel, type `/invite @loc-sentinel` (or channel name ▸ **Integrations → Add apps**).
3. **Get the channel ID:** click the channel name ▸ **About** tab → scroll to the bottom → copy the **Channel ID** (`C0…`) → this is `SLACK_LOC_CHANNEL_ID`.
   *(Or right-click the channel → **Copy link**; the ID is the `C0…` at the end of the URL.)*

## 6. Fill `.env` and run
```bash
# .env
SLACK_BOT_TOKEN=xoxb-…
SLACK_APP_TOKEN=xapp-1-…
SLACK_SIGNING_SECRET=…
SLACK_LOC_CHANNEL_ID=C0…
```
```bash
./run slack          # starts the Socket Mode bot (no tunnel needed)
```
Then post a demo card without touching Crowdin:
```bash
python scripts/simulate_event.py --lang pt-BR --post
```
You should see a ticket header + review cards appear in **#localization**, each with
**Approve / Edit / Reject**. Try `/loc queue` and `/loc status` from the message box.

---

### Troubleshooting
- **`not_in_channel` when posting** → invite the bot: `/invite @loc-sentinel`.
- **Slash command does nothing** → confirm **Socket Mode** is ON (Settings → Socket Mode) and the bot process (`./run slack`) is running.
- **`invalid_auth`** → you copied the User token, not the **Bot** token (`xoxb-`), or the app-level token isn't `xapp-`.
- **Buttons don't respond** → interactivity is delivered over Socket Mode; make sure `SLACK_APP_TOKEN` has the `connections:write` scope and the bot is running.
- Re-paste the manifest anytime under **App Manifest** if scopes drift; then reinstall.
