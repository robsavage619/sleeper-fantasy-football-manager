"""Owners router — behavioral profiles for every dynasty GM."""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter

from sleeper_ffm.model.owner_profile import build_owner_profiles

router = APIRouter(prefix="/owners", tags=["owners"])


@router.get("/profiles")
def get_owner_profiles() -> list[dict]:
    """Return a behavioral profile for every owner in the league."""
    return [dataclasses.asdict(p) for p in build_owner_profiles()]
