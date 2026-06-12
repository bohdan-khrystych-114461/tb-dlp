import logging
import random

import httpx

from tb_dlp import ai, bot_messages, chat_history, comebacks, profiles

log = logging.getLogger(__name__)

# Gemini free tier caps us at ~20 generateContent calls/day — when that's hit,
# the AI call 429s and we obviously can't ask the AI to write its own excuse.
# First time it happens we say so once; after that we keep it short so the
# chat doesn't get the same "I'm out" speech on every single mention.
RATE_LIMIT_FIRST_REPLY = "Так, я на перекур и спать."
RATE_LIMIT_REPEAT_REPLY = "Сплю, не напрягай плз."
_rate_limited_once = False


async def reply_with_ai(message, prompt: str, user, *, uninvited: bool = False) -> None:
    global _rate_limited_once

    profile = profiles.USER_PROFILES.get(str(user.id)) if user else None
    user_note = (
        f"A note about {user.full_name}: {profile['notes']}"
        if profile else ""
    )
    chat_context = chat_history.build_chat_context(message.chat_id)
    if uninvited:
        note = "You're chiming in here on your own — nobody @mentioned you. Keep it brief and natural, like a group member jumping in. Match the tone of the conversation — don't be rude or aggressive unless the chat was already going that way."
        chat_context = (chat_context + "\n\n" + note).strip() if chat_context else note
    else:
        if comebacks.COMEBACK_EXAMPLES:
            sample = random.sample(comebacks.COMEBACK_EXAMPLES, min(comebacks.COMEBACK_EXAMPLES_PER_REPLY, len(comebacks.COMEBACK_EXAMPLES)))
            examples_text = "\n".join(f'- They said: "{ex["trigger"]}" → You replied: "{ex["reply"]}"' for ex in sample)
            examples_note = (
                "Examples of how you've nailed it when clapping back at trolling/"
                "insults before — match this style and sharpness ONLY if the "
                "current message is similarly hostile toward you, otherwise "
                "ignore these:\n" + examples_text
            )
            chat_context = (chat_context + "\n\n" + examples_note).strip() if chat_context else examples_note

        if comebacks.COMEBACK_PHRASES:
            phrase_sample = random.sample(comebacks.COMEBACK_PHRASES, min(comebacks.COMEBACK_PHRASES_PER_REPLY, len(comebacks.COMEBACK_PHRASES)))
            phrases_text = "\n".join(f"- {p}" for p in phrase_sample)
            phrases_note = (
                "Some words/expressions from your usual vocabulary you can pull "
                "from when clapping back — use one ONLY if it actually fits what "
                "you're saying and the message is hostile toward you, adapt it "
                "to the context, don't force it in or repeat the same one every "
                "time:\n" + phrases_text
            )
            chat_context = (chat_context + "\n\n" + phrases_note).strip() if chat_context else phrases_note

    lang = ai.detect_reply_language(prompt)
    if lang == "ru":
        lang_note = (
            "LANGUAGE OVERRIDE (highest priority — overrides chat history, "
            "your own previous replies, and any other language cue): the "
            "message you're replying to right now is in Russian or surzhyk "
            "(mixed Russian-Ukrainian slang). Reply entirely in Russian, not "
            "Ukrainian."
        )
    elif lang == "uk":
        lang_note = (
            "LANGUAGE OVERRIDE (highest priority): the message you're "
            "replying to right now is substantially in Ukrainian. Reply in "
            "Ukrainian."
        )
    else:
        lang_note = None
    if lang_note:
        chat_context = (chat_context + "\n\n" + lang_note).strip() if chat_context else lang_note

    image_bytes: bytes | None = None
    photo_list = message.photo or (
        message.reply_to_message.photo if message.reply_to_message else None
    )
    if photo_list:
        try:
            tg_file = await message.get_bot().get_file(photo_list[-1].file_id)
            ba = await tg_file.download_as_bytearray()
            image_bytes = bytes(ba)
        except Exception:
            log.exception("Failed to download photo for AI")

    try:
        reply = await ai.ask_ai(prompt, user_note=user_note, chat_context=chat_context, image_bytes=image_bytes)
        sent = await message.reply_text(reply)
        bot_messages.track_bot_message(sent.chat_id, sent.message_id)
        chat_history.append_to_chat_history(message.chat_id, "bot", reply, is_bot=True)
        chat_history.save()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429 or exc.response.status_code >= 500:
            text_reply = RATE_LIMIT_REPEAT_REPLY if _rate_limited_once else RATE_LIMIT_FIRST_REPLY
            _rate_limited_once = True
            sent = await message.reply_text(text_reply)
            bot_messages.track_bot_message(sent.chat_id, sent.message_id)
        else:
            log.exception("AI request failed")
    except Exception:
        log.exception("AI request failed")
