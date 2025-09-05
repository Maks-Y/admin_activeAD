from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
    from ad.ad_client import search_candidates, reset_password, disable_user
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
    if not (update.message and update.effective_user):
        return
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("Access denied")
        return
    buttons = [
        [
            InlineKeyboardButton("Добавить админа", callback_data="super:add"),
            InlineKeyboardButton("Удалить админа", callback_data="super:remove"),
        ],
        [InlineKeyboardButton("Список админов", callback_data="super:list")],
    ]
    await update.message.reply_text(
        "Админские действия:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def super_cb(update: Update, context):
    query = update.callback_query
    user = update.effective_user
    if not (query and user):
        return

    data = query.data or ""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action in {"add", "remove"}:
        if user.id != SUPERADMIN_ID:
            await query.answer("Access denied", show_alert=True)
            return
        if len(parts) < 3:
            await query.answer("No user id", show_alert=True)
            return
        target = int(parts[2])
        if action == "add":
            res = add_admin(target, actor=user.id)
            msg = "Added" if res else "Already"
        else:
            res = remove_admin(target, actor=user.id)
            msg = "Removed" if res else "Missing"
        await query.answer(msg, show_alert=True)
    elif action == "list":
        if not is_admin(user.id):
            await query.answer("Access denied", show_alert=True)
            return
        admins = list_admins(actor=user.id)
        text = ", ".join(str(a) for a in admins) or "No admins"
        await query.answer(text, show_alert=True)
    else:
        await query.answer("Unknown action", show_alert=True)


async def ad_callback(update: Update, context):
    query = update.callback_query
    user = update.effective_user
    if not (query and user):
        return
    if not is_admin(user.id):
        await query.answer("Access denied", show_alert=True)
        return

    data = query.data or ""
    action, *args = data.split(":")
    target = args[0] if args else ""
    if action == "reset":
        pwd = await reset_password(target)
        await query.answer(f"{target}: {pwd}", show_alert=True)
    elif action == "disable":
        await disable_user(target)
        await query.answer(f"{target} disabled", show_alert=True)
    else:
        await query.answer("Unknown", show_alert=True)


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


