import sys
import types
from pathlib import Path

import pytest

# Ensure project root is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def fake_telegram_modules(monkeypatch):
    """Provide minimal telegram stubs if library is missing."""

    try:  # pragma: no cover - real library present
        import telegram  # type: ignore
        import telegram.ext  # type: ignore
        return
    except Exception:
        pass

    telegram = types.ModuleType("telegram")

    class Dummy:
        def __init__(self, *a, **kw):
            pass

    telegram.Update = Dummy
    telegram.ReplyKeyboardMarkup = Dummy
    telegram.InlineKeyboardButton = Dummy
    telegram.InlineKeyboardMarkup = Dummy
    sys.modules["telegram"] = telegram

    ext = types.ModuleType("telegram.ext")
    ext.CommandHandler = Dummy
    ext.MessageHandler = Dummy
    ext.CallbackQueryHandler = Dummy
    ext.filters = types.SimpleNamespace(TEXT=None, COMMAND=None)
    sys.modules["telegram.ext"] = ext

