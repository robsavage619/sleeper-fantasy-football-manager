"""FastAPI router — draft board and pick recommendation."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, PREFERRED_VALUE_SEASON

log = logging.getLogger(__name__)

router = APIRouter(prefix="/draft", tags=["draft"])


def _decision_card(players: list[dict], picks_until: int | None) -> dict | None:
    """Build the first-screen draft decision card from the ranked board.

    When picks_until is a known, positive number, the recommendation targets the
    best player LIKELY TO SURVIVE to that actual turn — not just the #1 overall
    name, which may be long gone by then. The true #1 overall is still surfaced
    in the reason text for context (e.g. for a trade-up decision).
    """
    if not players:
        return None

    overall_best = players[0]
    # "Realistically gone" / "risky" mirror prompts.draft._survival_signal's bands
    # (1-indexed rank <= picks_until -> GONE?, <= picks_until*1.6 -> RISKY).
    if picks_until and picks_until > 0:
        target_idx = next(
            (i for i, _ in enumerate(players) if (i + 1) > picks_until * 1.6),
            0,
        )
    else:
        target_idx = 0
    primary = players[target_idx]
    alternatives = players[target_idx + 1 : target_idx + 4]
    alt_gap = (
        round(primary["dynasty_value"] - alternatives[0]["dynasty_value"], 1)
        if alternatives
        else 0.0
    )
    if picks_until is None:
        urgency = "BOARD"
    elif picks_until == 0:
        urgency = "ON_CLOCK"
    elif picks_until <= 3:
        urgency = "MONITOR"
    else:
        urgency = "BOARD"

    survival_note = (
        f" {overall_best['name']} is the true #1 overall but {picks_until} picks happen "
        f"first and won't likely survive to your turn."
        if target_idx > 0
        else ""
    )
    reason = (
        f"Best value realistically available at your actual turn: {primary['position']} "
        f"with {primary['fpar']:.1f} FPAR; {alt_gap:+.1f} value gap over next option."
        f"{survival_note}"
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
            else f"Draft order not yet set — {primary['name']} is the top target once it is."
            if picks_until is None
            else f"Hold board; {primary['name']} is the realistic target "
            f"at your turn ({picks_until} picks away)."
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
    Expensive on first call (scores nflverse weekly data); the veteran valuation
    is then TTL-cached, so the frontend's poll does not re-score it every time.
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
    from sleeper_ffm.market.blend import FC_TO_DYNASTY_SCALE, FC_TO_FPAR_SCALE

    try:
        from sleeper_ffm.market.fantasycalc import fetch as _fc_fetch

        market_values = _fc_fetch()
    except Exception:
        log.warning("draft board: FC market fetch failed; STEAL/REACH signals disabled")
        market_values = {}

    # College context for the incoming class. Rookies dominate a dynasty rookie
    # draft board and carry no NFL production, so without this their rows are the
    # emptiest on the screen you are actually drafting from.
    try:
        from sleeper_ffm.cfbd.loader import college_context

        college_by_id = college_context()
    except Exception as exc:
        log.warning("draft board: college context unavailable (%s)", exc)
        college_by_id = {}

    players = []
    for p in pool[:top]:
        # STEAL/REACH compares age-adjusted dynasty value (not age-blind current
        # FPAR) against the market on the same scale, so old producers are not
        # systematically flagged STEAL and young ascenders REACH.
        dv = value_player(p)
        fc_raw = market_values.get(p.player_id)
        market_fpar = round(fc_raw / FC_TO_FPAR_SCALE, 1) if fc_raw is not None else None
        diff_pct = None
        signal = "HOLD"
        if fc_raw is not None:
            market_dv = fc_raw * FC_TO_DYNASTY_SCALE
            if market_dv > 0:
                diff_pct = round((dv - market_dv) / market_dv * 100, 1)
                if diff_pct > 20:
                    signal = "STEAL"
                elif diff_pct < -25:
                    signal = "REACH"
        college = college_by_id.get(p.player_id) or {}
        players.append(
            {
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
                "college": college.get("college"),
                "college_usage_rate": college.get("usage_rate"),
                "recruiting_rank": college.get("recruiting_rank"),
                "recruiting_stars": college.get("stars"),
            }
        )

    warnings = []
    if season != PREFERRED_VALUE_SEASON:
        warnings.append(
            f"Using valuation season {season}; preferred season "
            f"{PREFERRED_VALUE_SEASON} is unavailable locally."
        )
    if not market_values:
        warnings.append("FantasyCalc market unavailable; STEAL/REACH signals disabled.")
    if not board.order_confirmed and not board.is_complete():
        if board.order_projected:
            warnings.append(
                f"Sleeper has not officially set the draft order — my_slot below is a "
                f"projection from this league's verified reverse-standings convention "
                f"(source: {board.projection_source_season} final standings), not yet "
                "Sleeper-confirmed."
            )
        else:
            warnings.append(
                "Sleeper has not yet set/randomized the draft order, and no standings-based "
                "projection was available — my_slot, next_my_pick, and picks_until_my_turn "
                "are unknown."
            )

    if board.owned_pick_numbers and len(board.owned_pick_numbers) != board.total_rounds:
        owned_rounds = sorted({(n - 1) // board.total_teams + 1 for n in board.owned_pick_numbers})
        warnings.append(
            f"You hold {len(board.owned_pick_numbers)} of {board.total_rounds} picks "
            f"(rounds {', '.join(str(r) for r in owned_rounds)}); the rest changed hands "
            "in trades. Countdown and survival targeting use your real picks only."
        )

    if board.is_complete():
        status = "complete"
    elif not board.order_confirmed:
        status = "pre_draft"
    else:
        status = "active"

    return {
        "status": status,
        "order_projected": board.order_projected,
        "projection_source_season": board.projection_source_season,
        "current_pick": board.current_pick_no,
        "total_picks": board.total_picks,
        "current_round": board.current_round,
        "my_slot": board.my_slot,
        "picks_until_my_turn": board.picks_until_my_turn,
        "next_my_pick": board.next_my_pick,
        "my_pick_numbers": board.my_pick_numbers,
        "data_quality": "DEGRADED" if warnings else "FULL",
        "warnings": warnings,
        "recommendation": _decision_card(players, board.picks_until_my_turn),
        "players": players,
    }
