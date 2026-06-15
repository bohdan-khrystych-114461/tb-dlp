import asyncio
import logging
import random
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from tb_dlp import ai, bot_messages, chat_history, chats, config, downloader, profiles, replies, stats, webpage

log = logging.getLogger(__name__)


def _is_admin_dm(message) -> bool:
    return (
        message.chat.type == "private"
        and message.from_user is not None
        and message.from_user.id == config.ADMIN_USER_ID
    )


# Small chance the bot jumps in without being @mentioned — makes it feel like
# a real group member rather than a tool that only responds on command.
UNPROMPTED_CHANCE = 0.08        # base 8% per eligible message
UNPROMPTED_CHANCE_HOT = 0.14    # bumped to 14% when chat is actively flowing
UNPROMPTED_COOLDOWN = 120       # min seconds between unprompted replies per chat
CHAT_COLD_THRESHOLD = 30 * 60   # >30 min silence = cold, skip unprompted
CHAT_HOT_THRESHOLD = 3 * 60     # <3 min since last message = hot chat
_chat_last_unprompted: dict[int, float] = {}
_chat_last_activity: dict[int, float] = {}  # time of previous message per chat


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return

    log.info("Message from chat_id=%s chat_title=%r", message.chat_id, message.chat.title)

    if message.chat.title and chats.CHAT_NAMES.get(message.chat_id) != message.chat.title:
        chats.CHAT_NAMES[message.chat_id] = message.chat.title
        chats.save_chat_names()

    if message.chat_id not in chats.ALLOWED_CHAT_IDS:
        return

    text = message.text
    bot_username = context.bot.username
    user = message.from_user

    now = time.time()
    prev_activity = _chat_last_activity.get(message.chat_id, 0)
    _chat_last_activity[message.chat_id] = now

    if user and not user.is_bot:
        chat_history.append_to_chat_history(message.chat_id, user.full_name, text, is_bot=False)
        if config.GEMINI_API_KEY and ai.is_ai_enabled_for_chat(message.chat_id):
            profiles.USER_MESSAGE_BUFFERS.setdefault(user.id, []).append(text)
            profiles.save_message_buffers()
            asyncio.create_task(profiles.update_profile(user.id, user.full_name, user.username))
    elif user and user.is_bot and user.username and user.username.lower() == "ruzzkibot":
        # So the AI can react to/build on what its "best friend" says in the
        # chat — without this, RuzzkiBot's messages are invisible to
        # chat_context entirely and get completely ignored.
        chat_history.append_to_chat_history(message.chat_id, "RuzzkiBot", text, is_bot=False)

    # Reply to a message containing a URL + download trigger phrase → re-download
    if (
        user
        and message.reply_to_message
        and bot_username
        and f"@{bot_username}" in text
        and config.DOWNLOAD_TRIGGER_RE.search(text)
    ):
        src = message.reply_to_message.text or message.reply_to_message.caption or ""
        urls = config.URL_RE.findall(src)
        if urls:
            for url in urls:
                await downloader.handle_url(update, url, force=True)
            return

    if (
        config.GEMINI_API_KEY
        and ai.is_ai_enabled_for_chat(message.chat_id)
        and bot_username
        and user
        and not user.is_bot
        and f"@{bot_username}" in text
    ):
        prompt = (message.caption or text).replace(f"@{bot_username}", "").strip()
        page_context = ""
        for url in config.URL_RE.findall(prompt):
            if config.YOUTUBE_RE.search(url) or config.INSTAGRAM_RE.search(url) or config.TIKTOK_RE.search(url):
                continue
            summary = await webpage.fetch_page_summary(url)
            if summary:
                page_context = f"The message links to this page:\n{summary}"
                break
        await replies.reply_with_ai(message, prompt, user, trigger="mention", page_context=page_context)
        return

    if (
        config.GEMINI_API_KEY
        and ai.is_ai_enabled_for_chat(message.chat_id)
        and user
        and not user.is_bot
        and message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == context.bot.id
    ):
        await replies.reply_with_ai(message, message.caption or text, user, trigger="reply")
        return

    if (
        config.GEMINI_API_KEY
        and ai.is_ai_enabled_for_chat(message.chat_id)
        and user
        and not user.is_bot
        and len(text) >= 10
        and not text.startswith("/")
        and not config.URL_RE.search(text)  # don't interrupt URL downloads
        and now - prev_activity < CHAT_COLD_THRESHOLD  # skip if chat was silent for 30+ min
    ):
        last = _chat_last_unprompted.get(message.chat_id, 0)
        chat_is_hot = now - prev_activity < CHAT_HOT_THRESHOLD
        chance = UNPROMPTED_CHANCE_HOT if chat_is_hot else UNPROMPTED_CHANCE
        if now - last >= UNPROMPTED_COOLDOWN and random.random() < chance:
            _chat_last_unprompted[message.chat_id] = now
            await replies.reply_with_ai(message, text, user, uninvited=True, trigger="unprompted")
            return

    urls = config.URL_RE.findall(text)
    if not urls:
        return

    for url in urls:
        await downloader.handle_url(update, url)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    total = stats.STATS.get("total", 0)
    cache_hits = stats.STATS.get("cache_hits", 0)
    by_platform = stats.STATS.get("by_platform", {})

    lines = [
        f"📊 Videos sent: {total} (served from cache: {cache_hits})",
        f"Cached links: {len(stats.VIDEO_CACHE)}/{stats.MAX_CACHE_ENTRIES}",
        f"Member profiles: {len(profiles.USER_PROFILES)}",
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

    by_chat = stats.STATS.get("by_chat", {})
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


async def aistats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    s = stats.AI_STATS
    by_chat = s.get("by_chat", {})
    totals = {k: 0 for k in stats.AI_STAT_TRIGGERS}
    for data in by_chat.values():
        for k in stats.AI_STAT_TRIGGERS:
            totals[k] += data.get(k, 0)

    lines = [
        "🤖 AI chat activity:",
        f"  Mentions answered: {totals['mention']}",
        f"  Replies-to-bot answered: {totals['reply']}",
        f"  Unprompted chime-ins: {totals['unprompted']}",
        f"  Profile summaries generated: {s.get('profile_update', 0)}",
        f"  Rate-limited (all models exhausted): {totals['rate_limited']}",
    ]

    if by_chat:
        lines.append("")
        lines.append("By chat:")
        for chat_id, data in sorted(by_chat.items(), key=lambda kv: -sum(kv[1].get(k, 0) for k in stats.AI_STAT_TRIGGERS)):
            title = data.get("title") or chat_id
            lines.append(
                f"  {title}: mentions {data.get('mention', 0)}, replies {data.get('reply', 0)}, "
                f"unprompted {data.get('unprompted', 0)}, rate-limited {data.get('rate_limited', 0)}"
            )

    await message.reply_text("\n".join(lines))


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    if not config.ADMIN_TOKEN:
        await message.reply_text("ADMIN_TOKEN secret is not set.")
        return

    url = f"{config.DASHBOARD_BASE_URL}/admin?token={config.ADMIN_TOKEN}"
    await message.reply_text(
        "🔧 Admin dashboard",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open dashboard", url=url)]]),
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not _is_admin_dm(message):
        return

    if not profiles.USER_PROFILES:
        await message.reply_text(
            f"No profiles yet — need {profiles.PROFILE_UPDATE_THRESHOLD}+ tracked messages per person first."
        )
        return

    query = " ".join(context.args).strip() if context.args else ""
    if query:
        match = profiles.find_profile(query)
        if not match:
            await message.reply_text(f"No profile found for '{query}'.")
            return
        user_id, data = match
        buf_count = len(profiles.USER_MESSAGE_BUFFERS.get(int(user_id), []))
        handle = f" (@{data['username']})" if data.get("username") else ""
        await message.reply_text(
            f"{data['name']}{handle}\n\nNotes: {data['notes']}\n\nBuffer: {buf_count}/{profiles.PROFILE_UPDATE_THRESHOLD} messages until next refresh"
        )
        return

    lines = ["👥 What the bot has picked up on each member:"]
    for data in profiles.USER_PROFILES.values():
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

    match = profiles.find_profile(query)
    if not match:
        await message.reply_text(f"No profile found for '{query}'.")
        return

    user_id, data = match
    data["notes"] = new_notes
    profiles.USER_PROFILES[user_id] = data
    profiles.save_profiles()
    await message.reply_text(f"Updated notes for {data['name']}.")


# NOTE: Telegram only delivers message_reaction updates to bots that are
# administrators of the chat — this silently never fires otherwise. The bot
# is currently a regular member in our groups, so this is dormant until
# someone promotes it to admin.
async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reaction = update.message_reaction
    if not reaction or reaction.chat.id not in chats.ALLOWED_CHAT_IDS:
        return

    if not reaction.user or reaction.user.id != config.ADMIN_USER_ID:
        return

    key = (reaction.chat.id, reaction.message_id)
    if key not in bot_messages.BOT_MESSAGE_IDS:
        return

    emojis = {r.emoji for r in reaction.new_reaction if hasattr(r, "emoji")}
    if bot_messages.DELETE_REACTION_EMOJI not in emojis:
        return

    try:
        await context.bot.delete_message(chat_id=reaction.chat.id, message_id=reaction.message_id)
        bot_messages.BOT_MESSAGE_IDS.discard(key)
    except Exception:
        log.exception("Failed to delete message %s in chat %s", reaction.message_id, reaction.chat.id)
