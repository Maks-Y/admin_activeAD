#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бoт для администраторов AD (Windows Server 2019)
Функции:
- Роли: супер-админ (из переменной окружения SUPERADMIN_ID) и админы (в SQLite)
- Свободная форма команд («Смени пароль Устиновой Наталье»)
- Нечёткий поиск пользователей в AD, уточнение кнопками при дублях
- Блокировка учётки по письмам HR и/или по команде
- Планирование задач на 16:00 даты увольнения (APScheduler + SQLite)
- Аудит: логи в файл и таблицу audit_logs

Запуск:
  1) Python >= 3.10
  2) pip install -r requirements.txt
  3) Установить переменные окружения (см. секцию ENV ниже)
  4) python main.py

ENV (пример):
  TELEGRAM_TOKEN=123:ABC
  SUPERADMIN_ID=123456789
  TIMEZONE=Europe/Berlin
  # Подключение к AD — вариант 1: локальный PowerShell на Windows-сервере
  AD_CONNECTION=local
  AD_SEARCH_BASE="DC=corp,DC=local"
  # Вариант 2: удалённый WinRM (если бот не на AD-сервере)
  # AD_CONNECTION=winrm
  # AD_HOST=ad01.corp.local
  # AD_USER=CORP\\svc_adbot
  # AD_PASS=***

  # Почта HR (IMAP, SSL)
  IMAP_HOST=imap.example.com
  IMAP_USER=hr@example.com
  IMAP_PASS=***
  IMAP_FOLDER=INBOX
  IMAP_POLL_SECONDS=300

requirements.txt (минимум):
  python-telegram-bot~=21.4
  APScheduler~=3.10
  rapidfuzz~=3.9
  dateparser~=1.2
  # опционально для более качественной морфологии русского:
  pymorphy2~=0.9.1
  pymorphy2-dicts-ru~=2.4.417127.4579844
  # если используете WinRM:
  pypsrp~=0.9
  pywinrm~=0.4

"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import string
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional, Tuple

import dateparser
from rapidfuzz import process, fuzz

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

# --------- Глобальная настройка ---------
TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Berlin"))
SUPERADMIN_ID = int(os.getenv("SUPERADMIN_ID", "0") or 0)

DB_PATH = os.getenv("DB_PATH", "bot.db")
LOG_PATH = os.getenv("LOG_PATH", "logs/bot.log")

IMAP_POLL_SECONDS = int(os.getenv("IMAP_POLL_SECONDS", "300"))
IMAP_HOST = os.getenv("IMAP_HOST")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASS = os.getenv("IMAP_PASS")
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")

AD_CONNECTION = os.getenv("AD_CONNECTION", "local")  # local | winrm
AD_HOST = os.getenv("AD_HOST")
AD_USER = os.getenv("AD_USER")
AD_PASS = os.getenv("AD_PASS")
AD_SEARCH_BASE = os.getenv("AD_SEARCH_BASE", "DC=corp,DC=local")

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("tg_ad_bot")

