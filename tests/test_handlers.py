import types
import asyncio

import pytest


class DummyQuery:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = types.SimpleNamespace(id=user_id)
        self.answered = None

    async def answer(self, text, show_alert=False):
        self.answered = text


def test_super_cb_add_admin(monkeypatch):
    import bot.handlers as h

    called = {}

    def fake_add(uid, actor=None):
        called["args"] = (uid, actor)
        return True

    monkeypatch.setattr(h, "add_admin", fake_add)
    monkeypatch.setattr(h, "SUPERADMIN_ID", 1)

    q = DummyQuery("super:add:42", user_id=1)
    update = types.SimpleNamespace(callback_query=q, effective_user=q.from_user)

    asyncio.run(h.super_cb(update, None))

    assert called["args"] == (42, 1)

def test_super_cb_remove_requires_superadmin(monkeypatch):
    import bot.handlers as h

    called = {}

    def fake_remove(uid, actor=None):
        called["args"] = (uid, actor)
        return True

    monkeypatch.setattr(h, "remove_admin", fake_remove)
    monkeypatch.setattr(h, "SUPERADMIN_ID", 1)

    q = DummyQuery("super:remove:42", user_id=2)
    update = types.SimpleNamespace(callback_query=q, effective_user=q.from_user)

    asyncio.run(h.super_cb(update, None))

    assert called == {}

def test_super_cb_remove_admin(monkeypatch):
    import bot.handlers as h

    called = {}

    def fake_remove(uid, actor=None):
        called["args"] = (uid, actor)
        return True

    monkeypatch.setattr(h, "remove_admin", fake_remove)
    monkeypatch.setattr(h, "SUPERADMIN_ID", 1)

    q = DummyQuery("super:remove:7", user_id=1)
    update = types.SimpleNamespace(callback_query=q, effective_user=q.from_user)

    asyncio.run(h.super_cb(update, None))

    assert called["args"] == (7, 1)

