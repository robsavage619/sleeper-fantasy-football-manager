"""In-process scheduler that keeps real-world status flowing in on a cadence.

Runs inside the FastAPI process (started/stopped by the app lifespan). Two jobs:

- **status refresh** (cheap): re-pull the Sleeper dump — injuries, depth chart,
  news timestamps — and bust the intel-feed cache. Runs several times a day plus
  NFL game-day windows (Sunday around when inactives post ~90 min pre-kickoff,
  Thursday/Monday nights), because injury designations move intraday.
- **full refresh** (heavy): the complete data rebuild (nflverse + FantasyCalc +
  players + cache flush), once a week after Monday-night football.

All cron times are US Eastern — the timezone NFL injury/inactive news runs on.
Disabled automatically under pytest, and via ``SFFM_SCHEDULER=0``.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_TZ = ZoneInfo("America/New_York")
_scheduler: Any = None


def _refresh_status() -> None:
    """Light refresh: re-pull the Sleeper dump and bust the intel-feed cache."""
    try:
        from sleeper_ffm.api.routers.admin import _refresh_sleeper, record_status_refresh
        from sleeper_ffm.model import news_feed

        result = _refresh_sleeper()
        news_feed._players.cache_clear()  # type: ignore[attr-defined]
        record_status_refresh(result)
        log.info("scheduled status refresh ok: %s", result)
    except Exception as exc:
        log.error("scheduled status refresh failed: %s", exc)


def _refresh_full() -> None:
    """Heavy weekly refresh: nflverse + FantasyCalc + players, guarded by the job lock."""
    try:
        from sleeper_ffm.api.routers import admin

        with admin._JOB_LOCK:
            if admin._JOB["status"] == "running":
                log.info("scheduled full refresh skipped — a refresh is already running")
                return
            admin._JOB["status"] = "running"
            admin._JOB["started_at"] = admin._now_iso()
            admin._JOB["finished_at"] = None
            admin._JOB["sources"] = {}
        admin._run_refresh()
        log.info("scheduled full refresh complete")
    except Exception as exc:
        log.error("scheduled full refresh failed: %s", exc)


def _disabled() -> bool:
    return os.getenv("SFFM_SCHEDULER", "1") == "0" or bool(os.getenv("PYTEST_CURRENT_TEST"))


def start_scheduler() -> Any:
    """Start the in-process scheduler (idempotent). Returns the scheduler or None."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if _disabled():
        log.info("in-process scheduler disabled (env)")
        return None

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BackgroundScheduler(timezone=_TZ)
    opts = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 3600}

    # Cheap injury/depth/news refresh — daily windows...
    sched.add_job(
        _refresh_status,
        CronTrigger(hour="7,12,17", timezone=_TZ),
        id="status_daily",
        **opts,
    )
    # ...plus NFL game-day windows (Sunday inactives + TNF/MNF nights).
    sched.add_job(
        _refresh_status,
        CronTrigger(day_of_week="sun", hour="9,11,15", timezone=_TZ),
        id="status_sunday",
        **opts,
    )
    sched.add_job(
        _refresh_status,
        CronTrigger(day_of_week="thu,mon", hour=17, timezone=_TZ),
        id="status_gameday",
        **opts,
    )
    # Heavy full rebuild weekly, Tuesday morning (after MNF, before the new week).
    sched.add_job(
        _refresh_full,
        CronTrigger(day_of_week="tue", hour=6, timezone=_TZ),
        id="full_weekly",
        **opts,
    )

    sched.start()
    _scheduler = sched
    log.info("in-process scheduler started (%d jobs)", len(sched.get_jobs()))
    return sched


def stop_scheduler() -> None:
    """Stop the scheduler if running (called on app shutdown)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_info() -> dict[str, Any]:
    """Observability: whether the scheduler is on and when each job next fires."""
    if _scheduler is None:
        return {"enabled": False, "jobs": []}
    jobs = [
        {
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        }
        for job in _scheduler.get_jobs()
    ]
    return {"enabled": True, "timezone": str(_TZ), "jobs": jobs}
