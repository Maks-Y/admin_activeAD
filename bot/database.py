import sqlite3, json, os
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Berlin"))
DB_PATH = os.getenv("DB_PATH", "bot.db")

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
    if uid == int(os.getenv("SUPERADMIN_ID", "0")):
        return True
    cur = DB.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    return cur.fetchone() is not None

# … функции add_admin, remove_admin, list_admins, audit …
