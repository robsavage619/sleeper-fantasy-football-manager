"""Trade retrospective — did the engine pick the right side, blind?

The third decision surface. For every real trade in league history, we know which players
each side received and — from the matchup feed after the trade — exactly how many fantasy
points those players went on to score. So the realized winner of a trade (on immediate
production) is knowable. The test: does the engine's *as-of-then* valuation prefer the side
that actually produced more?

Per trade in week ``W``:

* split the received players by side (from the transaction's ``adds``),
* score each side's **realized** value = points its received players scored in weeks after
  ``W`` this season,
* score each side's **blind** value = the engine projector's per-game estimate at week ``W``
  (only earlier weeks), summed over received players,
* the engine is *correct* when the side it valued higher is the side that produced more.

Aggregated as a hit-rate against a 50% coin flip, with an exact sign-test p-value.

What this is NOT
----------------
This is a **win-now production** lens, and it is honest about that:

* **Draft picks are excluded from value.** A rebuilder who trades a veteran for picks looks
  like he "lost" on rest-of-season points even when the pick haul is the better dynasty
  asset. So a miss here is not necessarily a bad trade — it may be a rebuild the horizon
  can't see. The hit-rate is a floor on the engine's read of on-field value, not a verdict
  on dynasty trade IQ.
* **Only the trade season counts.** Multi-year value from acquired youth is invisible.
* **Small sample.** ~10-16 scorable trades per season, so every number ships with a sign-test
  p-value and should be read as suggestive, never as a headline claim.

Leakage discipline: the projector sees only weeks before the trade; realized value is read
strictly after it.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

from sleeper_ffm.evals.arena import (
    ArenaUnavailableError,
    PointHistory,
    _extend_history,
    _player_positions,
    _resolve_league_id,
    make_engine_projector,
)

log = logging.getLogger(__name__)

_MAX_WEEK = 18
_SCOREABLE = frozenset({"QB", "RB", "WR", "TE", "K", "DEF"})


@dataclass
class TradeScore:
    """One trade's blind-preference vs realized-production outcome."""

    season: int
    week: int
    roster_a: int
    roster_b: int
    engine_pref: int  # roster_id the engine valued higher
    realized_winner: int  # roster_id that actually produced more
    correct: bool


@dataclass
class TradeRetroResult:
    """Aggregate trade-side accuracy over one or more seasons."""

    seasons: tuple[int, ...]
    n_trades: int
    engine_correct: int
    correct_rate: float
    sign_test_pvalue: float
    trades: list[TradeScore] = field(default_factory=list)

    def summary(self) -> str:
        """One-line verdict."""
        seasons = "/".join(str(s) for s in self.seasons)
        return (
            f"{seasons} trades: engine picked the more-productive side "
            f"{self.engine_correct}/{self.n_trades} ({self.correct_rate:.0%}), "
            f"p={self.sign_test_pvalue} (win-now lens, picks excluded)"
        )


def score_trade(
    received: dict[int, list[str]],
    projected: dict[str, float],
    realized: dict[str, float],
) -> tuple[int, int, bool] | None:
    """Score one trade: (engine-preferred side, realized winner, whether they match).

    Pure and leak-free: ``projected`` is blind, ``realized`` is the future, combined only
    here. Returns None for a trade that can't be adjudicated (fewer than two sides that
    received a scoreable player, or a realized tie).

    Args:
        received: ``{roster_id: [received player ids]}`` — exactly two sides.
        projected: Blind per-player value at trade time.
        realized: Actual post-trade points per player.

    Returns:
        ``(engine_pref_roster, realized_winner_roster, correct)`` or None.
    """
    sides = [rid for rid, players in received.items() if any(p in realized for p in players)]
    if len(sides) != 2:
        return None
    a, b = sides
    proj_a = sum(projected.get(p, 0.0) for p in received[a])
    proj_b = sum(projected.get(p, 0.0) for p in received[b])
    real_a = sum(realized.get(p, 0.0) for p in received[a])
    real_b = sum(realized.get(p, 0.0) for p in received[b])
    if real_a == real_b or proj_a == proj_b:
        return None  # no adjudicable winner / no engine preference
    engine_pref = a if proj_a > proj_b else b
    realized_winner = a if real_a > real_b else b
    return engine_pref, realized_winner, engine_pref == realized_winner


