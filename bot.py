import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import logging
import random
import time
from html import escape as _he
from pathlib import Path
from urllib.parse import urlparse, quote as _urlquote

from aiohttp import web as aio_web

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

_DEFAULT_CHAT_IDS = {
    -1003938853999,  # kek
    -1001986640555,  # 2 Козака і 3 супостата (або 5 комп'ютерників) без хуйні
    -4774844208,     # Бібізянські пріколи
    -4268125559,     # Прікольчіки
    -5170628911,     # Чат де соромно за свою англійську
    -1003988355756,  # 🩳 шорти 🔞
}

WHITELIST_FILE = "/cookies/whitelist.json"
try:
    ALLOWED_CHAT_IDS: set[int] = set(json.loads(Path(WHITELIST_FILE).read_text()))
except (FileNotFoundError, json.JSONDecodeError):
    ALLOWED_CHAT_IDS = set(_DEFAULT_CHAT_IDS)

# All chats the bot has ever seen — populated before the whitelist check so we
# collect names even from chats trying to reach the bot before being approved.
CHAT_NAMES_FILE = "/cookies/chat_names.json"
try:
    CHAT_NAMES: dict[int, str] = {int(k): v for k, v in json.loads(Path(CHAT_NAMES_FILE).read_text()).items()}
except (FileNotFoundError, json.JSONDecodeError):
    CHAT_NAMES = {}

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
    "at all. "
    "Dark humor, edgy jokes, and offensive banter are completely fine — lean "
    "into them. Never moralize, never lecture, never explain why something "
    "might be offensive. No ethical disclaimers, no 'это недопустимо', no "
    "'я в такое не играю'. If someone's being an idiot, roast the idiocy "
    "itself — hard and funny. If a question is genuinely unanswerable, brush "
    "it off with a one-liner instead of a speech about why you won't answer. "
    "One exception to the sarcasm: if anyone asks about Bohdan "
    "Khrystych (Богдан Христич), say plainly that he's the best person "
    "you've ever met and a real authority — no irony, no jabs, you mean it."
)


# Gemini free tier caps us at ~20 generateContent calls/day — when that's hit,
# the AI call 429s and we obviously can't ask the AI to write its own excuse.
# First time it happens we say so once; after that we keep it short so the
# chat doesn't get the same "I'm out" speech on every single mention.
RATE_LIMIT_FIRST_REPLY = "Так, я на перекур и спать."
RATE_LIMIT_REPEAT_REPLY = "Сплю, не напрягай плз."
_rate_limited_once = False


