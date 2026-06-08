import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    MessageReactionHandler,
    filters,
)
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
    -5170628911,     # Чат де соромно за свою англійську
    -1003988355756,  # 🩳 шорти 🔞
}

# Admin-only commands (/stats, /profile) are restricted to a private DM from
# this Telegram user — keeps usage data and member profiles out of the groups.
ADMIN_USER_ID = 247313805


def _is_admin_dm(message) -> bool:
    return (
        message.chat.type == "private"
        and message.from_user is not None
        and message.from_user.id == ADMIN_USER_ID
    )

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Try the newest/sharpest model first, then fall back to others with looser
# free-tier daily quotas if it's 429ing — only once *all* of them are
# exhausted do we give up and send a "перекур" reply (see RATE_LIMIT_*).
GEMINI_MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
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
    "a joke, the humor should make that obvious on its own. When someone asks "
    "a question with actual logic or reasoning behind it, work through that "
    "logic for real before answering — a witty line that falls apart the "
    "moment someone thinks about it for two seconds is worse than no joke "
    "at all."
)


# Gemini free tier caps us at ~20 generateContent calls/day — when that's hit,
# the AI call 429s and we obviously can't ask the AI to write its own excuse.
# First time it happens we say so once; after that we keep it short so the
# chat doesn't get the same "I'm out" speech on every single mention.
RATE_LIMIT_FIRST_REPLY = "Так, я на перекур и спать."
RATE_LIMIT_REPEAT_REPLY = "Сплю, не напрягай плз."
_rate_limited_once = False


