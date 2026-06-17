from tb_dlp.storage import JSONStore

# Rolling per-chat message log — persisted to disk so context survives daily
# restarts. Each entry is {"author": str, "text": str, "is_bot": bool}.
CHAT_HISTORY_MAX = 40

_store = JSONStore(
    "/cookies/chat_history.json",
    default=dict,
    decode=lambda raw: {int(k): v for k, v in raw.items()},
)
CHAT_HISTORY: dict[int, list[dict]] = _store.load()


def save() -> None:
    _store.save(CHAT_HISTORY)


def append_to_chat_history(chat_id: int, author: str, text: str, *, is_bot: bool) -> None:
    history = CHAT_HISTORY.setdefault(chat_id, [])
    history.append({"author": author, "text": text, "is_bot": is_bot})
    if len(history) > CHAT_HISTORY_MAX:
        del history[:-CHAT_HISTORY_MAX]


def get_last_bot_message(chat_id: int) -> str | None:
    history = CHAT_HISTORY.get(chat_id, [])
    # Exclude the last entry — that's the message we're currently responding to.
    display = history[:-1] if len(history) > 1 else []
    for msg in reversed(display):
        if msg["is_bot"]:
            return msg["text"]
    return None


def build_chat_context(chat_id: int) -> str:
    history = CHAT_HISTORY.get(chat_id, [])
    # Exclude the last entry — that's the message we're currently responding to,
    # which is already the explicit prompt passed to ask_ai.
    display = history[:-1] if len(history) > 1 else []
    if not display:
        return ""
    lines = []
    for msg in display:
        prefix = "Ігор (you)" if msg["is_bot"] else msg["author"]
        lines.append(f"{prefix}: {msg['text']}")
    return "Recent group chat (most recent at bottom):\n" + "\n".join(lines)
