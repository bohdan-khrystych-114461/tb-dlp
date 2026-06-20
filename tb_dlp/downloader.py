import asyncio
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path

import httpx
import yt_dlp
from telegram import InputMediaPhoto, Update

from tb_dlp import bot_messages, config, stats

log = logging.getLogger(__name__)

COOKIES_FILE = "/cookies/cookies.txt"
_has_cookies = Path(COOKIES_FILE).exists()
COOKIES_MTIME: float | None = Path(COOKIES_FILE).stat().st_mtime if _has_cookies else None
if _has_cookies:
    log.info("Cookies file found at %s", COOKIES_FILE)

YDL_OPTS = {
    # Prefer pre-muxed formats first — merging separate video+audio streams
    # via ffmpeg spikes memory and OOM-killed the bot on a 256MB machine.
    "format": "best[height<=720][ext=mp4]/best[height<=720]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
    "format_sort": ["vcodec:h264"],
    "merge_output_format": "mp4",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extractor_args": {"youtube": {"player_client": ["android", "web", "ios"]}},
    **({"cookiefile": COOKIES_FILE} if _has_cookies else {}),
}

# Process one download at a time — running yt-dlp/ffmpeg in parallel on a
# 256MB machine multiplies peak memory use and risks an OOM kill.
DOWNLOAD_LOCK = asyncio.Semaphore(1)


async def _video_dimensions(filepath: Path) -> tuple[int | None, int | None]:
    """Get display width and height via ffprobe, accounting for rotation."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:stream_tags=rotate",
            "-of", "json", str(filepath),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None, None
        stream = json.loads(stdout).get("streams", [{}])[0]
        w, h = stream.get("width"), stream.get("height")
        if w is None or h is None:
            return None, None
        rotation = int(stream.get("tags", {}).get("rotate", "0"))
        if rotation % 180 != 0:
            w, h = h, w
        return w, h
    except Exception:
        return None, None


async def _download_threads(url: str, dest: str) -> dict | None:
    """Fetch video from a Threads post via the Instagram private API."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            page = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }, follow_redirects=True)
            match = re.search(r'"post_id":"(\d+)"', page.text)
            if not match:
                return None
            post_id = match.group(1)

        cookie_args = ["-b", COOKIES_FILE] if _has_cookies else []
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", *cookie_args,
            "-H", "User-Agent: Barcelona 289.0.0.77.109 Android",
            "-H", "X-IG-App-ID: 238260118697367",
            f"https://i.instagram.com/api/v1/media/{post_id}/info/",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        data = json.loads(stdout)
        items = data.get("items", [])
        if not items:
            return None

        item = items[0]
        video_versions = item.get("video_versions", [])
        if not video_versions:
            return None

        video_url = video_versions[0]["url"]
        async with httpx.AsyncClient(timeout=30) as client:
            video_resp = await client.get(video_url, follow_redirects=True)
            video_resp.raise_for_status()
        out_path = Path(dest) / f"{post_id}.mp4"
        out_path.write_bytes(video_resp.content)
        caption = item.get("caption")
        return {"title": (caption.get("text", "") if caption else "")[:100]}
    except Exception:
        log.exception("Threads download failed for %s", url)
        return None


async def handle_url(update: Update, url: str, force: bool = False) -> None:
    async with DOWNLOAD_LOCK:
        await _download_and_send(update, url, force=force)