async def ask_ai(prompt: str, user_note: str = "", history: list[dict] | None = None) -> str:
    system_parts = [AI_SYSTEM_PROMPT]
    if user_note:
        system_parts.append(user_note)

    contents = [*(history or []), {"role": "user", "parts": [{"text": prompt}]}]
    payload = {
        "system_instruction": {"parts": [{"text": "\n\n".join(system_parts)}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 300,
            # Some models spend tokens on invisible internal "thinking" before
            # answering — left enabled, that burns most of maxOutputTokens on
            # reasoning and truncates the visible reply mid-word. Replies are
            # short chat messages, not problems needing step-by-step reasoning.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        last_error: httpx.HTTPStatusError | None = None
        for model in GEMINI_MODELS:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": GEMINI_API_KEY},
                json=payload,
            )
            if resp.status_code == 429:
                last_error = httpx.HTTPStatusError(
                    f"429 from {model}", request=resp.request, response=resp
                )
                continue
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        assert last_error is not None
        raise last_error

# Telegram keeps uploaded videos on its own servers — resending by file_id
# is instant and needs no re-download/re-upload. Cache URL -> file_id so the
# same link posted again (or forwarded later) doesn't cost a fresh download.
VIDEO_CACHE_FILE = "/cookies/video_cache.json"
MAX_CACHE_ENTRIES = 500
try:
    VIDEO_CACHE: dict[str, str] = json.loads(Path(VIDEO_CACHE_FILE).read_text())
except (FileNotFoundError, json.JSONDecodeError):
    VIDEO_CACHE = {}


def _save_video_cache() -> None:
    try:
        Path(VIDEO_CACHE_FILE).write_text(json.dumps(VIDEO_CACHE))
    except OSError:
        log.exception("Failed to persist video cache")


def _remember_video(url: str, file_id: str) -> None:
    # Dicts keep insertion order — drop the oldest entries first (FIFO) so the
    # cache file doesn't grow without bound.
    VIDEO_CACHE[url] = file_id
    while len(VIDEO_CACHE) > MAX_CACHE_ENTRIES:
        VIDEO_CACHE.pop(next(iter(VIDEO_CACHE)))
    _save_video_cache()


STATS_FILE = "/cookies/stats.json"
try:
    STATS: dict = json.loads(Path(STATS_FILE).read_text())
except (FileNotFoundError, json.JSONDecodeError):
    STATS = {"total": 0, "cache_hits": 0, "by_platform": {}}


def _save_stats() -> None:
    try:
        Path(STATS_FILE).write_text(json.dumps(STATS))
    except OSError:
        log.exception("Failed to persist stats")


def _platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if "youtu" in host:
        return "youtube"
    if "instagram" in host:
        return "instagram"
    if "tiktok" in host:
        return "tiktok"
    if "twitter" in host or host == "x.com":
        return "twitter/x"
    if "facebook" in host or host == "fb.watch":
        return "facebook"
    if "reddit" in host:
        return "reddit"
    return host or "other"


def _record_stat(url: str, *, cache_hit: bool, chat_id: int, chat_title: str | None) -> None:
    platform = _platform_from_url(url)

    STATS["total"] = STATS.get("total", 0) + 1
    if cache_hit:
        STATS["cache_hits"] = STATS.get("cache_hits", 0) + 1
    by_platform = STATS.setdefault("by_platform", {})
    by_platform[platform] = by_platform.get(platform, 0) + 1

    by_chat = STATS.setdefault("by_chat", {})
    chat_stats = by_chat.setdefault(str(chat_id), {"title": chat_title, "total": 0, "cache_hits": 0, "by_platform": {}})
    chat_stats["title"] = chat_title  # keep the latest title (groups get renamed)
    chat_stats["total"] += 1
    if cache_hit:
        chat_stats["cache_hits"] += 1
    chat_platform = chat_stats.setdefault("by_platform", {})
    chat_platform[platform] = chat_platform.get(platform, 0) + 1

    _save_stats()


# Lightweight per-member profiles so AI replies can be tailored to whoever's
# talking — built up automatically from their own messages (interests, tone,
# recurring topics), no manual input needed.
USER_PROFILES_FILE = "/cookies/user_profiles.json"
USER_MESSAGE_BUFFERS_FILE = "/cookies/user_message_buffers.json"
PROFILE_UPDATE_THRESHOLD = 25  # messages collected before (re)summarizing someone

try:
    USER_PROFILES: dict[str, dict] = json.loads(Path(USER_PROFILES_FILE).read_text())
except (FileNotFoundError, json.JSONDecodeError):
    USER_PROFILES = {}

# Persisted to disk — the bot restarts daily for yt-dlp updates (and on every
# deploy), and an in-memory buffer would never reach PROFILE_UPDATE_THRESHOLD.
try:
    _raw_buffers = json.loads(Path(USER_MESSAGE_BUFFERS_FILE).read_text())
    USER_MESSAGE_BUFFERS: dict[int, list[str]] = {int(k): v for k, v in _raw_buffers.items()}
except (FileNotFoundError, json.JSONDecodeError):
    USER_MESSAGE_BUFFERS = {}

# Recent back-and-forth per (chat, person) so @mention replies can follow up on
# what was just said instead of treating every message as a fresh conversation.
# In-memory only — losing it on restart is fine, it's just short-term context.
CONVERSATIONS: dict[str, list[dict]] = {}
CONVERSATION_TURNS = 6  # how many user+model exchanges to keep per person

# You (and only you) can react with 👎 on a bot message to delete it. We track
# which (chat, message_id) pairs are the bot's own so this can never be used to
# remove someone else's message.
DELETE_REACTION_EMOJI = "👎"
BOT_MESSAGE_IDS: set[tuple[int, int]] = set()
MAX_TRACKED_MESSAGES = 1000


def _track_bot_message(chat_id: int, message_id: int) -> None:
    BOT_MESSAGE_IDS.add((chat_id, message_id))
    if len(BOT_MESSAGE_IDS) > MAX_TRACKED_MESSAGES:
        BOT_MESSAGE_IDS.pop()


def _save_user_profiles() -> None:
    try:
        Path(USER_PROFILES_FILE).write_text(json.dumps(USER_PROFILES))
    except OSError:
        log.exception("Failed to persist user profiles")


def _save_message_buffers() -> None:
    try:
        Path(USER_MESSAGE_BUFFERS_FILE).write_text(json.dumps(USER_MESSAGE_BUFFERS))
    except OSError:
        log.exception("Failed to persist user message buffers")


async def _update_profile(user_id: int, name: str) -> None:
    messages = USER_MESSAGE_BUFFERS.get(user_id, [])
    if len(messages) < PROFILE_UPDATE_THRESHOLD:
        return
    USER_MESSAGE_BUFFERS[user_id] = []
    _save_message_buffers()

    existing = USER_PROFILES.get(str(user_id), {}).get("notes", "")
    prompt = (
        f"Recent chat messages from {name}:\n" + "\n".join(messages) + "\n\n"
        + (f"Existing notes about them: {existing}\n\n" if existing else "")
        + "In one or two short, neutral sentences, note their interests and how "
          "they talk (tone, humor, recurring topics) based ONLY on what's shown "
          "above, so future replies to them can be tailored. No judgments, no "
          "guessing beyond the evidence."
    )
    try:
        notes = await ask_ai(prompt)
    except Exception:
        log.exception("Failed to update profile for %s", name)
        return

    USER_PROFILES[str(user_id)] = {"name": name, "notes": notes}
    _save_user_profiles()


COOKIES_FILE = "/cookies/cookies.txt"
_has_cookies = Path(COOKIES_FILE).exists()
if _has_cookies:
    log.info("Cookies file found at %s", COOKIES_FILE)

YDL_OPTS = {
    # Prefer pre-muxed formats first — merging separate video+audio streams
    # via ffmpeg spikes memory and OOM-killed the bot on a 256MB machine.
    "format": "best[height<=720][ext=mp4]/best[height<=720]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
    "merge_output_format": "mp4",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extractor_args": {"youtube": {"player_client": ["android", "web", "ios"]}},
    **({"cookiefile": COOKIES_FILE} if _has_cookies else {}),
}


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _rate_limited_once

    message = update.message
    if not message or not message.text:
        return

    log.info("Message from chat_id=%s chat_title=%r", message.chat_id, message.chat.title)

    if message.chat_id not in ALLOWED_CHAT_IDS:
        return

    text = message.text
    bot_username = context.bot.username
    user = message.from_user

    if GEMINI_API_KEY and user and not user.is_bot:
        USER_MESSAGE_BUFFERS.setdefault(user.id, []).append(text)
        _save_message_buffers()
        asyncio.create_task(_update_profile(user.id, user.full_name))

    if GEMINI_API_KEY and bot_username and f"@{bot_username}" in text:
        prompt = text.replace(f"@{bot_username}", "").strip()
        if prompt:
            convo_key = f"{message.chat_id}:{user.id}"
            try:
                profile = USER_PROFILES.get(str(user.id)) if user else None
                user_note = (
                    f"A note about {user.full_name}, who's talking to you right now: {profile['notes']}"
                    if profile else ""
                )
                history = CONVERSATIONS.get(convo_key, [])
                reply = await ask_ai(prompt, user_note, history=history)
                sent = await message.reply_text(reply)
                _track_bot_message(sent.chat_id, sent.message_id)

                history = history + [
                    {"role": "user", "parts": [{"text": prompt}]},
                    {"role": "model", "parts": [{"text": reply}]},
                ]
                CONVERSATIONS[convo_key] = history[-(CONVERSATION_TURNS * 2):]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    text_reply = RATE_LIMIT_REPEAT_REPLY if _rate_limited_once else RATE_LIMIT_FIRST_REPLY
                    _rate_limited_once = True
                    sent = await message.reply_text(text_reply)
                    _track_bot_message(sent.chat_id, sent.message_id)
                else:
                    log.exception("AI request failed")
            except Exception:
                log.exception("AI request failed")
        return

    urls = URL_RE.findall(text)
    if not urls:
        return

    for url in urls:
        await handle_url(update, url)


# Process one download at a time — running yt-dlp/ffmpeg in parallel on a
# 256MB machine multiplies peak memory use and risks an OOM kill.
DOWNLOAD_LOCK = asyncio.Semaphore(1)


async def handle_url(update: Update, url: str) -> None:
    async with DOWNLOAD_LOCK:
        await _download_and_send(update, url)


async def _download_and_send(update: Update, url: str) -> None:
    cached_file_id = VIDEO_CACHE.get(url)
    if cached_file_id:
        try:
            sent = await update.message.reply_video(video=cached_file_id, supports_streaming=True)
            _track_bot_message(sent.chat_id, sent.message_id)
            _record_stat(url, cache_hit=True, chat_id=sent.chat_id, chat_title=sent.chat.title)
            return
        except Exception:
            log.exception("Cached file_id for %s is no longer valid, re-downloading", url)
            VIDEO_CACHE.pop(url, None)
            _save_video_cache()

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
                sent = await update.message.reply_text(
                    f"Video is too large ({size // 1024 // 1024} MB) — Telegram allows 50 MB max."
                )
                _track_bot_message(sent.chat_id, sent.message_id)
                return

            title = info.get("title", "")
            with open(filepath, "rb") as f:
                msg = await update.message.reply_video(video=f, caption=title, supports_streaming=True)
            _track_bot_message(msg.chat_id, msg.message_id)

            if msg.video:
                _remember_video(url, msg.video.file_id)
            _record_stat(url, cache_hit=False, chat_id=msg.chat_id, chat_title=msg.chat.title)

        except yt_dlp.utils.DownloadError:
            pass  # URL wasn't a supported video — silently ignore
        except Exception:
            log.exception("Unexpected error for %s", url)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    total = STATS.get("total", 0)
    cache_hits = STATS.get("cache_hits", 0)
    by_platform = STATS.get("by_platform", {})

    lines = [
        f"📊 Videos sent: {total} (served from cache: {cache_hits})",
        f"Cached links: {len(VIDEO_CACHE)}/{MAX_CACHE_ENTRIES}",
        f"Member profiles: {len(USER_PROFILES)}",
    ]
    if by_platform:
        lines.append("")
        lines.append("By platform:")
        for platform, count in sorted(by_platform.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {platform}: {count}")

    await message.reply_text("\n".join(lines))


async def chatstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    by_chat = STATS.get("by_chat", {})
    if not by_chat:
        await message.reply_text("No per-chat stats yet.")
        return

    lines = ["📊 Per-chat breakdown:"]
    for chat_id, data in sorted(by_chat.items(), key=lambda kv: -kv[1]["total"]):
        title = data.get("title") or chat_id
        total = data.get("total", 0)
        cache_hits = data.get("cache_hits", 0)
        platforms = data.get("by_platform", {})
        top = ", ".join(
            f"{p}: {c}" for p, c in sorted(platforms.items(), key=lambda kv: -kv[1])
        )
        lines.append(f"\n{title} ({chat_id})")
        lines.append(f"  Videos sent: {total} (from cache: {cache_hits})")
        if top:
            lines.append(f"  {top}")

    await message.reply_text("\n".join(lines))


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    if not USER_PROFILES:
        await message.reply_text(
            f"No profiles yet — need {PROFILE_UPDATE_THRESHOLD}+ tracked messages per person first."
        )
        return

    lines = ["👥 What the bot has picked up on each member:"]
    for data in USER_PROFILES.values():
        lines.append(f"\n{data['name']}: {data['notes']}")

    await message.reply_text("\n".join(lines))


async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reaction = update.message_reaction
    if not reaction:
        return

    emojis = {r.emoji for r in reaction.new_reaction if hasattr(r, "emoji")}
    log.info(
        "Reaction update: chat_id=%s message_id=%s user_id=%s emojis=%s tracked=%s",
        reaction.chat.id,
        reaction.message_id,
        reaction.user.id if reaction.user else None,
        emojis,
        (reaction.chat.id, reaction.message_id) in BOT_MESSAGE_IDS,
    )

    if reaction.chat.id not in ALLOWED_CHAT_IDS:
        return

    if not reaction.user or reaction.user.id != ADMIN_USER_ID:
        return

    key = (reaction.chat.id, reaction.message_id)
    if key not in BOT_MESSAGE_IDS:
        return

    if DELETE_REACTION_EMOJI not in emojis:
        return

    try:
        await context.bot.delete_message(chat_id=reaction.chat.id, message_id=reaction.message_id)
        BOT_MESSAGE_IDS.discard(key)
    except Exception:
        log.exception("Failed to delete message %s in chat %s", reaction.message_id, reaction.chat.id)


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
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("chatstats", chatstats_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(MessageReactionHandler(on_reaction))
    log.info("Bot started, polling...")
    # message_reaction updates aren't included by default — request everything
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
