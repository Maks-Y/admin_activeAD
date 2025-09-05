from telegram.ext import ApplicationBuilder
from handlers import setup_handlers
from scheduler import scheduler, restore_jobs_on_startup
from mail_checker import start_mail_checker
from db.database import init_db, SUPERADMIN_ID
from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)
import os, logging, asyncio

async def on_startup(app):
    init_db()
    scheduler.start()
    await restore_jobs_on_startup()
    app.create_task(start_mail_checker())

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    application = ApplicationBuilder().token(token).concurrent_updates(True).build()

    setup_handlers(application)
    async def _set_commands():
        base_cmds = [
            BotCommand("start", "Start"),
            BotCommand("help", "Help"),
            BotCommand("whoami", "Who am I"),
            BotCommand("admin_menu", "Admin menu"),
            BotCommand("jobs", "Jobs"),
        ]
        await application.bot.set_my_commands(base_cmds)

        super_cmds = base_cmds + [
            BotCommand("add_admin", "Add admin"),
            BotCommand("remove_admin", "Remove admin"),
        ]
        await application.bot.set_my_commands(
            super_cmds, scope=BotCommandScopeChat(SUPERADMIN_ID)
        )

        reduced_cmds = [BotCommand("start", "Start"), BotCommand("help", "Help")]
        await application.bot.set_my_commands(
            reduced_cmds, scope=BotCommandScopeAllPrivateChats()
        )

    asyncio.run(_set_commands())
    application.post_init = on_startup

    logging.info("Bot starting")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
