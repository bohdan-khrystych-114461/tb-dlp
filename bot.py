import asyncio
import os
import re
import subprocess
import sys
import tempfile
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import yt_dlp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
MAX_BYTES = 50 * 1024 * 1024  # Telegram bot limit

URL_RE = re.compile(r"https?://[^\s]+")

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
    **({"cookiefile": COOKIES_FILE} if _has_cookies else {}),
}


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return

    urls = URL_RE.findall(message.text)
    if not urls:
        return

    for url in urls:
        await handle_url(update, url)


async def handle_url(update: Update, url: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        opts = {**YDL_OPTS, "outtmpl": f"{tmpdir}/%(id)s.%(ext)s"}

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

        except yt_dlp.utils.DownloadError:
            pass  # URL wasn't a supported video — silently ignore
        except Exception:
            log.exception("Unexpected error for %s", url)


async def daily_update(_) -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        log.info("Running daily yt-dlp update...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"])
        log.info("yt-dlp updated, restarting bot process...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(
        lambda a: asyncio.ensure_future(daily_update(a))
    ).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("Bot started, polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
