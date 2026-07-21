"""The arena — does our engine actually beat the managers, replayed blind?

Every other eval here scores a *component* (expected TDs, a projection's MAE, Elo's game
prediction). This scores the whole point of the product: the weekly start/sit decision,
replayed against our own league's real history, with no knowledge of the outcome at pick
time. It is the only test that answers "would our engine have won."

The ground truth is unusually clean. Sleeper's historical matchups
(:meth:`~sleeper_ffm.sleeper.client.SleeperClient.matchups`) hand us, for every roster and
every week of every completed season back to 2020:

* ``players`` — the exact roster available that week,
* ``starters`` — what the manager actually started,
* ``players_points`` — every player's real fantasy points, **already scored under this
  league's exact settings by Sleeper**.

So there is nothing to synthesize and nothing to re-derive: the roster is real, the
outcomes are real, and the human's decision is real. The arena replays each roster-week
three ways and scores all three on the same realized points:

* **engine** — a projector picks the lineup using ONLY weeks before the one being played,
  then that lineup is scored on what actually happened. Blind by construction.
* **actual** — what the manager really started. The opponent to beat.
* **optimal** — the best legal lineup in hindsight. The ceiling nobody reaches.

The projector is pluggable (:data:`Projector`) so different engine configurations compete
on the same slate. Two ship here:

* :func:`season_average_projector` — each player's mean points so far this season, from the
  league's own ``players_points``. Self-contained, covers every position (K/DEF included),
  and is exactly what a manager could compute at the time. The honest control.
* :func:`engine_projector` — our in-house forecast (:mod:`sleeper_ffm.model.forecast`) for
  skill positions, falling back to the season average for K/DEF and anyone without
  nflverse history. This is "our engine" as it could have run that week.

Note the rotowire provider is deliberately absent: Sleeper's GraphQL endpoint only serves
the current season, so it could not have been queried in a past week. Including it would be
lookahead. The arena tests only what was reconstructable point-in-time.

The verdict so far
------------------
Three seasons of this league, weeks 4-17, share of the hindsight-optimal lineup captured::

    season   managers   engine   season-avg   engine beat managers
    2022      85.2%      76.3%      72.5%           19% of weeks
    2023      85.1%      78.4%      73.8%           29%
    2024      83.5%      77.4%      72.3%           25%

Two stable, load-bearing conclusions:

* **The engine is directionally right.** Every season it beats the naive controls by 4-5
  points of capture (forecast + bye-awareness > recency > season-average), so the tools we
  built add real lineup value over a dumb heuristic.
* **It does not yet beat good managers.** It trails the humans by ~7-9 points of capture
  every season and wins only a quarter of roster-weeks. The managers here capture ~84% —
  they are strong. The gap is dominated by *availability*: the engine zeroes byes but has
  no point-in-time injury feed, so it still starts players who were questionable/out on
  news a manager had. Closing that (an nflverse injury-report join) is the clear next lever,
  and this harness is how we'll know if it worked.

That is the honest answer to "are we going in the right direction": yes on the model, not
yet on the outcome, and now we can measure every step toward it.

Why not simulate the current season
------------------------------------
2026 has not been played — there are no outcomes to be blind about. A blind test needs a
result to have been hidden, so it must be historical. This is why the arena targets
completed seasons, not the live one.

Leakage discipline
------------------
The single thing that makes or breaks this test is that the projector never sees the week
it is picking. The harness enforces it structurally: the projector is handed a
:class:`PointHistory` built from strictly-earlier weeks, and the realized points are
applied only after the lineup is chosen. If that guarantee ever weakens, every number here
becomes a lie, so it is centralized in one place (:func:`_replay_week`) rather than trusted
to each projector.
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field

from sleeper_ffm.model.owner_skill import _FLEX_ELIGIBLE, _NON_STARTING_SLOTS

log = logging.getLogger(__name__)

# Weeks before this have too little in-season history to project from; they warm up the
# season-to-date averages instead of being scored.
_DEFAULT_MIN_WEEK = 4
# Last regular + fantasy-playoff week worth scoring. Weeks past this are championship-only
# and sparsely rostered.
_DEFAULT_MAX_WEEK = 17

_DEDICATED = ("QB", "RB", "WR", "TE", "K", "DEF")


class ArenaUnavailableError(RuntimeError):
    """The Sleeper history needed to run the arena could not be loaded."""


@dataclass
class PointHistory:
    """Per-player realized points from weeks strictly before the one being projected.

    This is the *only* channel a projector may read about player form, and it contains no
    information from the week under test — that is what keeps the replay blind.
    """

    by_player: dict[str, list[float]] = field(default_factory=dict)

    def average(self, player_id: str) -> float | None:
        """Season-to-date mean points for a player, or None with no prior games."""
        games = self.by_player.get(player_id)
        return statistics.mean(games) if games else None

    def games(self, player_id: str) -> int:
        """How many prior games this player has on record."""
        return len(self.by_player.get(player_id, ()))


# A projector maps a roster-week to projected points per available player. It receives the
# week, the available player ids, their positions, and the blind history. It must not use
# any other source of week-of information.
Projector = Callable[[int, list[str], dict[str, str], PointHistory], dict[str, float]]


@dataclass
class WeekScore:
    """One roster's engine / actual / optimal points for one week."""

    week: int
    roster_id: int
    engine_pts: float
    actual_pts: float
    optimal_pts: float

    @property
    def engine_beat_actual(self) -> bool:
        """Whether the blind engine lineup matched or beat what the manager started."""
        return self.engine_pts >= self.actual_pts - 1e-9


