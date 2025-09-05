from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler, filters,
)
from db.database import is_admin, SUPERADMIN_ID, add_admin, remove_admin, list_admins
from ai.nlp import parse_command
from ad.ad_client import (
    search_candidates, reset_password, schedule_disable
)
from db.models import audit

def setup_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("admin_menu", super_cmd))
    app.add_handler(CallbackQueryHandler(super_cb, pattern=r"^super:"))
    app.add_handler(CallbackQueryHandler(ad_callback, pattern=r"^(reset|disable)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))

# … реализация start_cmd, help_cmd, whoami_cmd и др. …
# в free_text используется parse_command из ai/nlp.py
