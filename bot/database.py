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


def audit(user_id: int | None, action: str, target: str | None = None, details: str | None = None) -> None:
    ts = int(datetime.now(TZ).timestamp())
    DB.execute(
        "INSERT INTO audit_logs (ts, user_id, action, target, details) VALUES (?, ?, ?, ?, ?)",
        (ts, user_id, action, target, json.dumps(details) if isinstance(details, (dict, list)) else details),
    )
    DB.commit()


def add_admin(uid: int, actor: int | None = None) -> bool:
    cur = DB.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
    audit(actor, "add_admin", target=str(uid))
    return cur.rowcount > 0


def remove_admin(uid: int, actor: int | None = None) -> bool:
    cur = DB.execute("DELETE FROM admins WHERE user_id=?", (uid,))
    audit(actor, "remove_admin", target=str(uid))
    return cur.rowcount > 0


def list_admins(actor: int | None = None) -> list[int]:
    cur = DB.execute("SELECT user_id FROM admins ORDER BY user_id")
    rows = [r[0] for r in cur.fetchall()]
    audit(actor, "list_admins")
    return rows