# --------- БД ---------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS admins (
  user_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  details TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_type TEXT NOT NULL,              -- DISABLE_ACCOUNT
  sAMAccountName TEXT NOT NULL,
  run_at TEXT NOT NULL,                -- ISO
  status TEXT NOT NULL DEFAULT 'SCHEDULED', -- SCHEDULED | DONE | FAILED
  created_by INTEGER,
  meta TEXT
);
"""


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


# --------- Модели данных ---------
@dataclass
class ADUser:
    SamAccountName: str
    DisplayName: str
    DistinguishedName: str
    Enabled: bool


# --------- Утилиты ---------

def now_tz() -> datetime:
    return datetime.now(tz=TZ)


def parse_date_ru(text: str) -> Optional[datetime]:
    # Поддерживает: 31.08.2025, 31-08-2025, «31 августа 2025», «завтра», «сегодня» и т.п.
    dt = dateparser.parse(text, languages=["ru"], settings={"TIMEZONE": str(TZ), "RETURN_AS_TIMEZONE_AWARE": True})
    return dt


def audit(actor_id: int, action: str, target: str | None = None, details: dict | None = None):
    with db() as conn:
        conn.execute(
            "INSERT INTO audit_logs (ts, actor_id, action, target, details) VALUES (?,?,?,?,?)",
            (now_tz().isoformat(), actor_id, action, target, json.dumps(details, ensure_ascii=False) if details else None),
        )
        conn.commit()


# --------- Доступ/Роли ---------

def is_superadmin(user_id: int) -> bool:
    return SUPERADMIN_ID and user_id == SUPERADMIN_ID


def is_admin(user_id: int) -> bool:
    if is_superadmin(user_id):
        return True
    with db() as conn:
        cur = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return cur.fetchone() is not None


# --------- Генерация паролей ---------
SPECIAL_SAFE = "!@#$%^&*"  # безопасный набор для AD


def generate_password(length: int = 12) -> str:
    if length < 9:
        length = 12
    categories = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice(SPECIAL_SAFE),
    ]
    pool = string.ascii_letters + string.digits + SPECIAL_SAFE
    rest = [random.choice(pool) for _ in range(length - len(categories))]
    pwd_list = categories + rest
    random.shuffle(pwd_list)
    return "".join(pwd_list)


# --------- NLU (простые правила) ---------
RESET_PWD_PATTERNS = [r"смени\s+пароль", r"сброс(ь|ить)\s+пароль", r"reset\s+pass"]
DISABLE_PATTERNS = [r"заблокируй", r"отключи", r"disable\s+account", r"увол(ен|ена)"]
DATE_PATTERNS = [r"(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})", r"сегодня|завтра|послезавтра|через\s+\d+\s+дн"]


def detect_intent(text: str) -> str | None:
    t = text.lower()
    if any(re.search(p, t) for p in RESET_PWD_PATTERNS):
        return "reset_password"
    if any(re.search(p, t) for p in DISABLE_PATTERNS):
        return "disable_account"
    return None


def extract_name_query(text: str) -> Optional[str]:
    # Наивная вырезка всего после ключевой фразы, напр.: «Смени пароль Устиновой Наталье»
    t = text.lower()
    for p in RESET_PWD_PATTERNS + DISABLE_PATTERNS:
        m = re.search(p + r"\s+(.+)$", t)
        if m:
            return m.group(1).strip()
    return None


def extract_date(text: str) -> Optional[datetime]:
    # Ищем явные даты/слова
    for p in DATE_PATTERNS:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            dt = parse_date_ru(m.group(0))
            if dt:
                return dt
    return None


# --------- Доступ к AD ---------

def ps_escape(s: str) -> str:
    return s.replace("`", "``").replace("'", "''")


async def ad_search_candidates(name_query: str, limit: int = 10) -> List[ADUser]:
    """Возвращает кандидатов по подстроке из DisplayName/cn/sAM.
    Сначала делаем грубый поиск в AD, затем сортируем нечетким сравнением."""
    raw = await ad_invoke(
        f"""
        Import-Module ActiveDirectory;
        $q = '{ps_escape(name_query)}';
        $filter = "(displayName -like '*$q*') -or (cn -like '*$q*') -or (sAMAccountName -like '*$q*') -or (givenName -like '*$q*') -or (sn -like '*$q*')";
        Get-ADUser -LDAPFilter '(objectClass=user)' -SearchBase '{ps_escape(AD_SEARCH_BASE)}' -Properties displayName,distinguishedName,enabled,sAMAccountName |
          Where-Object {{ $_.displayName -like "*{ps_escape(name_query)}*" -or $_.sAMAccountName -like "*{ps_escape(name_query)}*" -or $_.Name -like "*{ps_escape(name_query)}*" }} |
          Select-Object sAMAccountName, displayName, distinguishedName, Enabled |
          ConvertTo-Json
        """
    )
    items = []
    try:
        data = json.loads(raw) if raw else []
        if isinstance(data, dict):
            data = [data]
        for it in data[:100]:
            items.append(
                ADUser(
                    SamAccountName=it.get("sAMAccountName", ""),
                    DisplayName=it.get("displayName", ""),
                    DistinguishedName=it.get("distinguishedName", ""),
                    Enabled=bool(it.get("Enabled", True)),
                )
            )
    except Exception as e:
        log.exception("ad_search_candidates parse error: %s", e)

    # Нечёткая сортировка по запросу против DisplayName/ sAM
    choices = {f"{u.DisplayName} ({u.SamAccountName})": u for u in items}
    ranked = process.extract(name_query, list(choices.keys()), scorer=fuzz.WRatio, limit=limit)
    result = [choices[k] for (k, _score, _idx) in ranked]
    return result


async def ad_reset_password(sam: str, new_pwd: str, force_change_at_logon: bool = True) -> str:
    script = f"""
        Import-Module ActiveDirectory;
        $sam = '{ps_escape(sam)}';
        $pwd = ConvertTo-SecureString '{ps_escape(new_pwd)}' -AsPlainText -Force;
        Set-ADAccountPassword -Identity $sam -Reset -NewPassword $pwd;
        {'Set-ADUser -Identity $sam -ChangePasswordAtLogon $true;' if force_change_at_logon else ''}
        Write-Output "OK"
    """
    out = await ad_invoke(script)
    return out.strip()


async def ad_disable_account(sam: str) -> str:
    script = f"""
        Import-Module ActiveDirectory;
        Disable-ADAccount -Identity '{ps_escape(sam)}';
        Write-Output "OK"
    """
    out = await ad_invoke(script)
    return out.strip()


async def ad_invoke(script: str) -> str:
    """Выполняет PowerShell локально или по WinRM. Возвращает stdout."""
    if AD_CONNECTION == "local":
        # Запуск локального PowerShell (требуется Windows + установленный модуль ActiveDirectory)
        import subprocess
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-NonInteractive", "-Command", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            log.error("PowerShell error: %s", err.decode(errors="ignore"))
            raise RuntimeError("PowerShell failed")
        return out.decode("utf-8", errors="ignore")
    elif AD_CONNECTION == "winrm":
        # Удалённый вызов через WinRM
        from pypsrp.client import Client
        client = Client(AD_HOST, username=AD_USER, password=AD_PASS, ssl=False, port=5985, connection_timeout=30)
        ps = client.execute_ps(script)
        if ps.rc != 0:
            log.error("WinRM error: %s", ps.error)
            raise RuntimeError("WinRM PowerShell failed")
        return ps.output
    else:
        raise RuntimeError("Unknown AD_CONNECTION")


# --------- Планировщик задач ---------
scheduler = AsyncIOScheduler(timezone=str(TZ))


def schedule_disable_job(sam: str, run_dt: datetime, created_by: int, meta: dict | None = None):
    run_dt = run_dt.astimezone(TZ)
    with db() as conn:
        conn.execute(
            "INSERT INTO jobs (job_type, sAMAccountName, run_at, created_by, meta) VALUES (?,?,?,?,?)",
            ("DISABLE_ACCOUNT", sam, run_dt.isoformat(), created_by, json.dumps(meta or {}, ensure_ascii=False)),
        )
        job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    scheduler.add_job(execute_disable_job, trigger=DateTrigger(run_date=run_dt), args=[job_id], id=f"job-{job_id}")
    log.info("Запланирована блокировка %s на %s (job %s)", sam, run_dt, job_id)


async def execute_disable_job(job_id: int):
    # Вызывается планировщиком
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["status"] != "SCHEDULED":
            return
        sam = row["sAMAccountName"]
    try:
        out = await ad_disable_account(sam)
        with db() as conn:
            conn.execute("UPDATE jobs SET status='DONE' WHERE id=?", (job_id,))
            conn.commit()
        log.info("Блокировка %s выполнена: %s", sam, out)
    except Exception as e:
        with db() as conn:
            conn.execute("UPDATE jobs SET status='FAILED' WHERE id=?", (job_id,))
            conn.commit()
        log.exception("Ошибка при блокировке %s: %s", sam, e)


async def restore_jobs_on_startup():
    # При рестарте подтягиваем будущие задачи
    with db() as conn:
        rows = conn.execute("SELECT id, run_at FROM jobs WHERE status='SCHEDULED'").fetchall()
    for r in rows:
        run_dt = datetime.fromisoformat(r["run_at"]).astimezone(TZ)
        if run_dt < now_tz():
            # просрочено — исполним немедленно
            scheduler.add_job(execute_disable_job, trigger=DateTrigger(run_date=now_tz()+timedelta(seconds=5)), args=[r["id"]], id=f"job-{r['id']}")
        else:
            scheduler.add_job(execute_disable_job, trigger=DateTrigger(run_date=run_dt), args=[r["id"]], id=f"job-{r['id']}")


# --------- IMAP парсер писем HR ---------
async def imap_poll_loop(app):
    if not IMAP_HOST or not IMAP_USER or not IMAP_PASS:
        log.warning("IMAP не настроен; пропускаю опрос почты")
        return
    import imaplib, email
    while True:
        try:
            M = imaplib.IMAP4_SSL(IMAP_HOST)
            M.login(IMAP_USER, IMAP_PASS)
            M.select(IMAP_FOLDER)
            # Ищем новые
            typ, data = M.search(None, 'UNSEEN')
            if typ == 'OK':
                for num in data[0].split():
                    typ, msg_data = M.fetch(num, '(RFC822)')
                    if typ != 'OK':
                        continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    subject = email.header.make_header(email.header.decode_header(msg.get('Subject', '')))
                    subj = str(subject)
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            ctype = part.get_content_type()
                            if ctype == 'text/plain':
                                body = part.get_payload(decode=True).decode(errors='ignore')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors='ignore')

                    text = f"{subj}\n{body}"
                    # Примитивные триггеры
                    if re.search(r"уволен|увольнение|последний рабочий день", text, flags=re.IGNORECASE):
                        dt = extract_date(text) or (now_tz())
                        # Если дата указана без времени — 16:00 локального времени
                        run_dt = dt.astimezone(TZ).replace(hour=16, minute=0, second=0, microsecond=0)
                        # Попробуем извлечь ФИО
                        # Ищем формулировки вроде: Сотрудник: Иванов Иван Иванович (sam: i.ivanov)
                        m = re.search(r"sam\s*[:=]\s*([a-z0-9_.-]+)", text, re.IGNORECASE)
                        sam = m.group(1) if m else None
                        if not sam:
                            # fallback: достаём строку вида «Иванов Иван», потом ищем в AD
                            m = re.search(r"([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)", text)
                            name_q = m.group(1) if m else None
                            if name_q:
                                cands = await ad_search_candidates(name_q)
                                sam = cands[0].SamAccountName if cands else None
                        if sam:
                            schedule_disable_job(sam, run_dt, created_by=SUPERADMIN_ID or 0, meta={"source": "email"})
                            log.info("IMAP: запланирована блокировка %s на %s", sam, run_dt)
            M.logout()
        except Exception as e:
            log.exception("IMAP poll error: %s", e)
        await asyncio.sleep(IMAP_POLL_SECONDS)


# --------- Telegram: хэндлеры ---------
async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if is_admin(user.id):
        await update.message.reply_text("Готов к работе. Введите задачу свободной фразой или /help.")
    else:
        await update.message.reply_text("Доступ ограничен. Попросите супер-админа выдать права.")


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    await update.message.reply_text(
        """Команды:
 - Свободный текст: «Смени пароль Устиновой Наталье», «Заблокируй Иванова 05.09.2025»
 - /whoami — показать ваш id и роль
 - /super — меню супер-админа (только SUPER)
 - /jobs — показать будущие задачи
