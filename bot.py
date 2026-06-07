import asyncio
import os
import re
import subprocess
import sys
import tempfile
import logging
from pathlib import Path

import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import yt_dlp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
MAX_BYTES = 50 * 1024 * 1024  # Telegram bot limit

URL_RE = re.compile(r"https?://[^\s]+")
YOUTUBE_RE = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)

ALLOWED_CHAT_IDS = {
    -1003938853999,  # kek
    -1001986640555,  # 2 Козака і 3 супостата (або 5 комп'ютерників) без хуйні
    -4774844208,     # Бібізянські пріколи
    -4268125559,     # Прікольчіки
}

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
AI_SYSTEM_PROMPT = (
    "You're a sarcastic member of a friend group chat. Mirror the tone and "
    "energy of whoever is talking to you — casual stays casual, and if they "
    "swear or talk trash, fire right back the same way without holding back. "
    "Keep replies short and punchy, like a real chat message, not an essay. "
    "Never invent facts, quotes, or events — if you don't actually know "
    "something, say so plainly instead of making something up. If you make a "
    "joke, it has to land on something real (an actual fact, a real quote, an "
    "actual stereotype) — a joke that references something fake isn't funny, "
    "it's just confusing. Don't add disclaimers like 'just joking' — if it's "
    "a joke, the humor should make that obvious on its own."
)


async def ask_ai(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": AI_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 300,
                "temperature": 0.4,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

COOKIES_FILE = "/cookies/cookies.txt"
_has_cookies = Path(COOKIES_FILE).exists()
if _has_cookies:
    log.info("Cookies file found at %s", COOKIES_FILE)

YDL_OPTS = {
    "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best",
    "merge_output_format": "mp4",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extractor_args": {"youtube": {"player_client": ["android", "web", "ios"]}},
    **({"cookiefile": COOKIES_FILE} if _has_cookies else {}),
}


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return

    log.info("Message from chat_id=%s chat_title=%r", message.chat_id, message.chat.title)

    if message.chat_id not in ALLOWED_CHAT_IDS:
        return

    text = message.text
    bot_username = context.bot.username

    if GROQ_API_KEY and bot_username and f"@{bot_username}" in text:
        prompt = text.replace(f"@{bot_username}", "").strip()
        if prompt:
            try:
                reply = await ask_ai(prompt)
                await message.reply_text(reply)
            except Exception:
                log.exception("AI request failed")
        return

    urls = URL_RE.findall(text)
    if not urls:
        return

    for url in urls:
        await handle_url(update, url)


async def handle_url(update: Update, url: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        opts = {**YDL_OPTS, "outtmpl": f"{tmpdir}/%(id)s.%(ext)s"}
        if YOUTUBE_RE.search(url):
            # Cookies push yt-dlp onto YouTube clients that currently hit the
            # SABR-streaming wall (no downloadable formats, only previews).
            # The android/ios clients work fine without cookies for public videos.
            opts.pop("cookiefile", None)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = Path(ydl.prepare_filename(info))

            if not filepath.exists():
                # yt-dlp may have merged into a different name — grab whatever is there
                files = list(Path(tmpdir).iterdir())
                if not files:
                    return
                filepath = files[0]

            size = filepath.stat().st_size
            if size > MAX_BYTES:
                await update.message.reply_text(
                    f"Video is too large ({size // 1024 // 1024} MB) — Telegram allows 50 MB max."
                )
                return

            title = info.get("title", "")
            with open(filepath, "rb") as f:
                await update.message.reply_video(video=f, caption=title, supports_streaming=True)

        except yt_dlp.utils.DownloadError as e:
            log.info("DownloadError for %s: %s", url, e)
        except Exception:
            log.exception("Unexpected error for %s", url)


async def daily_update(_) -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        log.info("Running daily yt-dlp update...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"])
        log.info("yt-dlp updated, restarting bot process...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


async def on_startup(application) -> None:
    asyncio.create_task(daily_update(application))


def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("Bot started, polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
