import sqlite3, json, os
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Berlin"))
DB_PATH = os.getenv("DB_PATH", "bot.db")
SUPERADMIN_ID = int(os.getenv("SUPERADMIN_ID", "0"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sam TEXT NOT NULL,
    run_ts INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    meta TEXT
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    user_id INTEGER,
    action TEXT NOT NULL,
    target TEXT,
    details TEXT
);
"""

DB: sqlite3.Connection | None = None

def init_db():
    global DB
    DB = sqlite3.connect(DB_PATH)
    DB.executescript(SCHEMA)
    DB.execute("PRAGMA journal_mode=WAL")
    return DB

def is_admin(uid: int) -> bool:
    if uid == SUPERADMIN_ID:
        return True
    cur = DB.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    return cur.fetchone() is not None


def add_admin(uid: int) -> None:
    """Add a user to the admins table."""

    DB.execute("INSERT OR IGNORE INTO admins(user_id) VALUES (?)", (uid,))
    DB.commit()


def remove_admin(uid: int) -> None:
    """Remove a user from the admins table."""

    DB.execute("DELETE FROM admins WHERE user_id=?", (uid,))
    DB.commit()


def list_admins() -> list[int]:
    """Return a list of admin user IDs."""

    cur = DB.execute("SELECT user_id FROM admins ORDER BY user_id")
    return [row[0] for row in cur.fetchall()]


def audit(user_id: int | None, action: str, target: str | None = None, details: str | None = None) -> None:
    """Store an audit record for administrative actions."""

    ts = int(datetime.now(TZ).timestamp())
    DB.execute(
        "INSERT INTO audit_logs(ts, user_id, action, target, details) VALUES (?,?,?,?,?)",
        (ts, user_id, action, target, details),
    )
    DB.commit()
