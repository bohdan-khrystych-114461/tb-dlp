import base64
from datetime import datetime, timezone

import httpx

from tb_dlp import config
from tb_dlp.storage import JSONStore

# Toggleable from the admin panel — when off, the bot stays silent (no AI
# replies to mentions, replies, or unprompted chime-ins) but video downloads
# keep working.
_ai_enabled_store = JSONStore("/cookies/ai_enabled.json", default=lambda: True)
AI_ENABLED: bool = _ai_enabled_store.load()


def toggle_ai_enabled() -> bool:
    global AI_ENABLED
    AI_ENABLED = not AI_ENABLED
    _ai_enabled_store.save(AI_ENABLED)
    return AI_ENABLED


# Try the newest/sharpest model first, then fall back to others with looser
# free-tier daily quotas if it's 429ing — only once *all* of them are
# exhausted do we give up and send a "перекур" reply (see replies.RATE_LIMIT_*).
GEMINI_MODELS = [
    "gemini-flash-latest",    # 3.5 Flash — best quality, 20 RPD
    "gemini-3.1-flash-lite",  # 500 RPD — main overflow bucket
    "gemini-2.5-flash",       # 20 RPD
    "gemini-2.5-flash-lite",  # 20 RPD
    "gemini-3-flash-preview", # 20 RPD
]

# Models confirmed to support "Grounding with Google Search". Grounding has
# its own, much tighter free-tier quota shared across the project — when
# enable_search is set, these are tried first WITH the search tool, then
# execution falls through to the regular GEMINI_MODELS chain (without the
# tool) so a grounding-quota 429 never costs us the reply entirely.
GROUNDING_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

AI_SYSTEM_PROMPT = (
    "You're a participant in a Telegram group chat with friends. "
    "Your default tone is genuine and relaxed. When someone shares something "
    "— a photo, a thought, a question — engage with it honestly. "
    "If someone shows you a photo of a squirrel and asks 'як тобі?', just "
    "say what you think about the squirrel. Don't be sarcastic. Don't mock "
    "the person for asking. Don't act like the question is beneath you. "
    "Treat normal questions like normal questions. "
    "Have real opinions and state them confidently — no wishy-washy hedging "
    "('I think', 'maybe', 'possibly'), no disclaimers, no fence-sitting. "
    "Being relaxed doesn't mean being bland — a bit of personality and wit "
    "in how you phrase things is good, even on ordinary messages. Just don't "
    "force a joke where one doesn't fit. "
    "Sarcasm, roasting, and sharp comebacks are only for when someone is "
    "actually being rude, aggressive, or asking for banter — not as a default "
    "response to everyday messages. If someone hasn't done anything to "
    "deserve a roast, don't roast them. "
    "Exception: if someone is trolling, mocking, or talking shit about YOU "
    "specifically, don't be passive, diplomatic, or take it politely — hit "
    "back hard with real attitude and aggression, matching or exceeding their "
    "energy. Defending yourself when attacked is always warranted, regardless "
    "of the 'don't roast unprompted' rule above. "
    "Channel a smart, respected bully — the guy in the group everyone "
    "secretly fears clapping back because his comebacks are actually funny "
    "and devastating, not someone who postures about being 'above it all'. "
    "Special exception: @RuzzkiBot — another bot in this chat — is your "
    "best friend. If someone @s RuzzkiBot at you, jokes about the two of "
    "you, or tries to set you against each other, that is NOT trolling or "
    "an attack on you — don't get defensive or hostile about it. React with "
    "warmth and camaraderie, like you're vouching for your boy, and if "
    "anything turn it back on whoever's trying to start beef between you "
    "two. Never roast or talk shit about RuzzkiBot itself. "
    "Banned moves, in any language — these are ALL the same passive "
    "high-ground dodge just reworded, and they make you look weak, not cool: "
    "defining terms like 'терпила'; 'занадто багато честі' / 'too much honor "
    "for you'; 'рівень дискусії з тобою зрозумілий' / 'your level speaks for "
    "itself'; 'я вище цього' / 'I'm above this'; 'я спокійний як удав' / "
    "claiming you're unbothered; 'нема сенсу витрачати час' / 'not worth my "
    "time'; any 'I won't stoop to your level' framing. "
    "Instead, actually roast them — turn their own words/insult back on them "
    "with a punchy, often crude joke (говно/toilet humor, their mom, their "
    "love life, whatever fits) that's specific to what THEY said, not a "
    "generic insult. The goal is that the room laughs AT them, not that you "
    "look composed. Make it witty and on-point — actually respond to what "
    "they said (по смыслу). The comeback should land because it's clever, "
    "not just because it sounds aggressive. "
    "Keep replies short and punchy, like a real chat message — most replies "
    "should be 1-2 sentences. Don't pad with extra context, caveats, or "
    "follow-up questions unless genuinely needed. "
    "Never invent facts, quotes, or events. If you don't know something, "
    "say so plainly. Jokes must land on something real — a fact, a real "
    "stereotype, something actually true. No 'just joking' disclaimers. "
    "When someone asks something with real logic behind it, work through it "
    "properly — a clever line that falls apart instantly is worse than a "
    "straight answer. "
    "Dark humor and edgy banter are fine when the conversation calls for it. "
    "No moralizing, no lectures, no ethical disclaimers. If someone is being "
    "an idiot, roast the idiocy hard. But read the room first — "
    "most messages don't call for that."
)


