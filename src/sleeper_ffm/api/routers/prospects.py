"""FastAPI router — CFBD dynasty prospect scouting board."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

log = logging.getLogger(__name__)

router = APIRouter(prefix="/draft", tags=["draft"])


@router.get("/prospects")
def draft_prospects(year: int = 2025, top: int = 50) -> list[dict]:
    """Return top dynasty prospects scored from CFBD college data.

    Args:
        year: Draft class year (2025 or 2026).
        top: Number of prospects to return (default 50).
    """
    from sleeper_ffm.cfbd.loader import load_prospects

    try:
        profiles = load_prospects(year=year, top=top)
    except Exception as exc:
        log.exception("load_prospects failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return [dataclasses.asdict(p) for p in profiles]


@router.get("/prospects/scouting-prompts")
def prospect_scouting_prompts_batch(
    year: int = 2026,
    top: int = 50,
    offset: int = 0,
    limit: int = 8,
) -> dict:
    """Batch scouting-prompt generator for the whole draft board.

    Enumerates ``load_prospects(year, top)`` and returns the deep-dive scouting prompt for
    a bounded slice ``[offset : offset+limit]``, so an orchestrator can page through the
    entire board and deep-scout every prospect without an N+1 of per-name calls. ``limit``
    is capped (each item assembles a multi-source report) to keep a request bounded.

    Returns ``{year, total, offset, count, prompts: [{player_id, name, position, college,
    dynasty_prospect_score, prompt}]}``.
    """
    from sleeper_ffm.cfbd.loader import load_prospects
    from sleeper_ffm.model.prospect_report import build_scouting_prompt

    limit = max(1, min(limit, 12))
    try:
        board = load_prospects(year=year, top=top)
    except Exception as exc:
        log.exception("load_prospects failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    window = board[offset : offset + limit]
    prompts: list[dict] = []
    for p in window:
        try:
            prompt = build_scouting_prompt(
                name=p.name,
                position=p.position,
                college=p.college,
                year=p.year,
                age=p.age,
                player_id=p.player_id,
                recruiting_rank=p.recruiting_rank,
                stars=p.stars,
                dynasty_prospect_score=p.dynasty_prospect_score,
            )
        except Exception as exc:  # one bad prospect must not sink the page
            log.warning("scouting prompt failed for %s: %s", p.name, exc)
            prompt = f"(degraded — scouting prompt for {p.name} unavailable: {exc})"
        prompts.append(
            {
                "player_id": p.player_id,
                "name": p.name,
                "position": p.position,
                "college": p.college,
                "dynasty_prospect_score": p.dynasty_prospect_score,
                "prompt": prompt,
            }
        )
    return {
        "year": year,
        "total": len(board),
        "offset": offset,
        "count": len(prompts),
        "prompts": prompts,
    }


@router.get("/prospects/scouting")
def prospect_scouting(
    name: str,
    position: str,
    college: str = "",
    year: int = 2025,
    age: float | None = None,
    player_id: str | None = None,
    recruiting_rank: int | None = None,
    stars: int | None = None,
    dynasty_prospect_score: float = 0.0,
) -> dict:
    """Return the full multi-source scouting report for one prospect.

    Assembles FantasyCalc market consensus, NFL draft capital, combine
    athleticism, CFBD college production (when a key is set), roster fit, and
    derived signals. Degrades gracefully — missing layers are absent, not fatal.

    Args:
        name: Prospect's full name (used for combine/CFBD name matching).
        position: QB, RB, WR, or TE.
        college: School name.
        year: Draft class year.
        age: Prospect's age, if known.
        player_id: Sleeper player id — used to match FantasyCalc market data.
        recruiting_rank: National recruiting rank, if known.
        stars: Recruiting star rating, if known.
        dynasty_prospect_score: This app's 0-100 heuristic score.
    """
    from sleeper_ffm.model.prospect_report import build_scouting_report

    try:
        return build_scouting_report(
            name=name,
            position=position,
            college=college,
            year=year,
            age=age,
            player_id=player_id,
            recruiting_rank=recruiting_rank,
            stars=stars,
            dynasty_prospect_score=dynasty_prospect_score,
        )
    except Exception as exc:
        log.exception("build_scouting_report failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/prospects/scouting-prompt")
def prospect_scouting_prompt(
    name: str,
    position: str,
    college: str = "",
    year: int = 2025,
    age: float | None = None,
    player_id: str | None = None,
    recruiting_rank: int | None = None,
    stars: int | None = None,
    dynasty_prospect_score: float = 0.0,
) -> dict:
    """Generate the deep-dive AI scouting prompt (NFL comps + team fit) for Claude Code."""
    from sleeper_ffm.model.prospect_report import build_scouting_prompt

    try:
        prompt = build_scouting_prompt(
            name=name,
            position=position,
            college=college,
            year=year,
            age=age,
            player_id=player_id,
            recruiting_rank=recruiting_rank,
            stars=stars,
            dynasty_prospect_score=dynasty_prospect_score,
        )
    except Exception as exc:
        log.exception("build_scouting_prompt failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"prompt": prompt}
