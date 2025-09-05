from telegram.ext import ApplicationBuilder
from handlers import setup_handlers
from scheduler import scheduler, restore_jobs_on_startup
from mail_checker import start_mail_checker
from db.database import init_db
import os, logging

async def on_startup(app):
    init_db()
    scheduler.start()
    await restore_jobs_on_startup()
    app.create_task(start_mail_checker())

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    application = ApplicationBuilder().token(token).concurrent_updates(True).build()

    setup_handlers(application)
    application.post_init = on_startup

    logging.info("Bot starting")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
