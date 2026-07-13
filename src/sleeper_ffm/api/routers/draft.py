"""FastAPI router — draft board and pick recommendation."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

log = logging.getLogger(__name__)

router = APIRouter(prefix="/draft", tags=["draft"])


@router.get("/board")
def draft_board(top: int = 50, season: int = 2024) -> dict:
    """Return the live draft board: board state + top available players.

    Combines veteran nflverse FPAR with rookie Sleeper search_rank heuristic.
    Expensive on first call (scores nflverse weekly data). Cached after first run
    until the process restarts.
    """
    from sleeper_ffm.draft.assistant import build_full_pool, sync_board
    from sleeper_ffm.model.dynasty import value_player

    try:
        board = sync_board()
    except Exception as exc:
        log.exception("draft board sync failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    pool = build_full_pool(board, seasons=[season])

    players = [
        {
            "player_id": p.player_id,
            "name": p.name,
            "position": p.position,
            "age": p.age,
            "team": p.team,
            "fpar": p.current_fpar,
            "dynasty_value": value_player(p),
            "is_rookie": p.is_taxi,
        }
        for p in pool[:top]
    ]

    return {
        "status": "complete" if board.is_complete() else "active",
        "current_pick": board.current_pick_no,
        "total_picks": board.total_picks,
        "current_round": board.current_round,
        "my_slot": board.my_slot,
        "picks_until_my_turn": board.picks_until_my_turn,
        "next_my_pick": board.next_my_pick,
        "players": players,
    }


@router.get("/prompt")
def draft_prompt(top: int = 25, season: int = 2024) -> dict:
    """Generate a Claude Code prompt for the current pick decision."""
    from sleeper_ffm.draft.assistant import build_full_pool, build_pick_prompt, sync_board

    try:
        board = sync_board()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if board.is_complete():
        raise HTTPException(status_code=409, detail="Draft is complete")

    pool = build_full_pool(board, seasons=[season])
    prompt = build_pick_prompt(board, pool, top_n=top)
    return {"prompt": prompt, "pick_number": board.current_pick_no}
