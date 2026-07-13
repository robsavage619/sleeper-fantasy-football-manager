"""FastAPI router — draft board and pick recommendation."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, PREFERRED_VALUE_SEASON

log = logging.getLogger(__name__)

router = APIRouter(prefix="/draft", tags=["draft"])


def _decision_card(players: list[dict], picks_until: int) -> dict | None:
    """Build the first-screen draft decision card from the ranked board."""
    if not players:
        return None
    primary = players[0]
    alternatives = players[1:4]
    alt_gap = (
        round(primary["dynasty_value"] - alternatives[0]["dynasty_value"], 1)
        if alternatives
        else 0.0
    )
    urgency = "ON_CLOCK" if picks_until == 0 else "MONITOR" if picks_until <= 3 else "BOARD"
    reason = (
        f"Top remaining dynasty value at {primary['position']} with "
        f"{primary['fpar']:.1f} FPAR; {alt_gap:+.1f} value gap over next option."
    )
    return {
        "player_id": primary["player_id"],
        "name": primary["name"],
        "position": primary["position"],
        "team": primary["team"],
        "dynasty_value": primary["dynasty_value"],
        "urgency": urgency,
        "reason": reason,
        "action": (
            f"Draft {primary['name']} in Sleeper."
            if picks_until == 0
            else f"Hold board; {primary['name']} is current top target."
        ),
        "alternatives": [
            {
                "player_id": player["player_id"],
                "name": player["name"],
                "position": player["position"],
                "dynasty_value": player["dynasty_value"],
            }
            for player in alternatives
        ],
    }


@router.get("/board")
def draft_board(top: int = 50, season: int = DEFAULT_VALUE_SEASON) -> dict:
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

    # Fetch FC market values for steal/reach signals (non-fatal if unavailable).
    try:
        from sleeper_ffm.market.fantasycalc import fetch as _fc_fetch
        from sleeper_ffm.market.blend import _FC_TO_FPAR_SCALE  # type: ignore[attr-defined]

        _FC_TO_FPAR_SCALE = 78.0  # local shadow in case import path changes
        market_values = _fc_fetch()
    except Exception:
        market_values = {}

    players = []
    for p in pool[:top]:
        dv = value_player(p)
        fc_raw = market_values.get(p.player_id)
        market_fpar = round(fc_raw / 78.0, 1) if fc_raw is not None else None
        diff_pct = None
        signal = "HOLD"
        if market_fpar is not None and market_fpar > 0:
            # Compare annual FPAR vs market annual FPAR (not discounted DV vs annual).
            diff_pct = round((p.current_fpar - market_fpar) / market_fpar * 100, 1)
            if diff_pct > 20:
                signal = "STEAL"
            elif diff_pct < -25:
                signal = "REACH"
        players.append({
            "player_id": p.player_id,
            "name": p.name,
            "position": p.position,
            "age": p.age,
            "team": p.team,
            "fpar": p.current_fpar,
            "dynasty_value": dv,
            "is_rookie": p.is_taxi,
            "market_fpar": market_fpar,
            "divergence_pct": diff_pct,
            "signal": signal,
        })

    warnings = []
    if season != PREFERRED_VALUE_SEASON:
        warnings.append(
            f"Using valuation season {season}; preferred season "
            f"{PREFERRED_VALUE_SEASON} is unavailable locally."
        )

    return {
        "status": "complete" if board.is_complete() else "active",
        "current_pick": board.current_pick_no,
        "total_picks": board.total_picks,
        "current_round": board.current_round,
        "my_slot": board.my_slot,
        "picks_until_my_turn": board.picks_until_my_turn,
        "next_my_pick": board.next_my_pick,
        "data_quality": "DEGRADED" if warnings else "FULL",
        "warnings": warnings,
        "recommendation": _decision_card(players, board.picks_until_my_turn),
        "players": players,
    }


@router.get("/prompt")
def draft_prompt(top: int = 25, season: int = DEFAULT_VALUE_SEASON) -> dict:
    """Generate a Claude Code prompt for the current pick decision."""
    from sleeper_ffm.draft.assistant import build_full_pool, build_pick_prompt, sync_board

    try:
        board = sync_board()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if board.is_complete():
        raise HTTPException(status_code=409, detail="Draft is complete")

    pool = build_full_pool(board, seasons=[season])

    try:
        from sleeper_ffm.market.fantasycalc import fetch as _fc_fetch
        market_values = _fc_fetch()
    except Exception:
        market_values = {}

    prompt = build_pick_prompt(board, pool, top_n=top, market_values=market_values)
    return {"prompt": prompt, "pick_number": board.current_pick_no}