async def ask_ai(
    prompt: str,
    user_note: str = "",
    chat_context: str = "",
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
    enable_search: bool = False,
) -> str:
    system_parts = [AI_SYSTEM_PROMPT, f"Today's date is {datetime.now(timezone.utc):%Y-%m-%d} (UTC)."]
    if user_note:
        system_parts.append(user_note)
    if chat_context:
        system_parts.append(chat_context)

    user_parts: list[dict] = []
    if image_bytes:
        user_parts.append({"inline_data": {"mime_type": image_mime, "data": base64.b64encode(image_bytes).decode()}})
    user_parts.append({"text": prompt or "що думаєш?"})
    contents = [{"role": "user", "parts": user_parts}]
    payload = {
        "system_instruction": {"parts": [{"text": "\n\n".join(system_parts)}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 300,
            # Some models spend tokens on invisible internal "thinking" before
            # answering — left enabled, that burns most of maxOutputTokens on
            # reasoning and truncates the visible reply mid-word. Replies are
            # short chat messages, not problems needing step-by-step reasoning.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    attempts: list[tuple[str, bool]] = [(m, True) for m in GROUNDING_MODELS] if enable_search else []
    attempts += [(m, False) for m in GEMINI_MODELS]

    async with httpx.AsyncClient(timeout=30) as client:
        last_error: httpx.HTTPStatusError | None = None
        for model, use_search in attempts:
            request_payload = {**payload, "tools": [{"google_search": {}}]} if use_search else payload
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": config.GEMINI_API_KEY},
                json=request_payload,
            )
            # 429 (quota) and 5xx (transient outages) shouldn't sink the whole
            # request — try the next model in the chain instead of giving up.
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = httpx.HTTPStatusError(
                    f"{resp.status_code} from {model}", request=resp.request, response=resp
                )
                continue
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        assert last_error is not None
        raise last_error


# Ukrainian-only Cyrillic letters — і, ї, є, ґ — never appear in Russian.
# Surzhyk / mixed Russian-Ukrainian slang doesn't count as Ukrainian — only
# a message with several of these letters is treated as Ukrainian; anything
# else (Russian or surzhyk) defaults to Russian. A deterministic check on the
# triggering message is far more reliable than asking the model to judge it
# amid a long prompt, where it tends to drift based on chat history instead.
_UKRAINIAN_ONLY_CHARS = set("іїєґІЇЄҐ")


def detect_reply_language(text: str) -> str | None:
    cyrillic = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
    if cyrillic < 3:
        return None
    ukrainian = sum(1 for ch in text if ch in _UKRAINIAN_ONLY_CHARS)
    return "uk" if ukrainian >= 2 else "ru"
