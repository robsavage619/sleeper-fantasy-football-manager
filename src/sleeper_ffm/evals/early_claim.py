"""Early-claim retro — would the engine have flagged a breakout before a rival grabbed him?

The waiver arena (:mod:`sleeper_ffm.evals.waiver_arena`) ranks only players someone actually
added — it can't say whether the engine saw a gem *before* the league did. This module
reconstructs the full free-agent ocean at every week of a season (every skill player in the
league's box scores that season, minus whoever any manager rostered that week) and asks two
sharper questions:

1. **Anticipation** — of every value-producing pickup a *rival* made, did the engine's blind
   top-``k`` watchlist flag that player in some earlier week, before the rival claimed him? If
   so, how many weeks of lead time, and how many points did the rival get that were already on
   the engine's radar?
2. **My-roster counterfactual** — each week, if the engine's top pool pick had been claimed in
   place of the worst-projected bench skill player on ``MY_ROSTER_ID``'s actual historical
   roster, how many more points would the blind engine-selected lineup have scored over the
   next few weeks?

Both questions reuse the arena's leakage discipline: the projector only ever sees a
:class:`~sleeper_ffm.evals.arena.PointHistory` of strictly earlier weeks, and every "realized"
number is read after the fact.

Free-agent universe
--------------------
The pool is not the entire ~11,000-player Sleeper dump (mostly retired players, practice-squad
names, and guys who never touched the field) — it is every player who has an nflverse
regular-season box-score row *that season*, restricted to QB/RB/WR/TE (the positions the
engine forecasts). That is exactly the set the projector can meaningfully rank; anyone else
would project near zero from an empty history and add nothing but noise.

Realized points for a pool player
----------------------------------
Sleeper's ``players_points`` is authoritative whenever a player was actually rostered that
week (identical scoring, ground truth). For weeks nobody rostered him, we fall back to
nflverse box scores re-scored under this league's settings
(:func:`~sleeper_ffm.model.valuation.score_weekly`) — the same source the forecast itself
trains on, so no new scoring logic is introduced.

Honest simplifications
-----------------------
* The counterfactual is **per-week independent**: it does not chain roster evolution across
  weeks (a claimed player isn't "kept" into next week's counterfactual). Each week asks "what
  if you'd made *this* swap and held it for the horizon," in addition to whatever you actually
  did — not "what would your season have looked like." A genuinely great pickup may therefore
  get counted more than once across nearby weeks; that is a known bias toward the honest
  headline finding, not against it.
* Lineup selection across the horizon reuses the **claim week's** blind projection rather than
  re-projecting fresh each future week — avoiding an expensive re-run of the forecast for every
  (claim week, horizon week) pair. Over a 4-week horizon this is a minor staleness, not a
  leakage risk (it is still strictly historical).
* The random-``k`` baseline for anticipation is computed **analytically** (an independent draw
  each week), not simulated, so results are deterministic and reproducible.
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
    select_lineup,
)

log = logging.getLogger(__name__)

_DEFAULT_MIN_WEEK = 3
_DEFAULT_MAX_WEEK = 17
_DEFAULT_HORIZON = 4
_DEFAULT_TOP_K = 10
_DEFAULT_VALUE_TOP_N = 25
_SCOREABLE = frozenset({"QB", "RB", "WR", "TE"})
_TXN_TYPES = frozenset({"waiver", "free_agent"})


# --- pure pieces ----------------------------------------------------------------------


def free_agent_pool(universe: frozenset[str], rostered: set[str]) -> list[str]:
    """Everyone in the season's skill-position universe not on any roster that week."""
    return [pid for pid in universe if pid not in rostered]


def realized_points(
    pid: str,
    week: int,
    points_by_week: dict[int, dict[str, float]],
    nflverse_points: dict[tuple[str, int], float],
    sleeper_to_gsis: dict[str, str],
) -> float:
    """A player's league-scored points that week: Sleeper's if he was rostered, else nflverse.

    Sleeper's ``players_points`` is the ground truth whenever it exists; nflverse fills in
    only for weeks nobody rostered him, which is the entire point of a free-agent-ocean pool.
    """
    sleeper_val = points_by_week.get(week, {}).get(pid)
    if sleeper_val is not None:
        return sleeper_val
    gsis = sleeper_to_gsis.get(pid)
    if gsis is None:
        return 0.0
    return nflverse_points.get((gsis, week), 0.0)


