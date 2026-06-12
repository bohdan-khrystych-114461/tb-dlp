import logging

from tb_dlp import ai
from tb_dlp.storage import JSONStore

log = logging.getLogger(__name__)

# Lightweight per-member profiles so AI replies can be tailored to whoever's
# talking — built up automatically from their own messages (interests, tone,
# recurring topics), no manual input needed.
PROFILE_UPDATE_THRESHOLD = 25  # messages collected before (re)summarizing someone

_profiles_store = JSONStore("/cookies/user_profiles.json", default=dict)
USER_PROFILES: dict[str, dict] = _profiles_store.load()

# Persisted to disk — the bot restarts daily for yt-dlp updates (and on every
# deploy), and an in-memory buffer would never reach PROFILE_UPDATE_THRESHOLD.
_buffers_store = JSONStore(
    "/cookies/user_message_buffers.json",
    default=dict,
    decode=lambda raw: {int(k): v for k, v in raw.items()},
)
USER_MESSAGE_BUFFERS: dict[int, list[str]] = _buffers_store.load()


def save_profiles() -> None:
    _profiles_store.save(USER_PROFILES)


def save_message_buffers() -> None:
    _buffers_store.save(USER_MESSAGE_BUFFERS)


async def update_profile(user_id: int, name: str, username: str | None, *, force: bool = False) -> None:
    messages = USER_MESSAGE_BUFFERS.get(user_id, [])
    if not force and len(messages) < PROFILE_UPDATE_THRESHOLD:
        return
    if not messages:
        return
    USER_MESSAGE_BUFFERS[user_id] = []
    save_message_buffers()

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
        notes = await ai.ask_ai(prompt)
    except Exception:
        log.exception("Failed to update profile for %s", name)
        return

    USER_PROFILES[str(user_id)] = {"name": name, "username": username, "notes": notes}
    save_profiles()


def find_profile(query: str) -> tuple[str, dict] | None:
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
