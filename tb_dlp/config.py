import json
import logging
import os
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# httpx logs the full request URL at INFO level, which for Telegram API calls
# includes the bot token (https://api.telegram.org/bot<TOKEN>/...) — keep
# that out of Fly's logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

# Public URL of the admin dashboard (Fly.io's default app domain), used to
# build a one-click login link for /dashboard.
DASHBOARD_BASE_URL = "https://tb-dlp.fly.dev"

# Admin-only commands (/stats, /profile) are restricted to a private DM from
# this Telegram user — keeps usage data and member profiles out of the groups.
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "247313805"))

MAX_BYTES = 50 * 1024 * 1024  # Telegram bot limit

URL_RE = re.compile(r"https?://[^\s]+")
YOUTUBE_RE = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)
INSTAGRAM_RE = re.compile(r"instagram\.com", re.IGNORECASE)
TIKTOK_RE = re.compile(r"tiktok\.com", re.IGNORECASE)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AUDIO_EXTS = {".mp3", ".m4a"}
DOWNLOAD_TRIGGER_RE = re.compile(
    r"\b(скачай|скачати|скачать|завантаж|завантажи|завантажити|загрузи|загрузить|качай|качни|download|redownload|retry)\b",
    re.IGNORECASE,
)

DEFAULT_CHAT_IDS: set[int] = set(
    json.loads(os.environ["DEFAULT_CHAT_IDS"])
    if "DEFAULT_CHAT_IDS" in os.environ
    else []
)
DEFAULT_CHAT_NAMES: dict[int, str] = (
    {int(k): v for k, v in json.loads(os.environ["DEFAULT_CHAT_NAMES"]).items()}
    if "DEFAULT_CHAT_NAMES" in os.environ
    else {}
)


def require_bot_token() -> str:
    if not BOT_TOKEN:
        log.critical("BOT_TOKEN environment variable is not set")
        raise SystemExit(1)
    return BOT_TOKEN
