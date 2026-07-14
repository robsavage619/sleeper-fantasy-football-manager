"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sleeper_ffm.api.routers import actions as actions_router
from sleeper_ffm.api.routers import admin as admin_router
from sleeper_ffm.api.routers import contention as contention_router
from sleeper_ffm.api.routers import dossier as dossier_router
from sleeper_ffm.api.routers import draft as draft_router
from sleeper_ffm.api.routers import evals as evals_router
from sleeper_ffm.api.routers import findings as findings_router
from sleeper_ffm.api.routers import gameday as gameday_router
from sleeper_ffm.api.routers import gm_address as gm_address_router
from sleeper_ffm.api.routers import handcuff as handcuff_router
from sleeper_ffm.api.routers import history as history_router
from sleeper_ffm.api.routers import intel as intel_router
from sleeper_ffm.api.routers import league as league_router
from sleeper_ffm.api.routers import mispricing as mispricing_router
from sleeper_ffm.api.routers import negotiation as negotiation_router
from sleeper_ffm.api.routers import offers as offers_router
from sleeper_ffm.api.routers import owners as owners_router
from sleeper_ffm.api.routers import picks as picks_router
from sleeper_ffm.api.routers import players as players_router
from sleeper_ffm.api.routers import prospects as prospects_router
from sleeper_ffm.api.routers import regression as regression_router
from sleeper_ffm.api.routers import roster as roster_router
from sleeper_ffm.api.routers import sabermetrics as sabermetrics_router
from sleeper_ffm.api.routers import schedule_strength as schedule_strength_router
from sleeper_ffm.api.routers import scoreboard as scoreboard_router
from sleeper_ffm.api.routers import season as season_router
from sleeper_ffm.api.routers import season_sim as season_sim_router
from sleeper_ffm.api.routers import skill as skill_router
from sleeper_ffm.api.routers import stadium as stadium_router
from sleeper_ffm.api.routers import trades as trades_router
from sleeper_ffm.api.routers import wire_watch as wire_watch_router
from sleeper_ffm.reasoning.findings import load_findings_from_disk
from sleeper_ffm.schedule.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    load_findings_from_disk()
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="sleeper-ffm",
        description="AI dynasty fantasy football GM — Sleeper-aware, scoring-driven.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(league_router.router)
    app.include_router(findings_router.router)
    app.include_router(owners_router.router)
    app.include_router(players_router.router)
    app.include_router(dossier_router.router)
    app.include_router(history_router.router)
    app.include_router(draft_router.router)
    app.include_router(evals_router.router)
    app.include_router(prospects_router.router)
    app.include_router(trades_router.router)
    app.include_router(roster_router.router)
    app.include_router(season_router.router)
    app.include_router(picks_router.router)
    app.include_router(skill_router.router)
    app.include_router(actions_router.router)
    app.include_router(offers_router.router)
    app.include_router(sabermetrics_router.players_router)
    app.include_router(sabermetrics_router.owners_router)
    app.include_router(admin_router.router)
    app.include_router(intel_router.router)
    app.include_router(mispricing_router.router)
    app.include_router(stadium_router.router)
    app.include_router(schedule_strength_router.router)
    app.include_router(season_sim_router.router)
    app.include_router(contention_router.router)
    app.include_router(regression_router.router)
    app.include_router(handcuff_router.router)
    app.include_router(scoreboard_router.router)
    app.include_router(negotiation_router.router)
    app.include_router(gm_address_router.router)
    app.include_router(wire_watch_router.router)
    app.include_router(gameday_router.router)
    return app


app = create_app()
