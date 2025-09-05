import asyncio
import logging
from email.message import EmailMessage
from datetime import datetime
import types
import sys

import pytest

# Provide stub scheduler module for import in mail_checker
sys.modules['scheduler'] = types.SimpleNamespace(schedule_disable_job=lambda *a, **k: None)
sys.modules['db'] = types.SimpleNamespace()
sys.modules['db.database'] = types.SimpleNamespace(TZ=None)

import bot.mail_checker as mc


class FakeIMAP:
    def __init__(self):
        self.messages = {
            b"1": {"flags": set(), "msg": self._make_msg("<id1>")},
            b"2": {"flags": {"\\Seen"}, "msg": self._make_msg("<id2>")},
        }

    def _make_msg(self, msg_id: str) -> bytes:
        m = EmailMessage()
        m["Message-ID"] = msg_id
        m.set_content("test")
        return m.as_bytes()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, user, pwd):
        pass

    def select(self, folder):
        pass

    def search(self, charset, criteria):
        unseen = [num.decode() for num, data in self.messages.items() if "\\Seen" not in data["flags"]]
        return "OK", [" ".join(unseen).encode()]

    def fetch(self, num, parts):
        return "OK", [(b"1", self.messages[num]["msg"])]

    def store(self, num, cmd, flags):
        self.messages[num]["flags"].add(flags)
        return "OK", []


def test_mail_checker_marks_seen(monkeypatch, caplog):
    fake = FakeIMAP()
    monkeypatch.setenv("IMAP_HOST", "host")
    monkeypatch.setenv("IMAP_USER", "user")
    monkeypatch.setenv("IMAP_PASS", "pass")

    monkeypatch.setattr(mc.imaplib, "IMAP4_SSL", lambda host: fake)
    monkeypatch.setattr(mc, "parse_hr_mail", lambda msg: ("User", datetime(2024, 1, 1)))

    scheduled = []
    monkeypatch.setattr(
        mc, "schedule_disable_job", lambda *args, **kwargs: scheduled.append(args)
    )

    async def fake_sleep(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(mc.asyncio, "sleep", fake_sleep)

    caplog.set_level(logging.INFO)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(mc.start_mail_checker())

    assert "\\Seen" in fake.messages[b"1"]["flags"]
    assert fake.messages[b"2"]["flags"] == {"\\Seen"}
    assert len(scheduled) == 1
    assert any("id1" in msg for msg in caplog.messages)
