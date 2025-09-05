from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Optional imports for extended functionality. They are kept behind try/except so
# that the module can be imported in a minimal environment during unit tests
# where these packages may be absent.
try:  # pragma: no cover - used only when full project layout is present
    from db.database import (
        is_admin,
        SUPERADMIN_ID,
        add_admin,
        remove_admin,
        list_admins,
    )
except Exception:  # pragma: no cover - tests focus only on basic handlers
    def is_admin(_):
        return False

    SUPERADMIN_ID = 0

    def add_admin(*_args, **_kwargs):
        return None

    def remove_admin(*_args, **_kwargs):
        return None

    def list_admins():  # noqa: D401 - placeholder
        """Return empty admin list"""
        return []

try:  # pragma: no cover
    from ad.ad_client import search_candidates, reset_password
except Exception:  # pragma: no cover
    async def search_candidates(_query):  # type: ignore
        return []

    async def reset_password(_sam, length: int = 12):  # type: ignore
        return ""

from ai.nlp import parse_command

def setup_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("admin_menu", super_cmd))
    app.add_handler(CallbackQueryHandler(super_cb, pattern=r"^super:"))
    app.add_handler(CallbackQueryHandler(ad_callback, pattern=r"^(reset|disable)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))

MENU_BUTTONS = [
    ["Reset Password", "Schedule Block"],
    ["List Jobs", "Admin Menu"],
]


def _main_keyboard() -> ReplyKeyboardMarkup:
    """Return the main reply keyboard used in the bot."""

    return ReplyKeyboardMarkup(MENU_BUTTONS, resize_keyboard=True)


async def start_cmd(update: Update, context):
    """Handle the /start command by greeting the user and showing the menu."""

    if update.message:  # pragma: no branch - always true for /start
        await update.message.reply_text(
            "Select an action:", reply_markup=_main_keyboard()
        )


async def menu_cmd(update: Update, context):
    """Re-send the main keyboard in case a user hid it."""

    if update.message:
        await update.message.reply_text(
            "Menu:", reply_markup=_main_keyboard()
        )


async def help_cmd(update: Update, context):
    if update.message:
        await update.message.reply_text(
            "Use the buttons or type commands like 'reset <user>'."
        )


async def whoami_cmd(update: Update, context):
    if update.message and update.effective_user:
        await update.message.reply_text(
            f"Your id: {update.effective_user.id}"
        )


async def super_cmd(update: Update, context):
    if update.message:
        await update.message.reply_text("Admin menu is not implemented.")


async def super_cb(update: Update, context):
    if update.callback_query:
        await update.callback_query.answer("Not implemented")


async def ad_callback(update: Update, context):
    if update.callback_query:
        await update.callback_query.answer("Not implemented")


async def free_text(update: Update, context):
    """Handle free-form text or payloads from reply buttons."""

    if not update.message:
        return

    text = update.message.text or ""
    cmd, args = parse_command(text)

    if cmd == "reset":
        if not args:
            await update.message.reply_text("Usage: reset <samAccountName>")
            return
        pwd = await reset_password(args[0])
        await update.message.reply_text(f"New password for {args[0]}: {pwd}")
    elif cmd == "disable":
        await update.message.reply_text("Scheduling is not implemented yet.")
    elif cmd == "jobs":
        await update.message.reply_text("No scheduled jobs.")
    elif cmd == "admin":
        await update.message.reply_text("Admin menu is not implemented.")
    else:
        await update.message.reply_text(
            "Unrecognised input. Use /menu to show available actions."
        )


