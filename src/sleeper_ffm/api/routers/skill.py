"""Skill router — True Owner Skill Index."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter

from sleeper_ffm.model.owner_skill import build_owner_skill

router = APIRouter(prefix="/owners", tags=["owners"])
log = logging.getLogger(__name__)


@router.get("/skill")
def owner_skill() -> list[dict]:
    """Return the True Owner Skill Index for every GM in the league."""
    results = build_owner_skill()
    return [dataclasses.asdict(r) for r in results]
