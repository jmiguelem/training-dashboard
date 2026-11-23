"""Weekly auto-run: sync Whoop and Garmin, then write the coming week's plan. Manual sync stays available."""
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config
from .analysis import coach
from .db import get_db
from .garmin.sync import sync_garmin
from .whoop.sync import sync_whoop

log = logging.getLogger("scheduler")
JOB_ID = "weekly"
_lock = threading.Lock()


def run_weekly_job() -> dict:
    """Never raises: each step's outcome is recorded so the header can show what failed."""
    if not _lock.acquire(blocking=False):
        return {"skipped": "already running"}
    started = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        log_id = conn.execute(
            "INSERT INTO sync_log (source, started_at, status) VALUES ('scheduled', ?, 'running')",
            (started,),
        ).lastrowid
    result: dict = {}
    try:
        for name, fn in (("whoop", sync_whoop), ("garmin", sync_garmin)):
            try:
                result[name] = fn()
            except Exception as exc:
                log.warning("scheduled %s sync failed: %s", name, exc)
                result[name] = {"error": str(exc)[:200]}
        try:
            coach.weekly_summary(force=False)
            result["plan"] = "ok"
        except Exception as exc:
            log.warning("scheduled plan failed: %s", exc)
            result["plan"] = {"error": str(exc)[:200]}
    finally:
        failed = [k for k, v in result.items() if isinstance(v, dict) and "error" in v]
        status = "ok" if not failed else ("error" if len(failed) == len(result) else "partial")
        with get_db() as conn:
            conn.execute(
                "UPDATE sync_log SET finished_at=?, status=?, detail=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), status, json.dumps(result), log_id),
            )
        _lock.release()
    return result


DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def last_fire_time(now: datetime | None = None) -> datetime:
    """The most recent moment the weekly job was due (local time)."""
    now = now or datetime.now().astimezone()
    idx = DAYS.index(config.AUTO_SYNC_DAY[:3].lower())
    due = now.replace(hour=config.AUTO_SYNC_HOUR, minute=config.AUTO_SYNC_MINUTE, second=0, microsecond=0)
    due -= timedelta(days=(now.weekday() - idx) % 7)
    return due - timedelta(days=7) if due > now else due


def _missed_last_run(now: datetime | None = None) -> bool:
    """True if the app has been used before but the last scheduled run never happened (Mac was off or asleep)."""
    due = last_fire_time(now)
    with get_db() as conn:
        used = conn.execute("SELECT 1 FROM sync_log WHERE status IN ('ok', 'partial') LIMIT 1").fetchone()
        rows = conn.execute(
            "SELECT started_at FROM sync_log WHERE source = 'scheduled' AND status IN ('ok', 'partial')"
        ).fetchall()
    if not used:
        return False
    for r in rows:
        t = datetime.fromisoformat(r["started_at"])
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if t >= due:
            return False
    return True


def start() -> BackgroundScheduler | None:
    if not config.AUTO_SYNC:
        return None
    sched = BackgroundScheduler()
    sched.add_job(
        run_weekly_job,
        CronTrigger(
            day_of_week=config.AUTO_SYNC_DAY, hour=config.AUTO_SYNC_HOUR, minute=config.AUTO_SYNC_MINUTE
        ),
        id=JOB_ID,
        misfire_grace_time=6 * 3600,
        coalesce=True,
        max_instances=1,
    )
    sched.start()
    if _missed_last_run():
        log.info("the last scheduled weekly run did not happen, catching up now")
        threading.Thread(target=run_weekly_job, daemon=True).start()
    return sched


def next_run(sched: BackgroundScheduler | None) -> str | None:
    if not sched:
        return None
    job = sched.get_job(JOB_ID)
    return job.next_run_time.isoformat() if job and job.next_run_time else None