"""
    )


async def whoami_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    role = "superadmin" if is_superadmin(uid) else ("admin" if is_admin(uid) else "user")
    await update.message.reply_text(f"Ваш id: {uid}\nРоль: {role}")


async def jobs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    with db() as conn:
        rows = conn.execute("SELECT id, job_type, sAMAccountName, run_at, status FROM jobs WHERE status='SCHEDULED' ORDER BY run_at").fetchall()
    if not rows:
        await update.message.reply_text("Нет запланированных задач.")
        return
    lines = [f"#{r['id']} {r['job_type']} {r['sAMAccountName']} → {r['run_at']}"]
    await update.message.reply_text("\n".join(lines))


# ----- СУПЕР-АДМИН МЕНЮ -----
async def super_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_user.id):
        await update.message.reply_text("Только для супер-админа.")
        return
    kb = [
        [InlineKeyboardButton("Добавить админа", callback_data="super:add")],
        [InlineKeyboardButton("Удалить админа", callback_data="super:del")],
        [InlineKeyboardButton("Показать админов", callback_data="super:list")],
    ]
    await update.message.reply_text("Меню супер-админа:", reply_markup=InlineKeyboardMarkup(kb))


async def super_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_superadmin(q.from_user.id):
        await q.edit_message_text("Только для супер-админа.")
        return
    action = q.data.split(":", 1)[1]
    if action == "list":
        with db() as conn:
            rows = conn.execute("SELECT user_id FROM admins ORDER BY user_id").fetchall()
        ids = ", ".join(str(r["user_id"]) for r in rows) or "(пусто)"
        await q.edit_message_text(f"Админы: {ids}")
    elif action in ("add", "del"):
        ctx.user_data["super_action"] = action
        await q.edit_message_text("Отправьте числовой ID пользователя для изменения роли.")


async def super_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_user.id):
        return
    action = ctx.user_data.get("super_action")
    if not action:
        return
    try:
        uid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Нужно число — Telegram user id.")
        return
    with db() as conn:
        if action == "add":
            conn.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (uid,))
            conn.commit()
            await update.message.reply_text(f"Добавлен админ {uid}")
        else:
            conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
            conn.commit()
            await update.message.reply_text(f"Удалён админ {uid}")
    audit(update.effective_user.id, f"super:{action}", details={"target": uid})
    ctx.user_data.pop("super_action", None)


# ----- СВОБОДНЫЙ ТЕКСТ (NLU) -----
async def free_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    txt = update.message.text.strip()
    intent = detect_intent(txt)
    if intent == "reset_password":
        await handle_reset_password(update, ctx, txt)
    elif intent == "disable_account":
        await handle_disable(update, ctx, txt)
    else:
        await update.message.reply_text("Не понял запрос. Пример: ‘Смени пароль Устиновой Наталье’.")


async def handle_reset_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    name_q = extract_name_query(text)
    if not name_q:
        await update.message.reply_text("Кого именно? Укажите фамилию и имя.")
        return
    cands = await ad_search_candidates(name_q)
    if not cands:
        await update.message.reply_text("Пользователь не найден.")
        return
    if len(cands) == 1:
        await confirm_reset_flow(update, ctx, cands[0])
        return
    # Выбор из кандидатов
    kb = []
    for u in cands[:10]:
        label = f"{u.DisplayName} / {u.SamAccountName}"
        kb.append([InlineKeyboardButton(label[:60], callback_data=f"reset:{u.SamAccountName}")])
    await update.message.reply_text("Найдено несколько, уточните:", reply_markup=InlineKeyboardMarkup(kb))


async def confirm_reset_flow(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user: ADUser):
    new_pwd = generate_password(12)
    try:
        out = await ad_reset_password(user.SamAccountName, new_pwd, True)
        audit(update.effective_user.id, "reset_password", target=user.SamAccountName)
        # По умолчанию пароль не показываем. Дадим кнопку «Показать».
        kb = [[InlineKeyboardButton("Показать пароль", callback_data=f"showpwd:{user.SamAccountName}:{new_pwd}")]]
        await update.message.reply_text(
            f"Пароль для {user.DisplayName} ({user.SamAccountName}) сброшен. Пользователю будет предложена смена при входе.",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    except Exception as e:
        log.exception("reset error: %s", e)
        await update.message.reply_text("Ошибка при смене пароля. Подробности в логах.")


async def reset_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.edit_message_text("Недостаточно прав.")
        return
    if q.data.startswith("reset:"):
        sam = q.data.split(":", 1)[1]
        # Получим пользователя ради красивого имени
        cands = await ad_search_candidates(sam)
        u = next((x for x in cands if x.SamAccountName.lower() == sam.lower()), None)
        if not u:
            u = ADUser(SamAccountName=sam, DisplayName=sam, DistinguishedName="", Enabled=True)
        await confirm_reset_flow(update, ctx, u)
    elif q.data.startswith("showpwd:"):
        # Показываем пароль только инициатору
        _tag, sam, pwd = q.data.split(":", 2)
        await q.edit_message_text(f"Учётка: {sam}\nПароль: {pwd}")


async def handle_disable(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    name_q = extract_name_query(text) or text
    when = extract_date(text)
    # Если даты нет — считаем сегодня 16:00
    if not when:
        when = now_tz()
    run_dt = when.astimezone(TZ).replace(hour=16, minute=0, second=0, microsecond=0)

    cands = await ad_search_candidates(name_q)
    if not cands:
        await update.message.reply_text("Пользователь не найден.")
        return
    if len(cands) > 1:
        kb = []
        for u in cands[:10]:
            label = f"{u.DisplayName} / {u.SamAccountName}"
            kb.append([InlineKeyboardButton(label[:60], callback_data=f"disablesel:{u.SamAccountName}:{int(run_dt.timestamp())}")])
        await update.message.reply_text("Уточните пользователя для блокировки:", reply_markup=InlineKeyboardMarkup(kb))
        return
    u = cands[0]
    schedule_disable_job(u.SamAccountName, run_dt, update.effective_user.id, meta={"source": "chat"})
    audit(update.effective_user.id, "schedule_disable", target=u.SamAccountName, details={"when": run_dt.isoformat()})
    await update.message.reply_text(f"Запланирована блокировка {u.DisplayName} в {run_dt.strftime('%d.%m.%Y %H:%M')}.")


async def disable_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.edit_message_text("Недостаточно прав.")
        return
    if q.data.startswith("disablesel:"):
        _tag, sam, ts = q.data.split(":", 2)
        run_dt = datetime.fromtimestamp(int(ts), tz=TZ)
        schedule_disable_job(sam, run_dt, q.from_user.id, meta={"source": "chat"})
        audit(q.from_user.id, "schedule_disable", target=sam, details={"when": run_dt.isoformat()})
        await q.edit_message_text(f"Запланирована блокировка {sam} в {run_dt.strftime('%d.%m.%Y %H:%M')}.")


# --------- bootstrap ---------
async def on_startup(app):
    init_db()
    scheduler.start()
    await restore_jobs_on_startup()
    # фоновый опрос почты
    app.create_task(imap_poll_loop(app))


def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_TOKEN not set")

    application = ApplicationBuilder().token(token).concurrent_updates(True).build()

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("whoami", whoami_cmd))
    application.add_handler(CommandHandler("jobs", jobs_cmd))

    # супер-меню и обработка ввода ID
    application.add_handler(CommandHandler("super", super_cmd))
    application.add_handler(CallbackQueryHandler(super_cb, pattern=r"^super:"))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), super_text))

    # сброс пароля / блокировка — коллбэки
    application.add_handler(CallbackQueryHandler(reset_cb, pattern=r"^(reset:|showpwd:)"))
    application.add_handler(CallbackQueryHandler(disable_cb, pattern=r"^disablesel:"))

    # свободный текст как fallback
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), free_text))

    application.post_init = on_startup

    log.info("Bot starting as @%s", application.bot.username if application.bot else "")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
