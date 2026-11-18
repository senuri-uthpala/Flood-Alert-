import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from .config import REFRESH_MINUTES
from .database import SessionLocal
from .services import refresh_all

log = logging.getLogger("floodalert.scheduler")
_scheduler: BackgroundScheduler | None = None


def _job():
    db = SessionLocal()
    try:
        refresh_all(db)
    except Exception:
        log.exception("Scheduled refresh failed")
    finally:
        db.close()


def start():
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Colombo")
    # run once right away so the map is populated, then every REFRESH_MINUTES
    _scheduler.add_job(_job, "interval", minutes=REFRESH_MINUTES, next_run_time=datetime.now(),
                       max_instances=1, coalesce=True)
    _scheduler.start()
    log.info("Scheduler started (every %d min)", REFRESH_MINUTES)


def stop():
    if _scheduler:
        _scheduler.shutdown(wait=False)
