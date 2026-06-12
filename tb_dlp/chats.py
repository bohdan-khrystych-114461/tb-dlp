from tb_dlp import config, stats
from tb_dlp.storage import JSONStore

_whitelist_store = JSONStore(
    "/cookies/whitelist.json",
    default=lambda: set(config.DEFAULT_CHAT_IDS),
    decode=lambda raw: {int(x) for x in raw},
    encode=list,
)
ALLOWED_CHAT_IDS: set[int] = _whitelist_store.load()

_chat_names_store = JSONStore(
    "/cookies/chat_names.json",
    default=dict,
    decode=lambda raw: {int(k): v for k, v in raw.items()},
)
# All chats the bot has ever seen — populated before the whitelist check so we
# collect names even from chats trying to reach the bot before being approved.
CHAT_NAMES: dict[int, str] = _chat_names_store.load()
# Seed known names so the whitelist page isn't blank on first run
for _cid, _cname in config.DEFAULT_CHAT_NAMES.items():
    CHAT_NAMES.setdefault(_cid, _cname)


def save_whitelist() -> None:
    _whitelist_store.save(ALLOWED_CHAT_IDS)


def save_chat_names() -> None:
    _chat_names_store.save(CHAT_NAMES)


def chat_name(chat_id: int) -> str:
    return (
        CHAT_NAMES.get(chat_id)
        or stats.STATS.get("by_chat", {}).get(str(chat_id), {}).get("title")
        or str(chat_id)
    )
