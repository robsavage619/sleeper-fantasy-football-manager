"""FastAPI router - recommendation quality evals."""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Query

from sleeper_ffm.evals.recommendations import build_recommendation_eval

router = APIRouter(prefix="/evals", tags=["evals"])


@router.get("/recommendations")
def recommendation_evals(top: int = Query(default=8, ge=1, le=30)) -> dict:
    """Return a non-mutating recommendation quality scorecard."""
    return dataclasses.asdict(build_recommendation_eval(top=top))
