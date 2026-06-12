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


def save_video_cache() -> None:
    _video_cache_store.save(VIDEO_CACHE)


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
