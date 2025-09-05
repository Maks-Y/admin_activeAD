import asyncio, email, imaplib, logging, os
from datetime import datetime
from scheduler import schedule_disable_job
from ai.nlp import parse_hr_mail
from db.database import TZ

async def start_mail_checker():
    host, user, pwd = os.getenv("IMAP_HOST"), os.getenv("IMAP_USER"), os.getenv("IMAP_PASS")
    if not all([host, user, pwd]):
        logging.info("IMAP disabled")
        return
    while True:
        try:
            with imaplib.IMAP4_SSL(host) as M:
                M.login(user, pwd)
                M.select(os.getenv("IMAP_FOLDER", "INBOX"))
                typ, data = M.search(None, "UNSEEN")
                for num in data[0].split():
                    typ, msg_data = M.fetch(num, "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])
                    msg_id = msg.get("Message-ID", num.decode())
                    logging.info("Processing mail %s", msg_id)
                    fio, date = parse_hr_mail(msg)
                    if fio and date:
                        run_dt = date.replace(hour=16, minute=0, second=0, tzinfo=TZ)
                        schedule_disable_job(fio, run_dt, created_by=0, meta={"source": "mail"})
                        M.store(num, "+FLAGS", "\\Seen")
                        logging.info("Processed mail %s", msg_id)
        except Exception:
            logging.exception("IMAP poll error")
        await asyncio.sleep(int(os.getenv("IMAP_POLL_SECONDS", "300")))
