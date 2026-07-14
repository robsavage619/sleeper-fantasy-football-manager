"""FastAPI router — pick market analysis."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter

from sleeper_ffm.model.pick_market import analyze_pick_market

router = APIRouter(prefix="/picks", tags=["picks"])
log = logging.getLogger(__name__)


@router.get("/market")
def pick_market() -> list[dict]:
    """Pick accumulation arbitrage signals."""
    signals = analyze_pick_market()
    return [dataclasses.asdict(s) for s in signals]


@router.get("/class-strength")
def draft_class_strength() -> list[dict]:
    """Market-implied strength of each upcoming rookie class (refreshed from FantasyCalc)."""
    from sleeper_ffm.model.draft_class import build_draft_class_strength

    return [dataclasses.asdict(c) for c in build_draft_class_strength()]
