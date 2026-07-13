"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sleeper_ffm.api.routers import dossier as dossier_router
from sleeper_ffm.api.routers import draft as draft_router
from sleeper_ffm.api.routers import findings as findings_router
from sleeper_ffm.api.routers import history as history_router
from sleeper_ffm.api.routers import league as league_router
from sleeper_ffm.api.routers import owners as owners_router
from sleeper_ffm.api.routers import picks as picks_router
from sleeper_ffm.api.routers import prospects as prospects_router
from sleeper_ffm.api.routers import roster as roster_router
from sleeper_ffm.api.routers import season as season_router
from sleeper_ffm.api.routers import skill as skill_router
from sleeper_ffm.api.routers import trades as trades_router
from sleeper_ffm.reasoning.findings import load_findings_from_disk


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    load_findings_from_disk()
    yield


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
    app.include_router(dossier_router.router)
    app.include_router(history_router.router)
    app.include_router(draft_router.router)
    app.include_router(prospects_router.router)
    app.include_router(trades_router.router)
    app.include_router(roster_router.router)
    app.include_router(season_router.router)
    app.include_router(picks_router.router)
    app.include_router(skill_router.router)
    return app


app = create_app()
