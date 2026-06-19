from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, MessageReactionHandler, TypeHandler, filters

from tb_dlp import config, handlers
from tb_dlp.lifecycle import on_startup


async def _on_any_update(update: Update, context) -> None:
    if update.message and not (update.message.text and update.message.text.startswith("/")):
        await handlers.on_message(update, context)


def main() -> None:
    config.require_bot_token()
    app = ApplicationBuilder().token(config.BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("stats", handlers.stats_command))
    app.add_handler(CommandHandler("chatstats", handlers.chatstats_command))
    app.add_handler(CommandHandler("aistats", handlers.aistats_command))
    app.add_handler(CommandHandler("dashboard", handlers.dashboard_command))
    app.add_handler(CommandHandler("profile", handlers.profile_command))
    app.add_handler(CommandHandler("editprofile", handlers.editprofile_command))
    app.add_handler(TypeHandler(Update, _on_any_update))
    app.add_handler(MessageReactionHandler(handlers.on_reaction))
    config.log.info("Bot started, polling...")
    # message_reaction updates aren't included by default — request everything
    app.run_polling(allowed_updates=Update.ALL_TYPES)