@dataclass
class ArenaResult:
    """Aggregate verdict for one projector over one season."""

    season: int
    league_id: str
    projector: str
    n_roster_weeks: int
    engine_mean: float
    actual_mean: float
    optimal_mean: float
    # Fraction of roster-weeks where the blind engine >= the human.
    engine_beats_actual_rate: float
    # Mean points/week the engine gained or lost vs the human.
    engine_vs_actual_margin: float
    # Share of the hindsight ceiling each side captured (higher = better lineup-setting).
    engine_capture: float
    actual_capture: float
    weeks_scored: tuple[int, ...] = ()

    def summary(self) -> str:
        """One-line human-readable verdict."""
        verb = "beats" if self.engine_vs_actual_margin > 0 else "trails"
        return (
            f"{self.season} [{self.projector}]: engine {verb} managers by "
            f"{self.engine_vs_actual_margin:+.1f} pts/wk "
            f"({self.engine_beats_actual_rate:.0%} of roster-weeks); "
            f"captured {self.engine_capture:.1%} of optimal vs managers' {self.actual_capture:.1%}"
        )


# --- lineup solving -----------------------------------------------------------------


def select_lineup(
    scores: dict[str, float],
    positions: dict[str, str],
    roster_positions: list[str],
) -> list[str]:
    """Pick the best legal lineup by ``scores`` and return the chosen player ids.

    The counterpart to :func:`sleeper_ffm.model.owner_skill.optimal_lineup_points`, but it
    returns *which* players it started so their realized points can be summed separately —
    the whole trick of scoring a blind pick on actual outcomes. Greedy is optimal because
    FLEX eligibility is a superset of the dedicated skill slots.

    Args:
        scores: ``{player_id: score}`` to rank by (projected, or actual for the ceiling).
        positions: ``{player_id: position}``.
        roster_positions: League slot layout, e.g. ``["QB", "RB", ..., "FLEX", "BN"]``.

    Returns:
        The chosen starter ids. Players without a position or a score are ineligible.
    """
    pools: dict[str, list[str]] = {pos: [] for pos in _DEDICATED}
    for pid in scores:
        pos = positions.get(pid)
        if pos in pools:
            pools[pos].append(pid)
    for pos in pools:
        pools[pos].sort(key=lambda p: scores.get(p, 0.0), reverse=True)

    chosen: list[str] = []
    flex_slots = 0
    for slot in roster_positions:
        if slot in _NON_STARTING_SLOTS:
            continue
        if slot == "FLEX":
            flex_slots += 1
            continue
        if pools.get(slot):
            chosen.append(pools[slot].pop(0))

    if flex_slots:
        flex_pool = sorted(
            (pid for pos in _FLEX_ELIGIBLE for pid in pools.get(pos, [])),
            key=lambda p: scores.get(p, 0.0),
            reverse=True,
        )
        chosen.extend(flex_pool[:flex_slots])
    return chosen


