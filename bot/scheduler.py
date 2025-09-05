from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
from zoneinfo import ZoneInfo
from ad.ad_client import disable_user
from db.database import DB, TZ

scheduler = AsyncIOScheduler(timezone=TZ)

def schedule_disable_job(sam, run_dt, created_by, meta=None):
    DB.execute(
        "INSERT INTO jobs(sam,run_ts,created_by,meta) VALUES (?,?,?,?)",
        (sam, int(run_dt.timestamp()), created_by, json.dumps(meta or {})),
    )
    DB.commit()
    scheduler.add_job(
        disable_user,
        trigger=DateTrigger(run_date=run_dt),
        args=[sam],
        id=f"disable:{sam}:{int(run_dt.timestamp())}",
        replace_existing=True,
    )

async def restore_jobs_on_startup():
    rows = DB.execute("SELECT sam, run_ts FROM jobs").fetchall()
    for sam, ts in rows:
        run_dt = datetime.fromtimestamp(ts, tz=TZ)
        scheduler.add_job(
            disable_user,
            trigger=DateTrigger(run_date=run_dt),
            args=[sam],
            id=f"disable:{sam}:{ts}",
            replace_existing=True,
        )
