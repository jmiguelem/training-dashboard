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


def _missed_last_run() -> bool:
    """True if we have synced before but nothing succeeded in the last 8 days (Mac was off on Sunday)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT MAX(started_at) AS t FROM sync_log WHERE status IN ('ok', 'partial')"
        ).fetchone()
    if not row or not row["t"]:
        return False
    last = datetime.fromisoformat(row["t"])
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last > timedelta(days=8)


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
        log.info("last successful sync is over 8 days old, catching up now")
        threading.Thread(target=run_weekly_job, daemon=True).start()
    return sched


def next_run(sched: BackgroundScheduler | None) -> str | None:
    if not sched:
        return None
    job = sched.get_job(JOB_ID)
    return job.next_run_time.isoformat() if job and job.next_run_time else None