# --- projectors ---------------------------------------------------------------------


def season_average_projector(
    week: int,
    available: list[str],
    positions: dict[str, str],
    history: PointHistory,
) -> dict[str, float]:
    """Project each player at their season-to-date mean. The honest control.

    Uses only the league's own realized points from earlier weeks, so it covers every
    position and leaks nothing. A player with no prior game projects at 0.0 — the same
    blind spot a manager faced.
    """
    return {pid: (history.average(pid) or 0.0) for pid in available}


def recency_projector(
    week: int,
    available: list[str],
    positions: dict[str, str],
    history: PointHistory,
) -> dict[str, float]:
    """Project each player at their mean over the last four games. A stronger control.

    Same self-contained, leak-free data as :func:`season_average_projector`, but weighting
    recent form — the "he's hot / he's cold" heuristic every manager already applies.
    """
    out: dict[str, float] = {}
    for pid in available:
        games = history.by_player.get(pid) or []
        out[pid] = statistics.mean(games[-4:]) if games else 0.0
    return out


def make_engine_projector(season: int) -> Projector:
    """Build a projector backed by our in-house forecast — "our engine" as it ran that week.

    This is the real subject of the test. Skill players are projected by
    :func:`sleeper_ffm.model.forecast.forecast_player` from their nflverse box scores
    through the prior week only (priors fit on the *previous* season, so nothing from the
    season under test leaks into the model's parameters). K, DEF, and anyone without
    nflverse history fall back to the season-to-date average. Players whose team is on bye
    that week are zeroed — a bye is public schedule information, so using it is not
    lookahead; failing to would just restart the naive control's biggest mistake.

    Heavy data (weekly box scores, priors, the id crosswalk, the bye calendar) is loaded
    once here and closed over; per-player forecasts are cached by ``(gsis_id, week)`` so a
    player is projected at most once per week across the whole replay.

    Args:
        season: The season being replayed.

    Returns:
        A :data:`Projector`. If nflverse data is unavailable it degrades to
        :func:`season_average_projector` rather than failing the arena.
    """
    import polars as pl

    from sleeper_ffm.model.forecast import build_priors, forecast_player
    from sleeper_ffm.nflverse.loader import load_id_map, load_schedules, load_weekly
    from sleeper_ffm.scoring.engine import load_scoring

    skill = frozenset({"QB", "RB", "WR", "TE"})

    weekly = load_weekly([season])
    if weekly.is_empty():
        log.warning("arena: no nflverse weekly for %s; engine falls back to season average", season)
        return season_average_projector
    weekly = weekly.filter(pl.col("season_type") == "REG")

    scoring = load_scoring()
    priors = build_priors(season - 1)
    if not priors.rates:  # no prior-season fit → the forecast has no anchor
        priors = build_priors(season)

    # sleeper_id -> gsis_id
    id_map = load_id_map()
    sleeper_to_gsis: dict[str, str] = {}
    if {"sleeper_id", "gsis_id"} <= set(id_map.columns):
        for r in id_map.select(["sleeper_id", "gsis_id"]).iter_rows(named=True):
            if r.get("sleeper_id") and r.get("gsis_id"):
                sleeper_to_gsis[str(r["sleeper_id"]).split(".")[0]] = str(r["gsis_id"])

    # Per-gsis weekly rows, chronological.
    rows_by_gsis: dict[str, list[dict]] = {}
    for row in weekly.sort("week").iter_rows(named=True):
        rows_by_gsis.setdefault(str(row["player_id"]), []).append(row)

    bye_teams = _bye_calendar(load_schedules, season)
    team_by_gsis = {
        gsis: (rows[-1].get("recent_team") or "") for gsis, rows in rows_by_gsis.items()
    }
    forecast_cache: dict[tuple[str, int], float] = {}

    def projector(
        wk: int, available: list[str], positions: dict[str, str], history: PointHistory
    ) -> dict[str, float]:
        out: dict[str, float] = {}
        for pid in available:
            pos = positions.get(pid)
            gsis = sleeper_to_gsis.get(pid)
            if pos in skill and gsis and gsis in rows_by_gsis:
                if team_by_gsis.get(gsis) in bye_teams.get(wk, frozenset()):
                    out[pid] = 0.0  # on bye — a manager would never start him
                    continue
                out[pid] = _cached_forecast(
                    gsis, wk, pos, rows_by_gsis, priors, scoring, forecast_cache, forecast_player
                )
            else:
                out[pid] = history.average(pid) or 0.0
        return out

    return projector


