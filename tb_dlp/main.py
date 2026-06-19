from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, MessageReactionHandler, TypeHandler, filters

from tb_dlp import config, handlers
from tb_dlp.lifecycle import on_startup


async def _log_all_updates(update: Update, context) -> None:
    msg = update.message or update.edited_message
    if msg:
        has_vn = bool(msg.video_note)
        has_text = bool(msg.text)
        config.log.info("RAW UPDATE: update_id=%s has_text=%s has_video_note=%s chat_id=%s", update.update_id, has_text, has_vn, msg.chat_id)


def main() -> None:
    config.require_bot_token()
    app = ApplicationBuilder().token(config.BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(TypeHandler(Update, _log_all_updates), group=-1)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handlers.on_message))
    app.add_handler(CommandHandler("stats", handlers.stats_command))
    app.add_handler(CommandHandler("chatstats", handlers.chatstats_command))
    app.add_handler(CommandHandler("aistats", handlers.aistats_command))
    app.add_handler(CommandHandler("dashboard", handlers.dashboard_command))
    app.add_handler(CommandHandler("profile", handlers.profile_command))
    app.add_handler(CommandHandler("editprofile", handlers.editprofile_command))
    app.add_handler(MessageReactionHandler(handlers.on_reaction))
    config.log.info("Bot started, polling...")
    # message_reaction updates aren't included by default — request everything
    app.run_polling(allowed_updates=Update.ALL_TYPES)