def counterfactual_week_points(
    roster_players: list[str],
    dropped_pid: str,
    added_pid: str,
    positions: dict[str, str],
    roster_positions: list[str],
    projected: dict[str, float],
    realized: dict[str, float],
) -> tuple[float, float]:
    """Realized lineup points for the actual roster vs. one swap, same blind projection.

    Returns ``(baseline_pts, mutated_pts)`` — the realized points of the blind
    engine-selected lineup from the roster as it actually was, and from the roster with
    ``dropped_pid`` swapped for ``added_pid``. Both lineups are chosen with the same
    ``projected`` scores, so the only thing that differs is which players were available to
    select from.
    """
    baseline_ids = select_lineup(
        {pid: projected.get(pid, 0.0) for pid in roster_players}, positions, roster_positions
    )
    mutated_players = [p for p in roster_players if p != dropped_pid] + [added_pid]
    mutated_ids = select_lineup(
        {pid: projected.get(pid, 0.0) for pid in mutated_players}, positions, roster_positions
    )
    baseline_pts = sum(realized.get(pid, 0.0) for pid in baseline_ids)
    mutated_pts = sum(realized.get(pid, 0.0) for pid in mutated_ids)
    return baseline_pts, mutated_pts


def select_best_add(
    watchlist: list[str],
    roster_players: list[str],
    dropped_pid: str,
    positions: dict[str, str],
    roster_positions: list[str],
    projected: dict[str, float],
) -> str | None:
    """Which watchlist candidate helps the PROJECTED lineup the most if swapped in.

    A blind decision using only ``projected`` scores, never realized ones. Picking the
    single raw-highest-scoring watchlist name is the wrong move in a 1QB
    league: free-agent QBs routinely out-project a bench RB/WR by raw points, but almost
    never out-project an established starting QB into the lineup, so that swap does
    nothing. This instead tries every watchlist candidate and keeps whichever one
    actually raises the projected lineup total — the closest analog to "which of these
    names would the engine actually have told you to add."

    Returns:
        The best candidate's id, or None if nothing on the watchlist improves the
        projected lineup at all.
    """
    baseline_ids = select_lineup(
        {pid: projected.get(pid, 0.0) for pid in roster_players}, positions, roster_positions
    )
    baseline_proj = sum(projected.get(pid, 0.0) for pid in baseline_ids)
    best_pid: str | None = None
    best_gain = 0.0
    for cand in watchlist:
        mutated_players = [p for p in roster_players if p != dropped_pid] + [cand]
        mutated_ids = select_lineup(
            {pid: projected.get(pid, 0.0) for pid in mutated_players}, positions, roster_positions
        )
        gain = sum(projected.get(pid, 0.0) for pid in mutated_ids) - baseline_proj
        if gain > best_gain:
            best_gain = gain
            best_pid = cand
    return best_pid


def random_anticipation_prob(
    pool_size_by_week: dict[int, int], min_week: int, claim_week: int, top_k: int
) -> float:
    """P(an independent random top-``k`` draw each week would have flagged the player first).

    The analytic no-skill baseline: each week before ``claim_week`` is treated as an
    independent draw of ``top_k`` names from that week's pool, so the chance he was *never*
    drawn is ``prod(1 - top_k/pool_size)`` and this returns the complement.
    """
    weeks = [w for w in range(min_week, claim_week) if pool_size_by_week.get(w)]
    if not weeks:
        return 0.0
    miss_prob = 1.0
    for w in weeks:
        size = pool_size_by_week[w]
        miss_prob *= max(0.0, 1.0 - top_k / size)
    return 1.0 - miss_prob


@dataclass
class StolenPickup:
    """A rival's value add the engine had already flagged before he claimed it."""

    player_id: str
    rival_roster_id: int
    claim_week: int
    first_flagged_week: int
    lead_weeks: int
    realized_value: float


@dataclass
class MissedPickup:
    """A rival's value add the engine's watchlist never flagged before the claim."""

    player_id: str
    rival_roster_id: int
    claim_week: int
    realized_value: float