async def _download_and_send(update: Update, url: str, force: bool = False) -> None:
    if force:
        stats.VIDEO_CACHE.pop(url, None)
    cached_file_id = stats.VIDEO_CACHE.get(url)
    if cached_file_id:
        try:
            sent = await update.message.reply_video(video=cached_file_id, supports_streaming=True)
            bot_messages.track_bot_message(sent.chat_id, sent.message_id)
            stats.record_stat(url, cache_hit=True, chat_id=sent.chat_id, chat_title=sent.chat.title)
            return
        except Exception:
            log.exception("Cached file_id for %s is no longer valid, re-downloading", url)
            stats.VIDEO_CACHE.pop(url, None)
            stats.save_video_cache()

    with tempfile.TemporaryDirectory() as tmpdir:
        if config.THREADS_RE.search(url):
            info = await _download_threads(url, tmpdir)
            if info is not None:
                all_files = [f for f in Path(tmpdir).iterdir() if f.is_file()]
                if all_files:
                    filepath = all_files[0]
                    size = filepath.stat().st_size
                    if size > config.MAX_BYTES:
                        sent = await update.message.reply_text(
                            f"Video is too large ({size // 1024 // 1024} MB) — Telegram allows 50 MB max."
                        )
                        bot_messages.track_bot_message(sent.chat_id, sent.message_id)
                        stats.record_failure(url, "too_large", update.message.chat_id, update.message.chat.title)
                        return
                    title = info.get("title", "")
                    w, h = await _video_dimensions(filepath)
                    with open(filepath, "rb") as f:
                        msg = await update.message.reply_video(video=f, caption=title, supports_streaming=True, width=w, height=h)
                    bot_messages.track_bot_message(msg.chat_id, msg.message_id)
                    if msg.video:
                        stats.remember_video(url, msg.video.file_id)
                    stats.record_stat(url, cache_hit=False, chat_id=msg.chat_id, chat_title=msg.chat.title)
                else:
                    stats.record_failure(url, "no_files", update.message.chat_id, update.message.chat.title)
                return
            stats.record_failure(url, "download_error", update.message.chat_id, update.message.chat.title)
            return

        opts = {**YDL_OPTS, "outtmpl": f"{tmpdir}/%(id)s.%(ext)s"}
        if config.YOUTUBE_RE.search(url):
            # Cookies push yt-dlp onto YouTube clients that currently hit the
            # SABR-streaming wall (no downloadable formats, only previews).
            # The android/ios clients work fine without cookies for public videos.
            opts.pop("cookiefile", None)
        if config.INSTAGRAM_RE.search(url):
            # Allow carousels (multiple photos/videos in one post) and use a
            # format selector that works for both video and image posts.
            opts["noplaylist"] = False
            opts["format"] = "best[height<=720][ext=mp4]/best[height<=720]/best[ext=jpg]/best[ext=jpeg]/best[ext=png]/best[ext=webp]/best"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError:
            if not (config.INSTAGRAM_RE.search(url) or config.TIKTOK_RE.search(url)):
                stats.record_failure(url, "download_error", update.message.chat_id, update.message.chat.title)
                return
            # yt-dlp intentionally doesn't support Instagram photo posts or
            # TikTok slideshow ("photo mode") posts — fall back to gallery-dl
            # which handles them properly.
            info = {}
            try:
                cookie_args = ["--cookies", COOKIES_FILE] if _has_cookies else []
                result = subprocess.run(
                    ["gallery-dl", *cookie_args, "--dest", tmpdir, url],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode != 0:
                    log.error("gallery-dl failed for %s: %s", url, result.stderr)
                    stats.record_failure(url, "gallery_dl_error", update.message.chat_id, update.message.chat.title)
                    return
            except Exception:
                log.exception("gallery-dl failed for %s", url)
                stats.record_failure(url, "gallery_dl_error", update.message.chat_id, update.message.chat.title)
                return
        except Exception:
            log.exception("Unexpected error for %s", url)
            stats.record_failure(url, "unexpected", update.message.chat_id, update.message.chat.title)
            return

        all_files = [f for f in Path(tmpdir).iterdir() if f.is_file()]
        if not all_files:
            # gallery-dl nests files in subdirs — walk the tree
            all_files = [f for f in Path(tmpdir).rglob("*") if f.is_file()]
        if not all_files:
            stats.record_failure(url, "no_files", update.message.chat_id, update.message.chat.title)
            return

        images = sorted(f for f in all_files if f.suffix.lower() in config.IMAGE_EXTS)
        audio = sorted(f for f in all_files if f.suffix.lower() in config.AUDIO_EXTS)
        videos = sorted(
            f for f in all_files
            if f.suffix.lower() not in config.IMAGE_EXTS and f.suffix.lower() not in config.AUDIO_EXTS
        )

        if videos:
            filepath = videos[0]
            size = filepath.stat().st_size
            if size > config.MAX_BYTES:
                sent = await update.message.reply_text(
                    f"Video is too large ({size // 1024 // 1024} MB) — Telegram allows 50 MB max."
                )
                bot_messages.track_bot_message(sent.chat_id, sent.message_id)
                stats.record_failure(url, "too_large", update.message.chat_id, update.message.chat.title)
                return
            title = info.get("title", "") if not isinstance(info.get("entries"), list) else ""
            w, h = await _video_dimensions(filepath)
            with open(filepath, "rb") as f:
                msg = await update.message.reply_video(video=f, caption=title, supports_streaming=True, width=w, height=h)
            bot_messages.track_bot_message(msg.chat_id, msg.message_id)
            if msg.video:
                stats.remember_video(url, msg.video.file_id)
            stats.record_stat(url, cache_hit=False, chat_id=msg.chat_id, chat_title=msg.chat.title)

        elif images:
            if len(images) == 1:
                with open(images[0], "rb") as f:
                    msg = await update.message.reply_photo(photo=f)
                bot_messages.track_bot_message(msg.chat_id, msg.message_id)
            else:
                media = [InputMediaPhoto(f.read_bytes()) for f in images[:10]]
                msgs = await update.message.reply_media_group(media=media)
                for msg in msgs:
                    bot_messages.track_bot_message(msg.chat_id, msg.message_id)
            if audio:
                # TikTok slideshow ("photo mode") posts pair images with a
                # backing track — send it separately as audio.
                with open(audio[0], "rb") as f:
                    msg = await update.message.reply_audio(audio=f)
                bot_messages.track_bot_message(msg.chat_id, msg.message_id)
            stats.record_stat(url, cache_hit=False, chat_id=update.message.chat_id, chat_title=update.message.chat.title)
