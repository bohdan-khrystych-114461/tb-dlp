from urllib.parse import urlparse

from tb_dlp.storage import JSONStore

# Telegram keeps uploaded videos on its own servers — resending by file_id
# is instant and needs no re-download/re-upload. Cache URL -> file_id so the
# same link posted again (or forwarded later) doesn't cost a fresh download.
MAX_CACHE_ENTRIES = 500

_video_cache_store = JSONStore("/cookies/video_cache.json", default=dict)
VIDEO_CACHE: dict[str, str] = _video_cache_store.load()

_stats_store = JSONStore(
    "/cookies/stats.json",
    default=lambda: {"total": 0, "cache_hits": 0, "by_platform": {}},
)
STATS: dict = _stats_store.load()

# Counts of AI chat activity by trigger — separate from download STATS above
# so /aistats and the dashboard can show how the bot is actually behaving in
# chat (how often it chimes in unprompted, how often it's quota-limited per
# chat, etc.) without grepping logs. profile_update is global (not tied to a
# single chat — a user's message buffer can span multiple chats).
AI_STAT_TRIGGERS = ("mention", "reply", "unprompted", "rate_limited")

_ai_stats_store = JSONStore(
    "/cookies/ai_stats.json",
    default=lambda: {"profile_update": 0, "by_chat": {}},
)
AI_STATS: dict = _ai_stats_store.load()


def save_video_cache() -> None:
    _video_cache_store.save(VIDEO_CACHE)


def save_ai_stats() -> None:
    _ai_stats_store.save(AI_STATS)


def _ai_chat_stats(chat_id: int, chat_title: str | None) -> dict:
    by_chat = AI_STATS.setdefault("by_chat", {})
    chat_stats = by_chat.setdefault(str(chat_id), {"title": chat_title, **{k: 0 for k in AI_STAT_TRIGGERS}})
    chat_stats["title"] = chat_title  # keep the latest title (groups get renamed)
    return chat_stats


def record_profile_update() -> None:
    AI_STATS["profile_update"] = AI_STATS.get("profile_update", 0) + 1
    save_ai_stats()


def record_ai_reply(trigger: str, chat_id: int, chat_title: str | None) -> None:
    chat_stats = _ai_chat_stats(chat_id, chat_title)
    chat_stats[trigger] = chat_stats.get(trigger, 0) + 1
    save_ai_stats()


def record_ai_rate_limit(chat_id: int, chat_title: str | None) -> None:
    chat_stats = _ai_chat_stats(chat_id, chat_title)
    chat_stats["rate_limited"] = chat_stats.get("rate_limited", 0) + 1
    save_ai_stats()


def remember_video(url: str, file_id: str) -> None:
    # Dicts keep insertion order — drop the oldest entries first (FIFO) so the
    # cache file doesn't grow without bound.
    VIDEO_CACHE[url] = file_id
    while len(VIDEO_CACHE) > MAX_CACHE_ENTRIES:
        VIDEO_CACHE.pop(next(iter(VIDEO_CACHE)))
    save_video_cache()


def save_stats() -> None:
    _stats_store.save(STATS)


def platform_from_url(url: str) -> str:
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


def record_stat(url: str, *, cache_hit: bool, chat_id: int, chat_title: str | None) -> None:
    platform = platform_from_url(url)

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

    save_stats()