def join_anticipation(
    value_adds: list[tuple[str, int, int, float]],
    watchlist_first_seen: dict[str, int],
) -> tuple[list[StolenPickup], list[MissedPickup]]:
    """Split rival value-adds into ones the engine flagged before the claim, and ones it missed.

    Pure join: ``value_adds`` is ``(player_id, claim_week, rival_roster_id, realized_value)``;
    ``watchlist_first_seen`` is the first week each player appeared in the engine's blind
    top-``k`` watchlist. A player only counts as anticipated if flagged strictly before the
    week he was actually claimed — a same-week flag is too late to act on.
    """
    stolen: list[StolenPickup] = []
    missed: list[MissedPickup] = []
    for pid, week, rid, value in value_adds:
        flagged_week = watchlist_first_seen.get(pid)
        if flagged_week is not None and flagged_week < week:
            stolen.append(
                StolenPickup(pid, rid, week, flagged_week, week - flagged_week, round(value, 2))
            )
        else:
            missed.append(MissedPickup(pid, rid, week, round(value, 2)))
    return stolen, missed


# --- aggregate result -------------------------------------------------------------------


@dataclass
class EarlyClaimResult:
    """Anticipation + my-roster counterfactual verdict for one season."""

    season: int
    league_id: str
    horizon: int
    top_k: int
    n_value_adds: int
    n_anticipated: int
    anticipation_rate: float
    baseline_rate: float
    median_lead_weeks: float
    stolen_points: float
    stolen: list[StolenPickup] = field(default_factory=list)
    missed: list[MissedPickup] = field(default_factory=list)
    n_counterfactual_weeks: int = 0
    counterfactual_mean_gain: float = 0.0
    counterfactual_ci: tuple[float, float] = (0.0, 0.0)

    def summary(self) -> str:
        """One-line verdict."""
        lo, hi = self.counterfactual_ci
        return (
            f"{self.season} early claims: engine flagged {self.n_anticipated}/{self.n_value_adds} "
            f"rival value adds before the claim ({self.anticipation_rate:.0%} vs "
            f"{self.baseline_rate:.0%} random-{self.top_k} baseline), median lead "
            f"{self.median_lead_weeks:.0f} wks, {self.stolen_points:.0f} stolen pts; "
            f"claiming the top pick over your worst bench spot would have added "
            f"{self.counterfactual_mean_gain:+.2f} pts/wk [95% CI {lo:+.2f}, {hi:+.2f}] "
            f"over {self.n_counterfactual_weeks} weeks"
        )


def _id_crosswalk() -> dict[str, str]:
    """sleeper_id -> gsis_id, same construction :func:`~arena.make_engine_projector` uses."""
    from sleeper_ffm.nflverse.loader import load_id_map

    id_map = load_id_map()
    out: dict[str, str] = {}
    if {"sleeper_id", "gsis_id"} <= set(id_map.columns):
        for r in id_map.select(["sleeper_id", "gsis_id"]).iter_rows(named=True):
            if r.get("sleeper_id") and r.get("gsis_id"):
                out[str(r["sleeper_id"]).split(".")[0]] = str(r["gsis_id"])
    return out


def _season_universe(
    season: int, positions: dict[str, str], sleeper_to_gsis: dict[str, str]
) -> frozenset[str]:
    """Every sleeper id with an nflverse REG box score that season, at a scoreable position."""
    import polars as pl

    from sleeper_ffm.nflverse.loader import load_weekly

    weekly = load_weekly([season])
    if weekly.is_empty():
        return frozenset()
    weekly = weekly.filter(pl.col("season_type") == "REG")
    gsis_with_games = {str(g) for g in weekly["player_id"].unique().to_list()}
    return frozenset(
        pid
        for pid, gsis in sleeper_to_gsis.items()
        if gsis in gsis_with_games and positions.get(pid) in _SCOREABLE
    )


def _nflverse_points_by_week(season: int) -> dict[tuple[str, int], float]:
    """``{(gsis_id, week): league-scored points}`` for every skill player that season."""
    from sleeper_ffm.model.valuation import score_weekly

    scored = score_weekly([season])
    if scored.is_empty():
        return {}
    return {
        (str(row["player_id"]), int(row["week"])): float(row["fp_sffm"])
        for row in scored.select(["player_id", "week", "fp_sffm"]).iter_rows(named=True)
    }