def _cached_forecast(
    gsis: str,
    week: int,
    position: str,
    rows_by_gsis: dict[str, list[dict]],
    priors,
    scoring: dict[str, float],
    cache: dict[tuple[str, int], float],
    forecast_player,
) -> float:
    """Mean of our forecast for one skill player-week, memoized and blind to week ``week``."""
    key = (gsis, week)
    if key in cache:
        return cache[key]
    prior_rows = [r for r in rows_by_gsis[gsis] if int(r["week"]) < week]
    if not prior_rows:
        cache[key] = 0.0
        return 0.0
    forecast = forecast_player(
        rows=prior_rows,
        player_id=gsis,
        name="",
        position=position,
        team="",
        opponent="",
        season=0,
        week=week,
        priors=priors,
        scoring=scoring,
        n_sims=200,
    )
    cache[key] = forecast.points.mean
    return forecast.points.mean


def _bye_calendar(load_schedules, season: int) -> dict[int, frozenset[str]]:
    """``{week: {teams on bye}}`` for a season, from the schedule (public, not lookahead)."""
    import polars as pl

    sched = load_schedules([season])
    if sched.is_empty():
        return {}
    reg = sched.filter((pl.col("season") == season) & (pl.col("game_type") == "REG"))
    weeks = sorted({int(w) for w in reg["week"].unique()})
    all_teams = set(reg["home_team"].to_list()) | set(reg["away_team"].to_list())
    out: dict[int, frozenset[str]] = {}
    for wk in weeks:
        wk_df = reg.filter(pl.col("week") == wk)
        playing = set(wk_df["home_team"].to_list()) | set(wk_df["away_team"].to_list())
        out[wk] = frozenset(all_teams - playing)
    return out


# --- replay -------------------------------------------------------------------------


def _replay_week(
    week: int,
    roster: dict,
    positions: dict[str, str],
    roster_positions: list[str],
    history: PointHistory,
    projector: Projector,
) -> WeekScore | None:
    """Score one roster's week three ways. Returns None if the week has no usable data.

    This function is the leakage firewall: ``projector`` is called with ``history`` (prior
    weeks only), and ``actual`` points are read *after* the pick. Nothing downstream can
    reintroduce week-of information into the projection.
    """
    actual_points_raw = roster.get("players_points") or {}
    available = [pid for pid in (roster.get("players") or []) if pid]
    if not available or not actual_points_raw:
        return None
    actual_points = {pid: float(pts) for pid, pts in actual_points_raw.items()}

    # Blind pick.
    projected = projector(week, available, positions, history)
    engine_ids = select_lineup(projected, positions, roster_positions)
    engine_pts = sum(actual_points.get(pid, 0.0) for pid in engine_ids)

    # Hindsight ceiling, scored on the same realized points.
    optimal_ids = select_lineup(actual_points, positions, roster_positions)
    optimal_pts = sum(actual_points.get(pid, 0.0) for pid in optimal_ids)

    # What the manager actually did.
    actual_starters = [pid for pid in (roster.get("starters") or []) if pid]
    actual_pts = sum(actual_points.get(pid, 0.0) for pid in actual_starters)

    return WeekScore(
        week=week,
        roster_id=int(roster.get("roster_id", 0)),
        engine_pts=round(engine_pts, 2),
        actual_pts=round(actual_pts, 2),
        optimal_pts=round(optimal_pts, 2),
    )


