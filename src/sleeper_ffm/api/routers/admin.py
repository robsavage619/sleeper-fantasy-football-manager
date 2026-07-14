"""Admin router — one-button data refresh, freshness status, and the AI briefing.

``POST /admin/refresh`` kicks a background job that force-refetches every data
source (Sleeper players + league/rosters, nflverse weekly + snaps, FantasyCalc)
and then flushes the in-process TTL caches so the next request sees fresh data.
Each source is isolated: one failure is recorded but does not abort the rest.

``GET /admin/refresh/status`` returns the job state plus per-source freshness
read cheaply from file mtimes (never by re-fetching).

``GET /ai/briefing`` returns the single master briefing prompt + its JSON schema.
"""

from __future__ import annotations

import datetime
import importlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from sleeper_ffm.config import (
    CACHE_DIR,
    DATA_DIR,
    NFLVERSE_DIR,
    PREFERRED_VALUE_SEASON,
    cached_weekly_seasons,
)
from sleeper_ffm.market import fantasycalc
from sleeper_ffm.nflverse import loader
from sleeper_ffm.prompts.master import (
    MASTER_SCHEMA,
    build_master_briefing,
    gather_briefing_context,
)
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

_PLAYERS_CACHE = CACHE_DIR / "players_nfl.json"
_SNAPS_PARQUET = NFLVERSE_DIR / "snaps.parquet"
_FANTASYCALC_LATEST = DATA_DIR / "market" / "fantasycalc_latest.json"

# Module-level job state, guarded by a lock so concurrent refreshes are rejected.
_JOB: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "sources": {},
}
_JOB_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


# --- per-source refresh functions (module-level so tests can monkeypatch) ------


def _refresh_sleeper() -> dict[str, Any]:
    """Force-refetch the Sleeper player dump plus league + rosters."""
    with SleeperClient() as c:
        players = c.players(force=True)
        league = c.league()
        rosters = c.rosters()
    return {"players": len(players), "rosters": len(rosters), "league": league.name}


def _refresh_nflverse() -> dict[str, Any]:
    """Force-refetch nflverse weekly (value season) + snap counts."""
    weekly = loader.load_weekly(seasons=[PREFERRED_VALUE_SEASON], force=True)
    snaps = loader.load_snaps(force=True)
    return {"weekly_rows": len(weekly), "snap_rows": len(snaps), "season": PREFERRED_VALUE_SEASON}


def _refresh_fantasycalc(archive_date: str) -> dict[str, Any]:
    """Force-refetch FantasyCalc and archive a timestamped snapshot for history.

    Args:
        archive_date: ``YYYYMMDD`` string used to name the archived snapshot.
    """
    data = fantasycalc._fetch_fresh()
    latest = fantasycalc._cache_path()
    latest.write_text(json.dumps(data))
    archive = latest.parent / f"fantasycalc_{archive_date}.json"
    archive.write_text(json.dumps(data))
    return {"entries": len(data), "archive": archive.name}


def _clear_caches() -> None:
    """Flush the in-process TTL caches after new data lands.

    ``sleeper_ffm.cache`` ships in a sibling analytics workstream; it is imported
    dynamically so this router works in checkouts where that module is not yet
    present. Absence raises loudly and is recorded in the job's source results.
    """
    importlib.import_module("sleeper_ffm.cache").clear_all()


def _run_refresh() -> None:
    """Run every source, isolate failures, then flush caches. Called in the background."""
    archive_date = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    sources: dict[str, Any] = {}
    steps: list[tuple[str, Any]] = [
        ("sleeper", _refresh_sleeper),
        ("nflverse", _refresh_nflverse),
        ("fantasycalc", lambda: _refresh_fantasycalc(archive_date)),
        ("cache_clear", _clear_caches),
    ]
    for name, fn in steps:
        try:
            result = fn()
            sources[name] = {"ok": True, "detail": result, "refreshed_at": _now_iso()}
            log.info("refresh: %s ok — %s", name, result)
        except Exception as exc:
            sources[name] = {"ok": False, "error": str(exc), "refreshed_at": _now_iso()}
            log.error("refresh: %s failed: %s", name, exc)

    all_ok = all(s["ok"] for s in sources.values())
    with _JOB_LOCK:
        _JOB["sources"] = sources
        _JOB["finished_at"] = _now_iso()
        _JOB["status"] = "done" if all_ok else "error"


def _file_freshness(path: Path) -> dict[str, Any]:
    """Cheap freshness read from a file's stat — mtime as ISO, existence flag."""
    if not path.exists():
        return {"exists": False, "mtime": None}
    mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.UTC).isoformat()
    return {"exists": True, "mtime": mtime}


@router.post("/admin/refresh")
def refresh(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Kick a background refresh of all data sources. Rejects a concurrent run with 409."""
    with _JOB_LOCK:
        if _JOB["status"] == "running":
            raise HTTPException(status_code=409, detail="refresh already running")
        _JOB["status"] = "running"
        _JOB["started_at"] = _now_iso()
        _JOB["finished_at"] = None
        _JOB["sources"] = {}
        started_at = _JOB["started_at"]
    background_tasks.add_task(_run_refresh)
    return {"status": "running", "started_at": started_at}


@router.get("/admin/refresh/status")
def refresh_status() -> dict[str, Any]:
    """Return job state plus per-source freshness (file mtimes, cheap coverage)."""
    with _JOB_LOCK:
        job = {
            "status": _JOB["status"],
            "started_at": _JOB["started_at"],
            "finished_at": _JOB["finished_at"],
            "sources": dict(_JOB["sources"]),
        }
    weekly_fresh = _file_freshness(NFLVERSE_DIR / "weekly" / f"{PREFERRED_VALUE_SEASON}.parquet")
    weekly_fresh["cached_seasons"] = cached_weekly_seasons()
    freshness = {
        "sleeper_players": _file_freshness(_PLAYERS_CACHE),
        "nflverse_weekly": weekly_fresh,
        "nflverse_snaps": _file_freshness(_SNAPS_PARQUET),
        "fantasycalc": _file_freshness(_FANTASYCALC_LATEST),
    }
    return {"job": job, "freshness": freshness}


@router.get("/ai/briefing", tags=["ai"])
def ai_briefing() -> dict[str, Any]:
    """Return the single master briefing prompt and the JSON schema Claude must return."""
    context = gather_briefing_context()
    prompt = build_master_briefing(context, generated_at=_now_iso())
    return {"prompt": prompt, "schema": MASTER_SCHEMA}
