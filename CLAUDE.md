# tb-dlp — Telegram Video Downloader Bot

A Telegram bot that automatically downloads and re-uploads videos when a URL is posted in a group chat. Uses yt-dlp for downloading and runs on Fly.io.

## How it works

1. Someone posts a URL in the Telegram group
2. Bot detects it automatically (no commands needed)
3. Downloads the video via yt-dlp using browser cookies for authentication
4. Sends the video back to the group
5. Videos over 50MB are rejected with a message

## Infrastructure

- **Hosting**: Fly.io (app name: `tb-dlp`, region: `ams`)
- **Machines**:
  - Primary: `9185d546f76ee8` (always running)
  - Standby: `9185d542a751d8` (stopped, takes over on hardware failure)
- **Volumes**: Each machine has a `cookies_vol` volume mounted at `/cookies`
- **yt-dlp**: Auto-updates itself every 24 hours inside the bot, no redeploy needed

## Cookies

### Why cookies are needed

yt-dlp needs browser cookies to download from platforms that require login:
- **Instagram** — always requires cookies
- **Twitter/X** — much more reliable with cookies
- **Facebook** — requires cookies
- **YouTube** — only needed for age-restricted/private videos
- **TikTok** — needed for some region-restricted content

Cookies expire every 30–90 days. When they expire, the bot will silently fail to download from those platforms.

### How to get new cookies

1. Install a browser extension:
   - Chrome/Edge: **Get cookies.txt LOCALLY**
   - Firefox: **cookies.txt**
2. Log into Instagram, Twitter/X, Facebook, TikTok, YouTube in your browser
3. Use the extension to export cookies for all sites into a single `cookies.txt` file
4. Save it to `C:\source\personal\tb-dlp\cookies.txt`

### How to upload new cookies

The cookies file lives on Fly.io volumes (not in the Docker image or secrets).
Both machines need the file uploaded separately. The standby must be temporarily started.

```powershell
$fly = "$env:USERPROFILE\.fly\bin\fly.exe"

# Delete old file from primary and upload new one
& $fly sftp shell --app tb-dlp  # then run: rm /cookies/cookies.txt
& $fly sftp put --app tb-dlp --machine 9185d546f76ee8 "C:\source\personal\tb-dlp\cookies.txt" /cookies/cookies.txt

# Do the same for standby
& $fly machine start 9185d542a751d8 --app tb-dlp
Start-Sleep -Seconds 5
& $fly sftp put --app tb-dlp --machine 9185d542a751d8 "C:\source\personal\tb-dlp\cookies.txt" /cookies/cookies.txt
& $fly machine stop 9185d542a751d8 --app tb-dlp

# Restart primary to pick up new cookies
& $fly machine restart 9185d546f76ee8 --app tb-dlp
```

Note: `fly sftp put` refuses to overwrite existing files. To replace, first delete via `fly sftp shell` using the `rm` command, then upload.

## Deploying changes

```powershell
cd "C:\source\personal\tb-dlp"
git add .
git commit -m "your message"
git push
fly deploy --app tb-dlp --ha=false
```

Use `--ha=false` to avoid Fly.io trying to create a second machine automatically (we manage the standby manually).

## Checking logs

```powershell
fly logs --app tb-dlp
```

You should see `getUpdates HTTP/1.1 200 OK` every 10 seconds — that means the bot is alive and polling Telegram.

## Bot token

Stored as a Fly.io secret (`BOT_TOKEN`). Never hardcoded. To rotate:
1. Go to @BotFather → `/mybots` → select bot → Revoke token
2. `fly secrets set BOT_TOKEN=<new_token> --app tb-dlp`

## Files

- `bot.py` — thin entrypoint shim (`from tb_dlp.main import main; main()`)
- `tb_dlp/` — the actual bot package
  - `config.py` — env vars, constants, regexes, logging setup
  - `storage.py` — generic `JSONStore` helper for persisted JSON state
  - `ai.py` — Gemini client, system prompt, language detection, AI on/off toggle
  - `chats.py` — chat whitelist + chat name lookups
  - `stats.py` — usage stats + video cache
  - `chat_history.py` — per-chat recent message history for AI context
  - `bot_messages.py` — tracks messages the bot sent (for the 👎 delete reaction)
  - `comebacks.py` — comeback examples/phrases shown to the AI
  - `profiles.py` — per-user profile notes, auto-updated from chat activity
  - `replies.py` — builds AI replies (prompt assembly, rate-limit handling)
  - `downloader.py` — yt-dlp/gallery-dl download + send logic
  - `handlers.py` — Telegram message/command/reaction handlers
  - `lifecycle.py` — daily yt-dlp self-update + startup hook
  - `main.py` — builds the `Application` and starts polling
  - `web/` — the admin dashboard (aiohttp), one module per page
- `Dockerfile` — upgrades yt-dlp on every startup, then runs bot.py
- `fly.toml` — Fly.io config (region, VM size, volume mount)
- `requirements.txt` — Python dependencies
- `cookies.txt` — **gitignored**, never commit this
