import os
import importlib
import types
import asyncio
import pytest

class DummyMessage:
    def __init__(self):
        self.texts = []
    async def reply_text(self, text, reply_markup=None):
        self.texts.append((text, reply_markup))

class DummyCallbackQuery:
    def __init__(self, data, message):
        self.data = data
        self.message = message
    async def answer(self, *args, **kwargs):
        pass

class DummyUser:
    def __init__(self, uid):
        self.id = uid

@pytest.fixture
def handlers_with_db(monkeypatch):
    os.environ["DB_PATH"] = ":memory:"
    os.environ["SUPERADMIN_ID"] = "1"
    import bot.database as db
    importlib.reload(db)
    db.init_db()
    import bot.handlers as handlers
    importlib.reload(handlers)
    monkeypatch.setattr(handlers, "add_admin", db.add_admin)
    monkeypatch.setattr(handlers, "remove_admin", db.remove_admin)
    monkeypatch.setattr(handlers, "list_admins", db.list_admins)
    monkeypatch.setattr(handlers, "SUPERADMIN_ID", db.SUPERADMIN_ID)
    return handlers, db

def test_super_cb_add_and_remove(handlers_with_db):
    handlers, db = handlers_with_db
    message = DummyMessage()
    update = types.SimpleNamespace(
        callback_query=DummyCallbackQuery("super:add:42", message),
        effective_user=DummyUser(1),
    )
    asyncio.run(handlers.super_cb(update, None))
    assert db.list_admins(actor=1) == [42]

    update.callback_query.data = "super:remove:42"
    asyncio.run(handlers.super_cb(update, None))
    assert db.list_admins(actor=1) == []