def run_arena(
    season: int,
    projector: Projector = season_average_projector,
    projector_name: str = "season_average",
    min_week: int = _DEFAULT_MIN_WEEK,
    max_week: int = _DEFAULT_MAX_WEEK,
    league_id: str | None = None,
) -> ArenaResult:
    """Replay a completed season's start/sit decisions blind and score the engine.

    Args:
        season: Completed NFL/fantasy season to replay.
        projector: The lineup-projection strategy under test.
        projector_name: Label for the result.
        min_week: First week scored; earlier weeks only warm the history.
        max_week: Last week scored.
        league_id: Override the league. Defaults to the season's entry in this league's
            own history chain.

    Returns:
        An :class:`ArenaResult` aggregating engine vs actual vs optimal over every
        roster-week.

    Raises:
        ArenaUnavailableError: The season's league history or matchups could not be loaded,
            or no week produced a usable roster.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        lid = league_id or _resolve_league_id(client, season)
        if lid is None:
            raise ArenaUnavailableError(f"no league in this dynasty's history for season {season}")
        league = client.league(lid)
        roster_positions = list(league.roster_positions or [])
        if not roster_positions:
            raise ArenaUnavailableError(f"league {lid} has no roster_positions")
        positions = _player_positions(client)

        history = PointHistory()
        scores: list[WeekScore] = []
        weeks_scored: list[int] = []
        for week in range(1, max_week + 1):
            try:
                matchups = client.matchups(week, league_id=lid)
            except Exception as exc:  # a missing week must not abort the whole replay
                log.warning("arena: %s week %s matchups unavailable: %s", season, week, exc)
                matchups = []
            if not matchups:
                continue

            if week >= min_week:
                for roster in matchups:
                    score = _replay_week(
                        week, roster, positions, roster_positions, history, projector
                    )
                    if score is not None:
                        scores.append(score)
                weeks_scored.append(week)

            _extend_history(history, matchups)

    if not scores:
        raise ArenaUnavailableError(f"no scorable roster-weeks for season {season}")
    return _aggregate(season, lid, projector_name, scores, tuple(weeks_scored))


def _aggregate(
    season: int,
    league_id: str,
    projector_name: str,
    scores: list[WeekScore],
    weeks_scored: tuple[int, ...],
) -> ArenaResult:
    n = len(scores)
    engine_mean = statistics.mean(s.engine_pts for s in scores)
    actual_mean = statistics.mean(s.actual_pts for s in scores)
    optimal_mean = statistics.mean(s.optimal_pts for s in scores)
    beat_rate = sum(1 for s in scores if s.engine_beat_actual) / n
    return ArenaResult(
        season=season,
        league_id=league_id,
        projector=projector_name,
        n_roster_weeks=n,
        engine_mean=round(engine_mean, 2),
        actual_mean=round(actual_mean, 2),
        optimal_mean=round(optimal_mean, 2),
        engine_beats_actual_rate=round(beat_rate, 4),
        engine_vs_actual_margin=round(engine_mean - actual_mean, 2),
        engine_capture=round(engine_mean / optimal_mean, 4) if optimal_mean else 0.0,
        actual_capture=round(actual_mean / optimal_mean, 4) if optimal_mean else 0.0,
        weeks_scored=weeks_scored,
    )


def _extend_history(history: PointHistory, matchups: list[dict]) -> None:
    """Fold a completed week's realized points into the running history."""
    for roster in matchups:
        for pid, pts in (roster.get("players_points") or {}).items():
            if pid:
                history.by_player.setdefault(pid, []).append(float(pts))


def _resolve_league_id(client, season: int) -> str | None:
    """Find the league_id for a season within this dynasty's previous_league_id chain."""
    for league in client.league_history():
        if str(league.season) == str(season):
            return league.league_id
    return None


def _player_positions(client) -> dict[str, str]:
    """``{sleeper_player_id: position}`` for every player, plus team-defense ids."""
    players = client.players()
    out: dict[str, str] = {}
    for pid, meta in players.items():
        pos = meta.get("position")
        if pos:
            out[pid] = pos
    return out
