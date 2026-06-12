from tb_dlp.storage import JSONStore

# Curated examples of "their message -> your comeback" for fight-back replies.
# Fed to the AI as few-shot context so it learns the desired roast style from
# real examples instead of just abstract rules. Managed via the admin panel.
COMEBACK_EXAMPLES_PER_REPLY = 3

# Standalone savage words/expressions (no situational context) the AI can
# draw from for vocabulary/flavor when clapping back. Lighter to curate than
# COMEBACK_EXAMPLES — just drop in good lines as you encounter them. Managed
# via the admin panel.
COMEBACK_PHRASES_PER_REPLY = 5

_examples_store = JSONStore("/cookies/comeback_examples.json", default=list)
COMEBACK_EXAMPLES: list[dict] = _examples_store.load()

_phrases_store = JSONStore("/cookies/comeback_phrases.json", default=list)
COMEBACK_PHRASES: list[str] = _phrases_store.load()


def save_examples() -> None:
    _examples_store.save(COMEBACK_EXAMPLES)


def save_phrases() -> None:
    _phrases_store.save(COMEBACK_PHRASES)
