"""Waiver blind test — would the engine have worked the wire better than the managers?

The arena scores lineup decisions; this scores the other weekly decision a GM makes: who
to pick up. Same discipline — replay the league's real history, rank blind, score on what
actually happened.

Ground truth, again from Sleeper with no synthesis: every completed ``add`` in the season's
transactions is a player who was genuinely available on the wire that week (someone rostered
him, so he cleared waivers), and once rostered his weekly points appear in the matchup feed.
So the realized value of any pickup is knowable: the fantasy points he went on to score over
the next few weeks, scored under this league's exact settings.

The test, per week:

* **candidates** — every player added by any manager that week. A real, known-available pool.
* rank them **blind** with the engine's projector (only weeks before the pickup), take the
  top ``k``.
* score each candidate by his **realized** points over the next ``horizon`` weeks.

Three numbers fall out: the engine's top-``k`` realized value, the pool mean (what a *random*
add returns — the no-skill baseline), and the best-possible top-``k`` (hindsight ceiling). The
headline is the **ranking capture**::

    capture = (engine_topk - pool_mean) / (optimal_topk - pool_mean)

0.0 means the engine's ordering is no better than picking a name at random; 1.0 means it
perfectly identified the best pickups on the board. It isolates *ranking skill* from how good
the week's waiver crop happened to be.

Leakage discipline mirrors the arena: the projector sees only a ``PointHistory`` of earlier
weeks, and the realized-value window is strictly *after* the pickup week.

Honest limits
-------------
* Only players who were actually added are scored — a gem nobody in the league picked up is
  invisible here. This measures ranking *among the adds that happened*, not gem-discovery in
  the full free-agent ocean (that needs nflverse scoring of never-rostered players; a later
  pass). So the pool is realistic but not exhaustive.
* A pickup dropped again before he produced scores 0 realized value — which is the honest
  outcome of a bad add, so it is left as 0 rather than excluded.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass

from sleeper_ffm.evals.arena import (
    ArenaUnavailableError,
    PointHistory,
    _extend_history,
    _player_positions,
    _resolve_league_id,
    make_engine_projector,
)

log = logging.getLogger(__name__)

_DEFAULT_MIN_WEEK = 3
_DEFAULT_HORIZON = 4
_DEFAULT_TOP_K = 3
# Positions worth evaluating on the wire. K/DEF churn heavily and add noise; the ranking
# question is most meaningful for the skill positions the engine actually forecasts.
_SCOREABLE = frozenset({"QB", "RB", "WR", "TE"})


@dataclass
class WaiverResult:
    """Aggregate waiver-ranking verdict for one season."""

    season: int
    league_id: str
    n_weeks: int
    n_candidates: int
    horizon: int
    top_k: int
    engine_value: float  # mean next-`horizon` points of the engine's top-k picks
    pool_mean_value: float  # mean of a random add (the no-skill baseline)
    optimal_value: float  # mean of the best-possible top-k (hindsight ceiling)
    capture: float  # (engine - pool) / (optimal - pool); 0 = random, 1 = perfect
    weeks_engine_beat_pool: int

    def summary(self) -> str:
        """One-line verdict."""
        return (
            f"{self.season} waivers: engine top-{self.top_k} adds returned "
            f"{self.engine_value:.1f} pts over the next {self.horizon} wks vs "
            f"{self.pool_mean_value:.1f} for a random add (ceiling {self.optimal_value:.1f}); "
            f"ranking capture {self.capture:.0%} "
            f"({self.weeks_engine_beat_pool}/{self.n_weeks} weeks beat random)"
        )


def rank_and_score(
    candidates: list[str],
    projections: dict[str, float],
    realized: dict[str, float],
    top_k: int,
) -> tuple[float, float, float] | None:
    """Score one week's waiver ranking: (engine top-k, pool mean, optimal top-k).

    Pure and leak-free by contract: ``projections`` are blind, ``realized`` is the future.
    They are only ever combined here, never inside the projector.

    Args:
        candidates: Available player ids this week.
        projections: Blind projected value per candidate (higher = ranked first).
        realized: Actual future points per candidate.
        top_k: How many top-ranked picks to average.

    Returns:
        ``(engine_topk_mean, pool_mean, optimal_topk_mean)``, or None if the pool is too
        small to form a top-k and a distinct random baseline.
    """
    scored = [c for c in candidates if c in realized]
    if len(scored) <= top_k:
        return None
    by_projection = sorted(scored, key=lambda c: projections.get(c, 0.0), reverse=True)
    by_realized = sorted(scored, key=lambda c: realized[c], reverse=True)

    engine_topk = statistics.mean(realized[c] for c in by_projection[:top_k])
    optimal_topk = statistics.mean(realized[c] for c in by_realized[:top_k])
    pool_mean = statistics.mean(realized[c] for c in scored)
    return engine_topk, pool_mean, optimal_topk


def run_waiver_arena(
    season: int,
    horizon: int = _DEFAULT_HORIZON,
    top_k: int = _DEFAULT_TOP_K,
    min_week: int = _DEFAULT_MIN_WEEK,
    league_id: str | None = None,
) -> WaiverResult:
    """Replay a season's waiver wire blind and score the engine's pickup ranking.

    Args:
        season: Completed season to replay.
        horizon: Weeks of realized points that count toward a pickup's value.
        top_k: How many top-ranked candidates the engine "adds" each week.
        min_week: First pickup week scored (earlier weeks warm the history).
        league_id: Override the league.

    Returns:
        A :class:`WaiverResult`.

    Raises:
        ArenaUnavailableError: League/matchups/transactions unavailable, or no week had a
            scorable candidate pool.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        lid = league_id or _resolve_league_id(client, season)
        if lid is None:
            raise ArenaUnavailableError(f"no league in this dynasty's history for season {season}")
        positions = _player_positions(client)
        proj = make_engine_projector(season)

        # Realized points per (player, week) from every roster's matchup feed, and the
        # completed adds per week from transactions.
        points_by_week: dict[int, dict[str, float]] = {}
        adds_by_week: dict[int, set[str]] = {}
        max_week = 18
        for week in range(1, max_week + 1):
            try:
                matchups = client.matchups(week, league_id=lid)
                txns = client.transactions(week, league_id=lid)
            except Exception as exc:
                log.warning("waiver: %s week %s unavailable: %s", season, week, exc)
                matchups, txns = [], []
            if matchups:
                points_by_week[week] = {
                    pid: float(p)
                    for r in matchups
                    for pid, p in (r.get("players_points") or {}).items()
                    if pid
                }
            adds_by_week[week] = _completed_adds(txns)

        # Rank each week off a history that accumulates strictly-earlier weeks only, so the
        # blind ranking never sees the week it is picking for.
        engine_vals: list[float] = []
        pool_vals: list[float] = []
        optimal_vals: list[float] = []
        n_candidates = 0
        weeks_beat = 0
        blind_history = PointHistory()
        for week in range(1, max_week + 1):
            if week >= min_week and week + horizon <= max_week:
                candidates = [
                    pid for pid in adds_by_week.get(week, set()) if positions.get(pid) in _SCOREABLE
                ]
                realized = {
                    pid: sum(
                        points_by_week.get(w, {}).get(pid, 0.0)
                        for w in range(week + 1, week + 1 + horizon)
                    )
                    for pid in candidates
                }
                projections = proj(week, candidates, positions, blind_history)
                scored = rank_and_score(candidates, projections, realized, top_k)
                if scored is not None:
                    engine_v, pool_v, optimal_v = scored
                    engine_vals.append(engine_v)
                    pool_vals.append(pool_v)
                    optimal_vals.append(optimal_v)
                    n_candidates += len(candidates)
                    weeks_beat += engine_v > pool_v
            if week in points_by_week:
                _extend_history(blind_history, [{"players_points": points_by_week[week]}])

    if not engine_vals:
        raise ArenaUnavailableError(f"no scorable waiver weeks for season {season}")
    engine_mean = statistics.mean(engine_vals)
    pool_mean = statistics.mean(pool_vals)
    optimal_mean = statistics.mean(optimal_vals)
    spread = optimal_mean - pool_mean
    return WaiverResult(
        season=season,
        league_id=lid,
        n_weeks=len(engine_vals),
        n_candidates=n_candidates,
        horizon=horizon,
        top_k=top_k,
        engine_value=round(engine_mean, 2),
        pool_mean_value=round(pool_mean, 2),
        optimal_value=round(optimal_mean, 2),
        capture=round((engine_mean - pool_mean) / spread, 4) if spread > 0 else 0.0,
        weeks_engine_beat_pool=weeks_beat,
    )


def _completed_adds(txns: list[dict]) -> set[str]:
    """Player ids added via a completed waiver/free-agent transaction this week."""
    out: set[str] = set()
    for t in txns:
        if t.get("status") == "complete" and t.get("adds"):
            out.update(str(pid) for pid in t["adds"])
    return out
