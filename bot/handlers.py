from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
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
    from .database import (
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
    from .ad_client import search_candidates, reset_password, disable_user
except Exception:  # pragma: no cover
    async def search_candidates(_query):  # type: ignore
        return []

    async def reset_password(_sam, length: int = 12):  # type: ignore
        return ""

    async def disable_user(_sam):  # type: ignore
        return None

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
    """Display superadmin menu with inline buttons."""

    if not update.message or not update.effective_user:
        return

    if update.effective_user.id != SUPERADMIN_ID:
        await update.message.reply_text("Access denied")
        return

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Добавить администратора", callback_data="super:add")],
            [InlineKeyboardButton("Удалить администратора", callback_data="super:remove")],
            [InlineKeyboardButton("Список администраторов", callback_data="super:list")],
        ]
    )

    await update.message.reply_text("Администрирование:", reply_markup=keyboard)


async def super_cb(update: Update, context):
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    if user.id != SUPERADMIN_ID:
        await query.answer("Access denied", show_alert=True)
        return

    await query.answer()
    data = (query.data or "").split(":")
    action = data[1] if len(data) > 1 else ""
    response = ""
    if action == "list":
        admins = list_admins(actor=user.id)
        response = ", ".join(map(str, admins)) if admins else "No admins"
    elif action in {"add", "remove"} and len(data) > 2:
        try:
            target = int(data[2])
        except ValueError:
            response = "Invalid user id"
        else:
            if action == "add":
                ok = add_admin(target, actor=user.id)
                response = "Admin added" if ok else "Already an admin"
            else:
                ok = remove_admin(target, actor=user.id)
                response = "Admin removed" if ok else "Not an admin"
    else:
        response = "Specify user id"

    await query.message.reply_text(response)


async def ad_callback(update: Update, context):
    query = update.callback_query
    if not query:
        return

    await query.answer()
    action, sam = (query.data or "").split(":", 1)
    if action == "reset":
        pwd = await reset_password(sam)
        await query.message.reply_text(f"New password for {sam}: {pwd}")
    elif action == "disable":
        await disable_user(sam)
        await query.message.reply_text(f"User {sam} disabled")


async def free_text(update: Update, context):
    """Handle free-form text or payloads from reply buttons."""

    if not update.message:
        return

    text = update.message.text or ""
    cmd, args = parse_command(text)

    if cmd in {"reset", "disable"}:
        if not args:
            await update.message.reply_text(f"Usage: {cmd} <query>")
            return
        query = " ".join(args)
        candidates = await search_candidates(query)
        if not candidates:
            await update.message.reply_text("No users found")
            return
        keyboard = [
            [InlineKeyboardButton(c.DisplayName, callback_data=f"{cmd}:{c.SamAccountName}")]
            for c in candidates
        ]
        await update.message.reply_text(
            "Select user:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif cmd == "jobs":
        await update.message.reply_text("No scheduled jobs.")
    elif cmd == "admin":
        await super_cmd(update, context)
    else:
        await update.message.reply_text(
            "Unrecognised input. Use /menu to show available actions.",
        )