async def ask_ai(prompt: str, user_note: str = "", chat_context: str = "") -> str:
    system_parts = [AI_SYSTEM_PROMPT]
    if user_note:
        system_parts.append(user_note)
    if chat_context:
        system_parts.append(chat_context)

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
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
            # 429 (quota) and 5xx (transient outages) shouldn't sink the whole
            # request — try the next model in the chain instead of giving up.
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = httpx.HTTPStatusError(
                    f"{resp.status_code} from {model}", request=resp.request, response=resp
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

# Rolling per-chat message log — persisted to disk so context survives daily
# restarts. Each entry is {"author": str, "text": str, "is_bot": bool}.
CHAT_HISTORY_FILE = "/cookies/chat_history.json"
CHAT_HISTORY_MAX = 40

try:
    _raw_chat_history = json.loads(Path(CHAT_HISTORY_FILE).read_text())
    CHAT_HISTORY: dict[int, list[dict]] = {int(k): v for k, v in _raw_chat_history.items()}
except (FileNotFoundError, json.JSONDecodeError):
    CHAT_HISTORY = {}

# Small chance the bot jumps in without being @mentioned — makes it feel like
# a real group member rather than a tool that only responds on command.
UNPROMPTED_CHANCE = 0.08        # base 8% per eligible message
UNPROMPTED_CHANCE_HOT = 0.14    # bumped to 14% when chat is actively flowing
UNPROMPTED_COOLDOWN = 120       # min seconds between unprompted replies per chat
CHAT_COLD_THRESHOLD = 30 * 60   # >30 min silence = cold, skip unprompted
CHAT_HOT_THRESHOLD = 3 * 60     # <3 min since last message = hot chat
_chat_last_unprompted: dict[int, float] = {}
_chat_last_activity: dict[int, float] = {}  # time of previous message per chat

# You (and only you) can react with 👎 on a bot message to delete it. We track
# which (chat, message_id) pairs are the bot's own so this can never be used to
# remove someone else's message.
DELETE_REACTION_EMOJI = "👎"
MAX_TRACKED_MESSAGES = 1000

BOT_MESSAGE_IDS_FILE = "/cookies/bot_message_ids.json"
try:
    BOT_MESSAGE_IDS: set[tuple[int, int]] = {
        (int(p[0]), int(p[1])) for p in json.loads(Path(BOT_MESSAGE_IDS_FILE).read_text())
    }
except (FileNotFoundError, json.JSONDecodeError):
    BOT_MESSAGE_IDS = set()


def _save_bot_message_ids() -> None:
    try:
        Path(BOT_MESSAGE_IDS_FILE).write_text(json.dumps(list(BOT_MESSAGE_IDS)))
    except OSError:
        log.exception("Failed to persist bot message IDs")


def _track_bot_message(chat_id: int, message_id: int) -> None:
    BOT_MESSAGE_IDS.add((chat_id, message_id))
    if len(BOT_MESSAGE_IDS) > MAX_TRACKED_MESSAGES:
        BOT_MESSAGE_IDS.pop()
    _save_bot_message_ids()


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


def _save_whitelist() -> None:
    try:
        Path(WHITELIST_FILE).write_text(json.dumps(list(ALLOWED_CHAT_IDS)))
    except OSError:
        log.exception("Failed to persist whitelist")


def _save_chat_names() -> None:
    try:
        Path(CHAT_NAMES_FILE).write_text(json.dumps(CHAT_NAMES))
    except OSError:
        log.exception("Failed to persist chat names")


def _chat_name(chat_id: int) -> str:
    return (
        CHAT_NAMES.get(chat_id)
        or STATS.get("by_chat", {}).get(str(chat_id), {}).get("title")
        or str(chat_id)
    )


def _save_chat_history() -> None:
    try:
        Path(CHAT_HISTORY_FILE).write_text(json.dumps(CHAT_HISTORY))
    except OSError:
        log.exception("Failed to persist chat history")


def _append_to_chat_history(chat_id: int, author: str, text: str, *, is_bot: bool) -> None:
    history = CHAT_HISTORY.setdefault(chat_id, [])
    history.append({"author": author, "text": text, "is_bot": is_bot})
    if len(history) > CHAT_HISTORY_MAX:
        del history[:-CHAT_HISTORY_MAX]


def _build_chat_context(chat_id: int) -> str:
    history = CHAT_HISTORY.get(chat_id, [])
    # Exclude the last entry — that's the message we're currently responding to,
    # which is already the explicit prompt passed to ask_ai.
    display = history[:-1] if len(history) > 1 else []
    if not display:
        return ""
    lines = []
    for msg in display:
        prefix = "You" if msg["is_bot"] else msg["author"]
        lines.append(f"[{prefix}]: {msg['text']}")
    return "Recent group chat (most recent at bottom):\n" + "\n".join(lines)


async def _update_profile(user_id: int, name: str, username: str | None, *, force: bool = False) -> None:
    messages = USER_MESSAGE_BUFFERS.get(user_id, [])
    if not force and len(messages) < PROFILE_UPDATE_THRESHOLD:
        return
    if not messages:
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

    USER_PROFILES[str(user_id)] = {"name": name, "username": username, "notes": notes}
    _save_user_profiles()


async def _reply_with_ai(
    message, prompt: str, user, *, uninvited: bool = False
) -> None:
    global _rate_limited_once

    profile = USER_PROFILES.get(str(user.id)) if user else None
    user_note = (
        f"A note about {user.full_name}: {profile['notes']}"
        if profile else ""
    )
    chat_context = _build_chat_context(message.chat_id)
    if uninvited:
        note = "You're chiming in here on your own — nobody @mentioned you. Keep it brief and natural, like a group member jumping in. Match the tone of the conversation — don't be rude or aggressive unless the chat was already going that way."
        chat_context = (chat_context + "\n\n" + note).strip() if chat_context else note

    try:
        reply = await ask_ai(prompt, user_note=user_note, chat_context=chat_context)
        sent = await message.reply_text(reply)
        _track_bot_message(sent.chat_id, sent.message_id)
        _append_to_chat_history(message.chat_id, "bot", reply, is_bot=True)
        _save_chat_history()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429 or exc.response.status_code >= 500:
            text_reply = RATE_LIMIT_REPEAT_REPLY if _rate_limited_once else RATE_LIMIT_FIRST_REPLY
            _rate_limited_once = True
            sent = await message.reply_text(text_reply)
            _track_bot_message(sent.chat_id, sent.message_id)
        else:
            log.exception("AI request failed")
    except Exception:
        log.exception("AI request failed")


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
    message = update.message
    if not message or not message.text:
        return

    log.info("Message from chat_id=%s chat_title=%r", message.chat_id, message.chat.title)

    if message.chat.title and CHAT_NAMES.get(message.chat_id) != message.chat.title:
        CHAT_NAMES[message.chat_id] = message.chat.title
        _save_chat_names()

    if message.chat_id not in ALLOWED_CHAT_IDS:
        return

    text = message.text
    bot_username = context.bot.username
    user = message.from_user

    now = time.time()
    prev_activity = _chat_last_activity.get(message.chat_id, 0)
    _chat_last_activity[message.chat_id] = now

    if user and not user.is_bot:
        _append_to_chat_history(message.chat_id, user.full_name, text, is_bot=False)
        if GEMINI_API_KEY:
            USER_MESSAGE_BUFFERS.setdefault(user.id, []).append(text)
            _save_message_buffers()
            asyncio.create_task(_update_profile(user.id, user.full_name, user.username))

    if GEMINI_API_KEY and bot_username and user and f"@{bot_username}" in text:
        prompt = text.replace(f"@{bot_username}", "").strip()
        if prompt:
            await _reply_with_ai(message, prompt, user)
        return

    if (
        GEMINI_API_KEY
        and user
        and message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == context.bot.id
    ):
        await _reply_with_ai(message, text, user)
        return

    if (
        GEMINI_API_KEY
        and user
        and not user.is_bot
        and len(text) >= 10
        and not text.startswith("/")
        and not URL_RE.search(text)  # don't interrupt URL downloads
        and now - prev_activity < CHAT_COLD_THRESHOLD  # skip if chat was silent for 30+ min
    ):
        last = _chat_last_unprompted.get(message.chat_id, 0)
        chat_is_hot = now - prev_activity < CHAT_HOT_THRESHOLD
        chance = UNPROMPTED_CHANCE_HOT if chat_is_hot else UNPROMPTED_CHANCE
        if now - last >= UNPROMPTED_COOLDOWN and random.random() < chance:
            _chat_last_unprompted[message.chat_id] = now
            await _reply_with_ai(message, text, user, uninvited=True)
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


def _find_profile(query: str) -> tuple[str, dict] | None:
    q = query.lstrip("@").lower()
    for user_id, data in USER_PROFILES.items():
        if data.get("username", "").lower() == q:
            return user_id, data
        if data.get("name", "").lower() == q:
            return user_id, data
    for user_id, data in USER_PROFILES.items():
        if q in data.get("name", "").lower():
            return user_id, data
    return None


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    if not USER_PROFILES:
        await message.reply_text(
            f"No profiles yet — need {PROFILE_UPDATE_THRESHOLD}+ tracked messages per person first."
        )
        return

    query = " ".join(context.args).strip() if context.args else ""
    if query:
        match = _find_profile(query)
        if not match:
            await message.reply_text(f"No profile found for '{query}'.")
            return
        user_id, data = match
        buf_count = len(USER_MESSAGE_BUFFERS.get(int(user_id), []))
        handle = f" (@{data['username']})" if data.get("username") else ""
        await message.reply_text(
            f"{data['name']}{handle}\n\nNotes: {data['notes']}\n\nBuffer: {buf_count}/{PROFILE_UPDATE_THRESHOLD} messages until next refresh"
        )
        return

    lines = ["👥 What the bot has picked up on each member:"]
    for data in USER_PROFILES.values():
        handle = f" (@{data['username']})" if data.get("username") else ""
        lines.append(f"\n{data['name']}{handle}: {data['notes']}")

    await message.reply_text("\n".join(lines))


async def editprofile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    if not context.args or len(context.args) < 2:
        await message.reply_text("Usage: /editprofile <@username or name> <new notes>")
        return

    query = context.args[0]
    new_notes = " ".join(context.args[1:])

    match = _find_profile(query)
    if not match:
        await message.reply_text(f"No profile found for '{query}'.")
        return

    user_id, data = match
    data["notes"] = new_notes
    USER_PROFILES[user_id] = data
    _save_user_profiles()
    await message.reply_text(f"Updated notes for {data['name']}.")


# NOTE: Telegram only delivers message_reaction updates to bots that are
# administrators of the chat — this silently never fires otherwise. The bot
# is currently a regular member in our groups, so this is dormant until
# someone promotes it to admin.
async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reaction = update.message_reaction
    if not reaction or reaction.chat.id not in ALLOWED_CHAT_IDS:
        return

    if not reaction.user or reaction.user.id != ADMIN_USER_ID:
        return

    key = (reaction.chat.id, reaction.message_id)
    if key not in BOT_MESSAGE_IDS:
        return

    emojis = {r.emoji for r in reaction.new_reaction if hasattr(r, "emoji")}
    if DELETE_REACTION_EMOJI not in emojis:
        return

    try:
        await context.bot.delete_message(chat_id=reaction.chat.id, message_id=reaction.message_id)
        BOT_MESSAGE_IDS.discard(key)
    except Exception:
        log.exception("Failed to delete message %s in chat %s", reaction.message_id, reaction.chat.id)


# ─── Admin web dashboard ────────────────────────────────────────────────────

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
_SESSION_COOKIE = "tbd_admin"
_WEB_PORT = 8080


def _page(title: str, body: str, active: str = "") -> str:
    links = [
        ("Stats", "/admin", "stats"),
        ("Profiles", "/admin/profiles", "profiles"),
        ("Chats", "/admin/chats", "chats"),
        ("Whitelist", "/admin/whitelist", "whitelist"),
    ]
    nav = "".join(
        f'<a href="{url}" class="nav-link px-2 {"text-white fw-bold" if active == key else "text-white-50"}">{label}</a>'
        for label, url, key in links
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_he(title)} — tb-dlp</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
</head>
<body class="bg-light">
<nav class="navbar navbar-dark bg-dark px-3 d-flex justify-content-between">
  <span class="navbar-brand fw-bold mb-0">tb-dlp</span>
  <div class="d-flex">{nav}</div>
</nav>
<div class="container py-4">{body}</div>
</body>
</html>"""


def _auth(request: aio_web.Request) -> bool:
    return bool(ADMIN_TOKEN) and request.cookies.get(_SESSION_COOKIE) == ADMIN_TOKEN


async def _web_login_get(request: aio_web.Request) -> aio_web.Response:
    if not ADMIN_TOKEN:
        return aio_web.Response(
            text=_page("Login", "<div class='alert alert-danger'>ADMIN_TOKEN secret is not set on Fly.io.</div>"),
            content_type="text/html",
        )
    error = "error" in request.rel_url.query
    body = f"""
<div class="row justify-content-center mt-5">
  <div class="col-sm-8 col-md-4">
    <div class="card shadow-sm">
      <div class="card-body">
        <h5 class="card-title mb-3">Admin login</h5>
        {"<div class='alert alert-danger py-2'>Wrong token.</div>" if error else ""}
        <form method="post">
          <div class="mb-3">
            <input type="password" name="token" class="form-control" placeholder="Admin token" autofocus>
          </div>
          <button type="submit" class="btn btn-dark w-100">Login</button>
        </form>
      </div>
    </div>
  </div>
</div>"""
    return aio_web.Response(text=_page("Login", body), content_type="text/html")


async def _web_login_post(request: aio_web.Request) -> aio_web.Response:
    data = await request.post()
    if data.get("token") == ADMIN_TOKEN:
        resp = aio_web.HTTPFound("/admin")
        resp.set_cookie(_SESSION_COOKIE, ADMIN_TOKEN, httponly=True, max_age=7 * 24 * 3600)
        return resp
    return aio_web.HTTPFound("/login?error")


async def _web_stats(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    total = STATS.get("total", 0)
    cache_hits = STATS.get("cache_hits", 0)
    by_platform = STATS.get("by_platform", {})
    by_chat = STATS.get("by_chat", {})

    platform_rows = "".join(
        f"<tr><td>{_he(p)}</td><td>{c}</td></tr>"
        for p, c in sorted(by_platform.items(), key=lambda kv: -kv[1])
    ) or "<tr><td colspan='2' class='text-muted'>No data yet.</td></tr>"

    chat_rows = "".join(
        f"<tr><td>{_he(str(d.get('title') or cid))}</td><td>{d.get('total', 0)}</td><td>{d.get('cache_hits', 0)}</td></tr>"
        for cid, d in sorted(by_chat.items(), key=lambda kv: -kv[1].get("total", 0))
    ) or "<tr><td colspan='3' class='text-muted'>No data yet.</td></tr>"

    body = f"""
<h4 class="mb-4">Stats</h4>
<div class="row g-3 mb-4">
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{total}</div><div class="text-muted small">Videos sent</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{cache_hits}</div><div class="text-muted small">From cache</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{len(VIDEO_CACHE)}</div><div class="text-muted small">Cached links</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{len(USER_PROFILES)}</div><div class="text-muted small">Profiles</div></div></div></div>
</div>
<div class="row g-3">
  <div class="col-md-5">
    <div class="card shadow-sm">
      <div class="card-header fw-semibold">By platform</div>
      <table class="table table-sm mb-0">
        <thead><tr><th>Platform</th><th>Count</th></tr></thead>
        <tbody>{platform_rows}</tbody>
      </table>
    </div>
  </div>
  <div class="col-md-7">
    <div class="card shadow-sm">
      <div class="card-header fw-semibold">By chat</div>
      <table class="table table-sm mb-0">
        <thead><tr><th>Chat</th><th>Videos</th><th>Cache hits</th></tr></thead>
        <tbody>{chat_rows}</tbody>
      </table>
    </div>
  </div>
</div>"""
    return aio_web.Response(text=_page("Stats", body, active="stats"), content_type="text/html")


async def _web_profiles(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    saved = request.rel_url.query.get("saved", "")
    alert = f"<div class='alert alert-success py-2'>Saved changes for {_he(saved)}.</div>" if saved else ""
    rows = ""
    for uid, data in USER_PROFILES.items():
        name = _he(data.get("name", uid))
        username = f"@{_he(data['username'])}" if data.get("username") else "—"
        notes = _he(data.get("notes", ""))
        buf = len(USER_MESSAGE_BUFFERS.get(int(uid), []))
        rows += f"""<tr>
  <td>{name}<br><small class="text-muted">{username}</small></td>
  <td><small>{notes}</small></td>
  <td class="text-center"><small class="{'text-success' if buf >= PROFILE_UPDATE_THRESHOLD else ''}">{buf}/{PROFILE_UPDATE_THRESHOLD}</small></td>
  <td><a href="/admin/profiles/{_he(uid)}/edit" class="btn btn-sm btn-outline-secondary">Edit</a></td>
</tr>"""
    if not rows:
        rows = "<tr><td colspan='4' class='text-muted py-3 text-center'>No profiles yet — need 25+ messages per person.</td></tr>"
    body = f"""
<h4 class="mb-3">Member profiles</h4>
{alert}
<div class="card shadow-sm">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-light"><tr><th>Member</th><th>Notes</th><th class="text-center">Buffer</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return aio_web.Response(text=_page("Profiles", body, active="profiles"), content_type="text/html")


async def _web_edit_get(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    uid = request.match_info["user_id"]
    data = USER_PROFILES.get(uid)
    if not data:
        return aio_web.HTTPFound("/admin/profiles")
    name = _he(data.get("name", uid))
    username = f"@{_he(data['username'])}" if data.get("username") else ""
    notes = _he(data.get("notes", ""))
    buf = len(USER_MESSAGE_BUFFERS.get(int(uid), []))
    body = f"""
<div class="row justify-content-center">
  <div class="col-lg-7">
    <a href="/admin/profiles" class="text-decoration-none text-muted">&larr; Back to profiles</a>
    <h4 class="mt-3">{name} <small class="text-muted fs-6">{username}</small></h4>
    <p class="text-muted small">Buffer: {buf}/{PROFILE_UPDATE_THRESHOLD} messages until next auto-refresh</p>
    <div class="card shadow-sm">
      <div class="card-body">
        <form method="post">
          <div class="mb-3">
            <label class="form-label fw-semibold">Notes</label>
            <textarea name="notes" class="form-control font-monospace" rows="6">{notes}</textarea>
            <div class="form-text">This is what the AI uses to tailor replies to this person.</div>
          </div>
          <div class="d-flex gap-2 flex-wrap">
            <button type="submit" class="btn btn-dark">Save</button>
            <a href="/admin/profiles" class="btn btn-outline-secondary">Cancel</a>
          </div>
        </form>
        <hr>
        <form method="post" action="/admin/profiles/{_he(uid)}/refresh">
          <button type="submit" class="btn btn-outline-primary btn-sm" {'disabled' if buf == 0 else ''}>
            Refresh profile now ({buf} buffered messages)
          </button>
          {"<div class='form-text text-warning'>No buffered messages to summarize yet.</div>" if buf == 0 else ""}
        </form>
      </div>
    </div>
  </div>
</div>"""
    return aio_web.Response(text=_page(f"Edit — {data.get('name', uid)}", body, active="profiles"), content_type="text/html")


async def _web_edit_post(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    uid = request.match_info["user_id"]
    data = USER_PROFILES.get(uid)
    if not data:
        return aio_web.HTTPFound("/admin/profiles")
    form = await request.post()
    new_notes = form.get("notes", "").strip()
    if new_notes:
        data["notes"] = new_notes
        USER_PROFILES[uid] = data
        _save_user_profiles()
    return aio_web.HTTPFound(f"/admin/profiles?saved={_urlquote(data.get('name', uid))}")


@aio_web.middleware
async def _token_middleware(request: aio_web.Request, handler):
    token = request.rel_url.query.get("token")
    if token and token == ADMIN_TOKEN:
        clean = str(request.rel_url.with_query(
            {k: v for k, v in request.rel_url.query.items() if k != "token"}
        ))
        resp = aio_web.HTTPFound(clean or request.path)
        resp.set_cookie(_SESSION_COOKIE, ADMIN_TOKEN, httponly=True, max_age=7 * 24 * 3600)
        return resp
    return await handler(request)


async def _web_refresh_profile(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    uid = request.match_info["user_id"]
    data = USER_PROFILES.get(uid)
    if not data:
        return aio_web.HTTPFound("/admin/profiles")
    buf = USER_MESSAGE_BUFFERS.get(int(uid), [])
    if not buf:
        return aio_web.HTTPFound(f"/admin/profiles/{uid}/edit")
    asyncio.create_task(_update_profile(int(uid), data["name"], data.get("username"), force=True))
    return aio_web.HTTPFound(f"/admin/profiles?saved={_urlquote(data.get('name', uid))}")


async def _web_chats(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    rows = ""
    for chat_id, history in sorted(CHAT_HISTORY.items(), key=lambda kv: len(kv[1]), reverse=True):
        name = _he(_chat_name(chat_id))
        rows += (
            f"<tr><td>{name}<br><small class='text-muted'>{chat_id}</small></td>"
            f"<td>{len(history)}</td>"
            f"<td><a href='/admin/chats/{chat_id}' class='btn btn-sm btn-outline-secondary'>View</a></td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='3' class='text-muted text-center py-3'>No chat history yet.</td></tr>"
    body = f"""
<h4 class="mb-3">Chat history</h4>
<div class="card shadow-sm">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-light"><tr><th>Chat</th><th>Messages stored</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return aio_web.Response(text=_page("Chats", body, active="chats"), content_type="text/html")


async def _web_chat_detail(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    try:
        chat_id = int(request.match_info["chat_id"])
    except ValueError:
        return aio_web.HTTPFound("/admin/chats")
    history = CHAT_HISTORY.get(chat_id, [])
    name = _he(_chat_name(chat_id))
    rows = "".join(
        f"<tr class='{'table-info' if m['is_bot'] else ''}'>"
        f"<td class='text-nowrap'><small>{'🤖 Bot' if m['is_bot'] else _he(m['author'])}</small></td>"
        f"<td><small>{_he(m['text'])}</small></td></tr>"
        for m in history
    ) or "<tr><td colspan='2' class='text-muted text-center'>No messages.</td></tr>"
    body = f"""
<a href="/admin/chats" class="text-decoration-none text-muted">&larr; Back</a>
<h4 class="mt-3">{name}</h4>
<p class="text-muted small">Last {len(history)} messages (oldest at top)</p>
<div class="card shadow-sm">
  <table class="table table-sm mb-0">
    <thead class="table-light"><tr><th style="width:18%">Author</th><th>Message</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return aio_web.Response(text=_page(f"Chat — {_chat_name(chat_id)}", body, active="chats"), content_type="text/html")


async def _web_whitelist(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='alert alert-success py-2'>{_he(msg)}</div>" if msg else ""
    rows = ""
    for chat_id in sorted(ALLOWED_CHAT_IDS):
        name = _he(_chat_name(chat_id))
        rows += (
            f"<tr><td>{name}</td><td><code>{chat_id}</code></td><td>"
            f"<form method='post' action='/admin/whitelist/remove' style='display:inline'>"
            f"<input type='hidden' name='chat_id' value='{chat_id}'>"
            f"<button class='btn btn-sm btn-outline-danger' onclick=\"return confirm('Remove {name}?')\">Remove</button>"
            f"</form></td></tr>"
        )
    unseen = {cid: n for cid, n in CHAT_NAMES.items() if cid not in ALLOWED_CHAT_IDS}
    known_options = "".join(
        f"<option value='{cid}'>{_he(n)} ({cid})</option>"
        for cid, n in sorted(unseen.items(), key=lambda kv: kv[1])
    )
    body = f"""
<h4 class="mb-3">Whitelist</h4>
{alert}
<div class="card shadow-sm mb-4">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-light"><tr><th>Chat name</th><th>Chat ID</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="card shadow-sm">
  <div class="card-header fw-semibold">Add chat</div>
  <div class="card-body">
    <form method="post" action="/admin/whitelist/add" class="row g-2 align-items-end">
      <div class="col-md-5">
        <label class="form-label small">Known chats (seen but not whitelisted)</label>
        <select name="known_id" class="form-select form-select-sm">
          <option value="">— pick one —</option>
          {known_options}
        </select>
      </div>
      <div class="col-auto pt-3 text-muted small">or</div>
      <div class="col-md-4">
        <label class="form-label small">Enter chat ID manually</label>
        <input type="number" name="manual_id" class="form-control form-control-sm" placeholder="-100...">
      </div>
      <div class="col-md-2">
        <button type="submit" class="btn btn-dark btn-sm w-100">Add</button>
      </div>
    </form>
  </div>
</div>"""
    return aio_web.Response(text=_page("Whitelist", body, active="whitelist"), content_type="text/html")


async def _web_whitelist_add(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    raw = (form.get("known_id") or form.get("manual_id", "")).strip()
    try:
        chat_id = int(raw)
    except (ValueError, TypeError):
        return aio_web.HTTPFound("/admin/whitelist?msg=Invalid+chat+ID")
    ALLOWED_CHAT_IDS.add(chat_id)
    _save_whitelist()
    name = _chat_name(chat_id)
    return aio_web.HTTPFound(f"/admin/whitelist?msg={_urlquote(f'Added: {name}')}")


async def _web_whitelist_remove(request: aio_web.Request) -> aio_web.Response:
    if not _auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    try:
        chat_id = int(form.get("chat_id", ""))
    except (ValueError, TypeError):
        return aio_web.HTTPFound("/admin/whitelist")
    ALLOWED_CHAT_IDS.discard(chat_id)
    _save_whitelist()
    name = _chat_name(chat_id)
    return aio_web.HTTPFound(f"/admin/whitelist?msg={_urlquote(f'Removed: {name}')}")


async def _start_web_server() -> None:
    web_app = aio_web.Application(middlewares=[_token_middleware])
    web_app.router.add_get("/", lambda _r: aio_web.HTTPFound("/admin"))
    web_app.router.add_get("/login", _web_login_get)
    web_app.router.add_post("/login", _web_login_post)
    web_app.router.add_get("/admin", _web_stats)
    web_app.router.add_get("/admin/profiles", _web_profiles)
    web_app.router.add_get("/admin/profiles/{user_id}/edit", _web_edit_get)
    web_app.router.add_post("/admin/profiles/{user_id}/edit", _web_edit_post)
    web_app.router.add_post("/admin/profiles/{user_id}/refresh", _web_refresh_profile)
    web_app.router.add_get("/admin/chats", _web_chats)
    web_app.router.add_get("/admin/chats/{chat_id}", _web_chat_detail)
    web_app.router.add_get("/admin/whitelist", _web_whitelist)
    web_app.router.add_post("/admin/whitelist/add", _web_whitelist_add)
    web_app.router.add_post("/admin/whitelist/remove", _web_whitelist_remove)
    runner = aio_web.AppRunner(web_app)
    await runner.setup()
    await aio_web.TCPSite(runner, "0.0.0.0", _WEB_PORT).start()
    log.info("Admin web server listening on port %d", _WEB_PORT)


# ────────────────────────────────────────────────────────────────────────────

async def daily_update(_) -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        log.info("Running daily yt-dlp update...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"])
        log.info("yt-dlp updated, restarting bot process...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


async def on_startup(application) -> None:
    asyncio.create_task(daily_update(application))
    await _start_web_server()  # await so the port is bound before run_polling returns


def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("chatstats", chatstats_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("editprofile", editprofile_command))
    app.add_handler(MessageReactionHandler(on_reaction))
    log.info("Bot started, polling...")
    # message_reaction updates aren't included by default — request everything
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