def run_early_claim(
    season: int,
    top_k: int = _DEFAULT_TOP_K,
    horizon: int = _DEFAULT_HORIZON,
    min_week: int = _DEFAULT_MIN_WEEK,
    max_week: int = _DEFAULT_MAX_WEEK,
    value_top_n: int = _DEFAULT_VALUE_TOP_N,
    my_roster_id: int | None = None,
    league_id: str | None = None,
) -> EarlyClaimResult:
    """Replay a season's free-agent ocean blind: anticipation rate + my-roster counterfactual.

    Args:
        season: Completed season to replay.
        top_k: Size of the engine's blind weekly watchlist.
        horizon: Weeks of realized points that count toward a pickup's value.
        min_week: First week scored (earlier weeks warm the history).
        max_week: Last claim/watchlist week scored.
        value_top_n: How many of the season's top rival value-adds (by realized points) to
            adjudicate for anticipation.
        my_roster_id: Roster to run the counterfactual for. Defaults to ``MY_ROSTER_ID``.
        league_id: Override the league.

    Returns:
        An :class:`EarlyClaimResult`.

    Raises:
        ArenaUnavailableError: League/matchups unavailable, or nothing was scorable.
    """
    from sleeper_ffm.config import MY_ROSTER_ID
    from sleeper_ffm.evals.stats import paired_diff_ci
    from sleeper_ffm.sleeper.client import SleeperClient

    target = my_roster_id if my_roster_id is not None else MY_ROSTER_ID
    fetch_max = max_week + horizon  # need realized points this far past the last claim week

    with SleeperClient() as client:
        lid = league_id or _resolve_league_id(client, season)
        if lid is None:
            raise ArenaUnavailableError(f"no league in this dynasty's history for season {season}")
        league = client.league(lid)
        roster_positions = list(league.roster_positions or [])
        if not roster_positions:
            raise ArenaUnavailableError(f"league {lid} has no roster_positions")
        positions = _player_positions(client)
        proj = make_engine_projector(season)
        sleeper_to_gsis = _id_crosswalk()
        universe = _season_universe(season, positions, sleeper_to_gsis)
        if not universe:
            raise ArenaUnavailableError(f"no nflverse universe for season {season}")
        nflverse_pts = _nflverse_points_by_week(season)

        points_by_week: dict[int, dict[str, float]] = {}
        rostered_by_week: dict[int, set[str]] = {}
        my_roster_by_week: dict[int, list[str]] = {}
        rival_adds: list[tuple[str, int, int]] = []  # (pid, rival_roster_id, week)
        for week in range(1, fetch_max + 1):
            try:
                matchups = client.matchups(week, league_id=lid)
                txns = client.transactions(week, league_id=lid) if week <= max_week else []
            except Exception as exc:
                log.warning("early_claim: %s week %s unavailable: %s", season, week, exc)
                matchups, txns = [], []
            if matchups:
                points_by_week[week] = {
                    pid: float(p)
                    for r in matchups
                    for pid, p in (r.get("players_points") or {}).items()
                    if pid
                }
                rostered_by_week[week] = {
                    pid for r in matchups for pid in (r.get("players") or []) if pid
                }
                for r in matchups:
                    if int(r.get("roster_id", -1)) == target:
                        my_roster_by_week[week] = [pid for pid in (r.get("players") or []) if pid]
            for t in txns:
                if t.get("status") != "complete" or t.get("type") not in _TXN_TYPES:
                    continue
                for pid, rid in (t.get("adds") or {}).items():
                    if int(rid) != target:
                        rival_adds.append((str(pid), int(rid), week))

        watchlist_first_seen: dict[str, int] = {}
        pool_size_by_week: dict[int, int] = {}
        counterfactual_baseline: list[float] = []
        counterfactual_mutated: list[float] = []
        n_counterfactual_weeks = 0
        blind_history = PointHistory()
        for week in range(1, fetch_max + 1):
            if min_week <= week <= max_week:
                rostered = rostered_by_week.get(week, set())
                pool = free_agent_pool(universe, rostered)
                pool_size_by_week[week] = len(pool)
                my_players = my_roster_by_week.get(week, [])
                scores = proj(
                    week, list(dict.fromkeys(pool + my_players)), positions, blind_history
                )

                top = sorted(pool, key=lambda p: scores.get(p, 0.0), reverse=True)[:top_k]
                for pid in top:
                    watchlist_first_seen.setdefault(pid, week)

                if top and my_players:
                    my_lineup = select_lineup(
                        {pid: scores.get(pid, 0.0) for pid in my_players},
                        positions,
                        roster_positions,
                    )
                    bench = [pid for pid in my_players if pid not in my_lineup]
                    if bench:
                        worst_bench = min(bench, key=lambda p: scores.get(p, 0.0))
                        best_pickup = select_best_add(
                            top, my_players, worst_bench, positions, roster_positions, scores
                        )
                        if best_pickup is not None:
                            for w2 in range(week + 1, week + 1 + horizon):
                                realized = {
                                    pid: realized_points(
                                        pid, w2, points_by_week, nflverse_pts, sleeper_to_gsis
                                    )
                                    for pid in {*my_players, best_pickup}
                                }
                                baseline_pts, mutated_pts = counterfactual_week_points(
                                    my_players,
                                    worst_bench,
                                    best_pickup,
                                    positions,
                                    roster_positions,
                                    scores,
                                    realized,
                                )
                                counterfactual_baseline.append(baseline_pts)
                                counterfactual_mutated.append(mutated_pts)
                            n_counterfactual_weeks += 1
            if week in points_by_week:
                _extend_history(blind_history, [{"players_points": points_by_week[week]}])

        # First claim per player across the season — once a rival grabs him he's off the
        # pool for everyone else, so only the earliest claim matters for "was he flagged first".
        first_claim: dict[str, tuple[int, int]] = {}
        for pid, rid, week in sorted(rival_adds, key=lambda x: x[2]):
            first_claim.setdefault(pid, (week, rid))

        value_adds: list[tuple[str, int, int, float]] = []
        for pid, (week, rid) in first_claim.items():
            value = sum(
                realized_points(pid, w2, points_by_week, nflverse_pts, sleeper_to_gsis)
                for w2 in range(week + 1, min(week + 1 + horizon, fetch_max + 1))
            )
            value_adds.append((pid, week, rid, value))
        value_adds.sort(key=lambda x: -x[3])
        value_adds = value_adds[:value_top_n]

    stolen, missed = join_anticipation(value_adds, watchlist_first_seen)
    if not value_adds and not counterfactual_mutated:
        raise ArenaUnavailableError(f"nothing scorable for season {season}")

    n_value_adds = len(value_adds)
    n_anticipated = len(stolen)
    baseline_rate = (
        statistics.mean(
            random_anticipation_prob(pool_size_by_week, min_week, wk, top_k)
            for _, wk, _, _ in value_adds
        )
        if value_adds
        else 0.0
    )
    margin_ci = (
        paired_diff_ci(counterfactual_mutated, counterfactual_baseline)
        if counterfactual_mutated
        else (0.0, 0.0)
    )
    n_samples = len(counterfactual_mutated)
    mean_gain = (
        round((sum(counterfactual_mutated) - sum(counterfactual_baseline)) / n_samples, 3)
        if n_samples
        else 0.0
    )

    return EarlyClaimResult(
        season=season,
        league_id=lid,
        horizon=horizon,
        top_k=top_k,
        n_value_adds=n_value_adds,
        n_anticipated=n_anticipated,
        anticipation_rate=round(n_anticipated / n_value_adds, 4) if n_value_adds else 0.0,
        baseline_rate=round(baseline_rate, 4),
        median_lead_weeks=statistics.median([s.lead_weeks for s in stolen]) if stolen else 0.0,
        stolen_points=round(sum(s.realized_value for s in stolen), 2),
        stolen=stolen,
        missed=missed,
        n_counterfactual_weeks=n_counterfactual_weeks,
        counterfactual_mean_gain=mean_gain,
        counterfactual_ci=margin_ci,
    )


__all__ = [
    "EarlyClaimResult",
    "MissedPickup",
    "StolenPickup",
    "counterfactual_week_points",
    "free_agent_pool",
    "join_anticipation",
    "random_anticipation_prob",
    "realized_points",
    "run_early_claim",
    "select_best_add",
]
