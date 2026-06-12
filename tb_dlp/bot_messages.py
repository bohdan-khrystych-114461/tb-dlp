from tb_dlp.storage import JSONStore

# You (and only you) can react with 👎 on a bot message to delete it. We track
# which (chat, message_id) pairs are the bot's own so this can never be used to
# remove someone else's message.
DELETE_REACTION_EMOJI = "👎"
MAX_TRACKED_MESSAGES = 1000

_store = JSONStore(
    "/cookies/bot_message_ids.json",
    default=set,
    decode=lambda raw: {(int(p[0]), int(p[1])) for p in raw},
    encode=list,
)
BOT_MESSAGE_IDS: set[tuple[int, int]] = _store.load()


def save() -> None:
    _store.save(BOT_MESSAGE_IDS)


def track_bot_message(chat_id: int, message_id: int) -> None:
    BOT_MESSAGE_IDS.add((chat_id, message_id))
    if len(BOT_MESSAGE_IDS) > MAX_TRACKED_MESSAGES:
        BOT_MESSAGE_IDS.pop()
    save()
