import os
import importlib

import pytest


@pytest.fixture
def db():
    os.environ["DB_PATH"] = ":memory:"
    import bot.database as database
    importlib.reload(database)
    database.init_db()
    return database


def test_add_and_remove_admin(db):
    assert db.list_admins(actor=1) == []
    assert db.add_admin(42, actor=1) is True
    assert db.list_admins(actor=1) == [42]
    assert db.remove_admin(42, actor=1) is True
    assert db.list_admins(actor=1) == []


def test_audit_logging(db):
    db.add_admin(7, actor=99)
    db.list_admins(actor=99)
    db.remove_admin(7, actor=99)
    rows = db.DB.execute(
        "SELECT action, target, user_id FROM audit_logs ORDER BY id"
    ).fetchall()
    assert rows == [
        ("add_admin", "7", 99),
        ("list_admins", None, 99),
        ("remove_admin", "7", 99),
    ]