def run_trade_retro(
    seasons: tuple[int, ...] = (2022, 2023, 2024),
    league_id: str | None = None,
) -> TradeRetroResult:
    """Replay every trade across the given seasons and score the engine's side preference.

    Args:
        seasons: Completed seasons to include (pooled for the sign test).
        league_id: Override the league for a single season; ignored for multi-season runs.

    Returns:
        A :class:`TradeRetroResult`.

    Raises:
        ArenaUnavailableError: No scorable trade in any requested season.
    """
    from sleeper_ffm.evals.stats import sign_test_pvalue

    all_trades: list[TradeScore] = []
    for season in seasons:
        lid = league_id if (league_id and len(seasons) == 1) else None
        all_trades.extend(_score_season_trades(season, lid))

    if not all_trades:
        raise ArenaUnavailableError(f"no scorable trades in seasons {seasons}")
    correct = sum(1 for t in all_trades if t.correct)
    n = len(all_trades)
    return TradeRetroResult(
        seasons=seasons,
        n_trades=n,
        engine_correct=correct,
        correct_rate=round(correct / n, 4),
        sign_test_pvalue=sign_test_pvalue(correct, n),
        trades=all_trades,
    )


def _score_season_trades(season: int, league_id: str | None) -> list[TradeScore]:
    """Score every completed trade in one season."""
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        lid = league_id or _resolve_league_id(client, season)
        if lid is None:
            log.warning("trade_retro: no league for season %s", season)
            return []
        positions = _player_positions(client)
        proj = make_engine_projector(season)

        points_by_week: dict[int, dict[str, float]] = {}
        trades_by_week: dict[int, list[dict]] = {}
        for week in range(1, _MAX_WEEK + 1):
            try:
                matchups = client.matchups(week, league_id=lid)
                txns = client.transactions(week, league_id=lid)
            except Exception as exc:
                log.warning("trade_retro: %s week %s unavailable: %s", season, week, exc)
                matchups, txns = [], []
            if matchups:
                points_by_week[week] = {
                    pid: float(p)
                    for r in matchups
                    for pid, p in (r.get("players_points") or {}).items()
                    if pid
                }
            trades_by_week[week] = [
                t for t in txns if t.get("type") == "trade" and t.get("status") == "complete"
            ]

    out: list[TradeScore] = []
    blind_history = PointHistory()
    for week in range(1, _MAX_WEEK + 1):
        for trade in trades_by_week.get(week, []):
            scored = _score_one(season, week, trade, positions, points_by_week, proj, blind_history)
            if scored is not None:
                out.append(scored)
        if week in points_by_week:
            _extend_history(blind_history, [{"players_points": points_by_week[week]}])
    return out


def _score_one(
    season: int,
    week: int,
    trade: dict,
    positions: dict[str, str],
    points_by_week: dict[int, dict[str, float]],
    projector,
    history: PointHistory,
) -> TradeScore | None:
    """Adjudicate a single trade, or None if it can't be scored."""
    received: dict[int, list[str]] = {}
    for pid, rid in (trade.get("adds") or {}).items():
        if positions.get(str(pid)) in _SCOREABLE:
            received.setdefault(int(rid), []).append(str(pid))
    if len(received) < 2:
        return None

    all_players = [p for players in received.values() for p in players]
    realized = {
        pid: sum(points_by_week.get(w, {}).get(pid, 0.0) for w in range(week + 1, _MAX_WEEK + 1))
        for pid in all_players
    }
    projected = projector(week, all_players, positions, history)

    result = score_trade(received, projected, realized)
    if result is None:
        return None
    engine_pref, realized_winner, correct = result
    sides = sorted(received)
    return TradeScore(
        season=season,
        week=week,
        roster_a=sides[0],
        roster_b=sides[1],
        engine_pref=engine_pref,
        realized_winner=realized_winner,
        correct=correct,
    )


def mean_hit_rate(results: list[TradeRetroResult]) -> float:
    """Convenience: pooled hit-rate across several season results."""
    trades = [t for r in results for t in r.trades]
    if not trades:
        return 0.0
    return round(statistics.mean(1.0 if t.correct else 0.0 for t in trades), 4)
