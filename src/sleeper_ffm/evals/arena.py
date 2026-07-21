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
Four seasons of this league, weeks 4-17, share of the hindsight-optimal lineup captured.
The availability levers (injury-report gating + a box-score-absence discount) were the
predicted fix for the original ~7-9 point gap, and they landed::

    season   managers   engine (base)   engine (+availability)   beat rate   dead starters/wk
    2022      85.2%         76.3%              82.0%                 36%        1.49 -> 0.56
    2023      85.1%         78.4%              81.8%                 39%        1.17 -> 0.45
    2024      83.5%         77.4%              81.1%                 38%        1.29 -> 0.44
    2025      84.2%          —                 81.0%                 39%           -> 0.44

What the levers did, and what remains:

* **Availability was the gap, and it was measurable.** The base engine started ~1.2-1.5
  dead (0.0-point) starters per week; managers started ~0.3. Gating Out/Doubtful players to
  zero, shading Questionable ones, and discounting anyone who missed his team's last game
  cut that to ~0.45-0.56 — near the human rate — and lifted capture 3-6 points and the
  beat-rate from ~25% to ~38% on every season. The tools now do most of what a manager
  does before lock.
* **A ~2-3 point residual remains, and it is honest.** The engine still trails the managers
  by 2-3 points of capture. That gap is the reconstructable-information ceiling: late
  Sunday-morning inactive news the weekly injury report doesn't carry, plus ordinary
  ranking misses among healthy players (the forecast is ~as accurate as a season average in
  raw MAE — measured separately). Rotowire, which would help the ranking side, is excluded
  as lookahead in a historical replay. Whether that residual can close further is what the
  waiver/trade/H2H batteries and any future ranking work get measured against.

* **In this league, "3 points below average" means near the bottom.** :func:`run_league_h2h`
  replays every roster with the engine: it would out-manage only ~1 of 10 managers on
  points. That is not a contradiction of the small capture gap — it *is* it. The managers
  here are strong and tightly clustered (~84% capture, low spread), so sitting 3 points
  under the pack ranks near last, not middle. The availability levers moved the engine from
  well below the field to just below it; reaching "unbeatable" now requires clearing the
  ranking bar above ~84%, which is a projection/news problem, not an availability one. The
  arena is now sharp enough to see a 3-point gap and rank the engine within the league,
  which is exactly the instrument needed to chase the rest.

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

# Availability multipliers (Levers A & B). A player designated Out/Doubtful is zeroed; a
# Questionable one plays ~75-80% of the time historically, so his projection is shaded
# rather than cut. A player who missed his team's most recent game (no box-score row) is
# heavily discounted but not zeroed — he may be returning, and the absence of an Out
# designation this week is the "he's back" signal. Constants are documented, not tuned
# per season; the arena is what tells us whether they help.
_QUESTIONABLE_FACTOR = 0.8
_OUT_STATUSES = frozenset({"Out", "Doubtful"})
_DNP_FACTOR = 0.3


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
    # Starters that scored exactly 0.0 — the fingerprint of a bye/inactive/out player who
    # should never have been in the lineup. The whole availability thesis is that the
    # engine's count is higher than the managers'.
    engine_zero_starters: int = 0
    actual_zero_starters: int = 0

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
    # Mean 0.0-point starters per lineup — the availability fingerprint (see WeekScore).
    engine_zero_starter_rate: float = 0.0
    actual_zero_starter_rate: float = 0.0
    weeks_scored: tuple[int, ...] = ()

    def summary(self) -> str:
        """One-line human-readable verdict."""
        verb = "beats" if self.engine_vs_actual_margin > 0 else "trails"
        return (
            f"{self.season} [{self.projector}]: engine {verb} managers by "
            f"{self.engine_vs_actual_margin:+.1f} pts/wk "
            f"({self.engine_beats_actual_rate:.0%} of roster-weeks); "
            f"captured {self.engine_capture:.1%} vs managers' {self.actual_capture:.1%}; "
            f"dead starters {self.engine_zero_starter_rate:.2f}/wk vs "
            f"{self.actual_zero_starter_rate:.2f}"
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


def make_engine_projector(season: int, blend_weight: float = 0.0) -> Projector:
    """Build a projector backed by our in-house forecast — "our engine" as it ran that week.

    This is the real subject of the test. Skill players are projected by
    :func:`sleeper_ffm.model.forecast.forecast_player` from their nflverse box scores
    through the prior week only (priors fit on the *previous* season, so nothing from the
    season under test leaks into the model's parameters). K, DEF, and anyone without
    nflverse history fall back to the season-to-date average. Players whose team is on bye
    that week are zeroed — a bye is public schedule information, so using it is not
    lookahead; failing to would just restart the naive control's biggest mistake.

    ``blend_weight`` (Lever C) mixes the forecast with the player's own league-scored last-4
    average from ``history`` — ``blend_weight`` of the latter, ``1 - blend_weight`` of the
    forecast. It defaults off because a sweep (0.25/0.5/0.75) *rejected* it: capture was
    flat-to-worse on every weight and season (e.g. 2023: 81.8% at 0.0 → 80.5% at 0.75). The
    league last-4 is a noisier ranking signal than the forecast, so blending it in does not
    sharpen lineups. The knob stays for future ranking experiments run through the arena, not
    because it helps today.

    Heavy data (weekly box scores, priors, the id crosswalk, the bye calendar) is loaded
    once here and closed over; per-player forecasts are cached by ``(gsis_id, week)`` so a
    player is projected at most once per week across the whole replay.

    Args:
        season: The season being replayed.
        blend_weight: Fraction of the projection taken from the player's league-scored
            last-4 average rather than the forecast (Lever C). 0.0 = pure forecast.

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
    weeks_played = _weeks_played_by_team(load_schedules, season)
    injuries = _injury_calendar(season)
    team_by_gsis = {
        gsis: (rows[-1].get("recent_team") or "") for gsis, rows in rows_by_gsis.items()
    }
    box_weeks_by_gsis = {
        gsis: {int(r["week"]) for r in rows} for gsis, rows in rows_by_gsis.items()
    }
    forecast_cache: dict[tuple[str, int], float] = {}

    def projector(
        wk: int, available: list[str], positions: dict[str, str], history: PointHistory
    ) -> dict[str, float]:
        # Only this week's injury report is ever consulted — the lookup is keyed by wk, so
        # no future week's designations can leak in.
        week_injuries = injuries.get(wk, {})
        out: dict[str, float] = {}
        for pid in available:
            pos = positions.get(pid)
            gsis = sleeper_to_gsis.get(pid)
            if pos in skill and gsis and gsis in rows_by_gsis:
                if team_by_gsis.get(gsis) in bye_teams.get(wk, frozenset()):
                    out[pid] = 0.0  # on bye — a manager would never start him
                    continue
                base = _cached_forecast(
                    gsis, wk, pos, rows_by_gsis, priors, scoring, forecast_cache, forecast_player
                )
                if blend_weight > 0:
                    league_games = history.by_player.get(pid) or []
                    if league_games:
                        league_l4 = statistics.mean(league_games[-4:])
                        base = (1 - blend_weight) * base + blend_weight * league_l4
                out[pid] = base * _availability_multiplier(
                    gsis, wk, week_injuries, weeks_played, team_by_gsis, box_weeks_by_gsis
                )
            else:
                out[pid] = history.average(pid) or 0.0
        return out

    return projector


def _availability_multiplier(
    gsis: str,
    wk: int,
    week_injuries: dict[str, str],
    weeks_played: dict[str, set[int]],
    team_by_gsis: dict[str, str],
    box_weeks_by_gsis: dict[str, set[int]],
) -> float:
    """Point-in-time availability shade for a skill player (Levers A & B).

    Lever A — this week's injury designation: Out/Doubtful zeroes the projection,
    Questionable shades it. Lever B — if the player has no box score for his team's most
    recent completed game, he was inactive and is heavily discounted (he may be returning,
    so not zeroed). Returns 1.0 when nothing flags him.
    """
    status = week_injuries.get(gsis)
    if status in _OUT_STATUSES:
        return 0.0
    factor = _QUESTIONABLE_FACTOR if status == "Questionable" else 1.0

    team = team_by_gsis.get(gsis, "")
    prior_team_weeks = [w for w in weeks_played.get(team, ()) if w < wk]
    if prior_team_weeks:
        last_team_week = max(prior_team_weeks)
        if last_team_week not in box_weeks_by_gsis.get(gsis, set()):
            factor *= _DNP_FACTOR  # missed the team's last game — inactive/scratched
    return factor


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


def _weeks_played_by_team(load_schedules, season: int) -> dict[str, set[int]]:
    """``{team: {weeks that team played}}`` — the inverse of the bye calendar."""
    import polars as pl

    sched = load_schedules([season])
    if sched.is_empty():
        return {}
    reg = sched.filter((pl.col("season") == season) & (pl.col("game_type") == "REG"))
    out: dict[str, set[int]] = {}
    for row in reg.iter_rows(named=True):
        wk = int(row["week"])
        for team in (row.get("home_team"), row.get("away_team")):
            if team:
                out.setdefault(team, set()).add(wk)
    return out


def _injury_calendar(season: int) -> dict[int, dict[str, str]]:
    """``{week: {gsis_id: report_status}}`` from the nflverse injury reports.

    Best-effort: a fetch failure (or a season nflverse never published) degrades to an
    empty calendar, so the arena runs on Lever B alone rather than aborting. Practice-only
    rows carry a null ``report_status`` and are dropped — only the pregame game designation
    (Out/Doubtful/Questionable) is kept. Using it is not lookahead: it is the report that
    stood before kickoff, exactly what a manager saw.
    """
    import polars as pl

    from sleeper_ffm.nflverse.loader import load_injuries

    try:
        inj = load_injuries([season])
    except Exception as exc:  # availability is a best-effort companion, never fatal
        log.warning("arena: injuries for %s unavailable (%s); running Lever B only", season, exc)
        return {}
    needed = {"week", "gsis_id", "report_status", "game_type"}
    if inj.is_empty() or not needed.issubset(inj.columns):
        return {}
    reg = inj.filter((pl.col("game_type") == "REG") & pl.col("report_status").is_not_null())
    out: dict[int, dict[str, str]] = {}
    for row in reg.select(["week", "gsis_id", "report_status"]).iter_rows(named=True):
        gsis = row.get("gsis_id")
        status = row.get("report_status")
        if gsis and status:
            out.setdefault(int(row["week"]), {})[str(gsis)] = str(status)
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
        engine_zero_starters=sum(1 for pid in engine_ids if actual_points.get(pid, 0.0) == 0.0),
        actual_zero_starters=sum(
            1 for pid in actual_starters if actual_points.get(pid, 0.0) == 0.0
        ),
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
        engine_zero_starter_rate=round(statistics.mean(s.engine_zero_starters for s in scores), 3),
        actual_zero_starter_rate=round(statistics.mean(s.actual_zero_starters for s in scores), 3),
        weeks_scored=weeks_scored,
    )


def _extend_history(history: PointHistory, matchups: list[dict]) -> None:
    """Fold a completed week's realized points into the running history."""
    for roster in matchups:
        for pid, pts in (roster.get("players_points") or {}).items():
            if pid:
                history.by_player.setdefault(pid, []).append(float(pts))


def append_arena_ledger(result: ArenaResult) -> str:
    """Append a compact arena result to the shared eval ledger for regression tracking.

    Records the capture gap and dead-starter rate under a git SHA, so a future engine
    change's arena impact is visible in the same ``sffm eval report`` trail as the tier-1
    scenarios. Mirrors :mod:`sleeper_ffm.evals.harness`'s ledger shape.

    Args:
        result: The arena result to log.

    Returns:
        The ledger path written to.
    """
    import json
    import subprocess
    from datetime import UTC, datetime

    from sleeper_ffm.evals.scenarios import RUNS_DIR

    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "unknown"

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "kind": "arena",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": sha,
        "season": result.season,
        "projector": result.projector,
        "engine_capture": result.engine_capture,
        "actual_capture": result.actual_capture,
        "capture_gap": round(result.actual_capture - result.engine_capture, 4),
        "engine_beats_actual_rate": result.engine_beats_actual_rate,
        "engine_dead_starters": result.engine_zero_starter_rate,
        "n_roster_weeks": result.n_roster_weeks,
    }
    path = RUNS_DIR / "arena_ledger.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return str(path)


# --- head-to-head counterfactual: would the engine have WON? ------------------------


@dataclass
class H2HResult:
    """Would-we-have-won verdict for one roster over one season's regular schedule.

    The counterfactual changes only this roster's lineup decisions; every opponent keeps
    the exact score they really posted. So a flipped win is one this roster would have won
    purely by setting a better lineup — nothing about the rest of the league moves.
    """

    season: int
    league_id: str
    roster_id: int
    projector: str
    n_weeks: int
    engine_wins: int
    engine_losses: int
    actual_wins: int
    actual_losses: int
    engine_points_for: float
    actual_points_for: float
    # All-play: record vs every other team each week (schedule-luck-free strength).
    engine_allplay_wins: int
    actual_allplay_wins: int
    allplay_games: int
    # Mean weekly points the engine's lineup gained over the manager's, with a bootstrap CI.
    points_margin: float
    points_margin_ci: tuple[float, float]
    # Two-sided sign-test p-value that the engine outscores the manager != half the time.
    outscore_pvalue: float

    def summary(self) -> str:
        """One-line verdict."""
        lo, hi = self.points_margin_ci
        return (
            f"{self.season} roster {self.roster_id} [{self.projector}]: engine "
            f"{self.engine_wins}-{self.engine_losses} vs manager's "
            f"{self.actual_wins}-{self.actual_losses} (H2H, {self.n_weeks} wks); "
            f"all-play {self.engine_allplay_wins}/{self.allplay_games} vs "
            f"{self.actual_allplay_wins}/{self.allplay_games}; "
            f"outscored the manager {self.points_margin:+.1f} pts/wk "
            f"[95% CI {lo:+.1f}, {hi:+.1f}], p={self.outscore_pvalue}"
        )


def run_h2h(
    season: int,
    roster_id: int | None = None,
    projector: Projector | None = None,
    projector_name: str = "engine",
    min_week: int = _DEFAULT_MIN_WEEK,
    league_id: str | None = None,
) -> H2HResult:
    """Replay one roster's season with engine lineups; would its record have improved?

    Restricted to the regular season (``playoff_week_start - 1``), where ``matchup_id``
    gives a real head-to-head opponent. Each week the target roster's blind engine lineup
    is scored on realized points and compared to the opponent's actual total (the opponent
    is untouched). All-play compares the roster's score to every other team's actual score
    that week — a schedule-luck-free read.

    Args:
        season: Completed season to replay.
        roster_id: Which roster to manage with the engine. Defaults to
            :data:`~sleeper_ffm.config.MY_ROSTER_ID`.
        projector: Lineup strategy. Defaults to :func:`make_engine_projector` for ``season``.
        projector_name: Label for the result.
        min_week: First week counted (earlier weeks warm the projection history).
        league_id: Override the league; defaults to the season's entry in this dynasty.

    Returns:
        An :class:`H2HResult`.

    Raises:
        ArenaUnavailableError: League/matchups unavailable, or the roster never appears.
    """
    from sleeper_ffm.config import MY_ROSTER_ID
    from sleeper_ffm.evals.stats import paired_diff_ci, sign_test_pvalue
    from sleeper_ffm.sleeper.client import SleeperClient

    target = roster_id if roster_id is not None else MY_ROSTER_ID

    with SleeperClient() as client:
        lid = league_id or _resolve_league_id(client, season)
        if lid is None:
            raise ArenaUnavailableError(f"no league in this dynasty's history for season {season}")
        league = client.league(lid)
        roster_positions = list(league.roster_positions or [])
        if not roster_positions:
            raise ArenaUnavailableError(f"league {lid} has no roster_positions")
        regular_weeks = int(league.settings.get("playoff_week_start", 15)) - 1
        positions = _player_positions(client)
        proj = projector or make_engine_projector(season)

        history = PointHistory()
        engine_pf = actual_pf = 0.0
        e_wins = e_losses = a_wins = a_losses = 0
        e_ap = a_ap = ap_games = 0
        engine_series: list[float] = []
        actual_series: list[float] = []

        for week in range(1, regular_weeks + 1):
            try:
                matchups = client.matchups(week, league_id=lid)
            except Exception as exc:
                log.warning("h2h: %s week %s unavailable: %s", season, week, exc)
                matchups = []
            if not matchups:
                continue

            if week >= min_week:
                verdict = _score_h2h_week(
                    week, matchups, target, positions, roster_positions, history, proj
                )
                if verdict is not None:
                    engine_pts, actual_pts, opp_pts, others = verdict
                    engine_pf += engine_pts
                    actual_pf += actual_pts
                    engine_series.append(engine_pts)
                    actual_series.append(actual_pts)
                    if opp_pts is not None:
                        e_wins += engine_pts > opp_pts
                        e_losses += engine_pts < opp_pts
                        a_wins += actual_pts > opp_pts
                        a_losses += actual_pts < opp_pts
                    for o in others:
                        ap_games += 1
                        e_ap += engine_pts > o
                        a_ap += actual_pts > o

            _extend_history(history, matchups)

    if not engine_series:
        raise ArenaUnavailableError(f"roster {target} produced no scorable weeks in {season}")

    margins = [e - a for e, a in zip(engine_series, actual_series, strict=True)]
    wins = sum(1 for m in margins if m > 0)
    return H2HResult(
        season=season,
        league_id=lid,
        roster_id=target,
        projector=projector_name,
        n_weeks=len(engine_series),
        engine_wins=e_wins,
        engine_losses=e_losses,
        actual_wins=a_wins,
        actual_losses=a_losses,
        engine_points_for=round(engine_pf, 2),
        actual_points_for=round(actual_pf, 2),
        engine_allplay_wins=e_ap,
        actual_allplay_wins=a_ap,
        allplay_games=ap_games,
        points_margin=round(statistics.mean(margins), 2),
        points_margin_ci=paired_diff_ci(engine_series, actual_series),
        outscore_pvalue=sign_test_pvalue(wins, len(margins)),
    )


@dataclass
class LeagueH2HResult:
    """Every roster replayed with the same engine — does it beat the weaker managers?

    Guards against reading too much into a single roster: the engine losing to one strong
    manager (Rob's, say) and beating five weak ones are both true and both important. This
    is the league-wide view.
    """

    season: int
    league_id: str
    projector: str
    per_roster: list[H2HResult]

    @property
    def rosters_outscored(self) -> int:
        """How many managers the engine outscored on average over the season."""
        return sum(1 for r in self.per_roster if r.points_margin > 0)

    @property
    def rosters_out_allplayed(self) -> int:
        """How many managers the engine beat on all-play record (schedule-luck-free)."""
        return sum(1 for r in self.per_roster if r.engine_allplay_wins > r.actual_allplay_wins)

    def summary(self) -> str:
        """One-line league-wide verdict."""
        n = len(self.per_roster)
        return (
            f"{self.season} [{self.projector}]: engine would out-manage "
            f"{self.rosters_outscored}/{n} rosters on points, "
            f"{self.rosters_out_allplayed}/{n} on all-play record"
        )


def run_league_h2h(
    season: int,
    projector_name: str = "engine",
    min_week: int = _DEFAULT_MIN_WEEK,
    league_id: str | None = None,
) -> LeagueH2HResult:
    """Replay every roster in the league with the engine and rank it against each manager.

    The engine projector is built once and shared across all rosters (the per-player
    forecast cache is reused), so this costs barely more than a single-roster H2H.

    Args:
        season: Completed season to replay.
        projector_name: Label for the result.
        min_week: First week counted.
        league_id: Override the league.

    Returns:
        A :class:`LeagueH2HResult` with a per-roster :class:`H2HResult` list.

    Raises:
        ArenaUnavailableError: League/matchups unavailable.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        lid = league_id or _resolve_league_id(client, season)
        if lid is None:
            raise ArenaUnavailableError(f"no league in this dynasty's history for season {season}")
        roster_ids = sorted(int(r.roster_id) for r in client.rosters(lid))

    projector = make_engine_projector(season)
    per_roster: list[H2HResult] = []
    for rid in roster_ids:
        try:
            per_roster.append(
                run_h2h(
                    season,
                    roster_id=rid,
                    projector=projector,
                    projector_name=projector_name,
                    min_week=min_week,
                    league_id=lid,
                )
            )
        except ArenaUnavailableError as exc:
            log.warning("league_h2h: roster %s skipped: %s", rid, exc)
    if not per_roster:
        raise ArenaUnavailableError(f"no rosters produced scorable weeks for {season}")
    return LeagueH2HResult(
        season=season, league_id=lid, projector=projector_name, per_roster=per_roster
    )


def _score_h2h_week(
    week: int,
    matchups: list[dict],
    target: int,
    positions: dict[str, str],
    roster_positions: list[str],
    history: PointHistory,
    projector: Projector,
) -> tuple[float, float, float | None, list[float]] | None:
    """Engine/actual/opponent points and all other teams' actual points for one week.

    Returns ``None`` if the target roster has no scorable data this week.
    """
    by_roster = {int(r.get("roster_id", -1)): r for r in matchups}
    roster = by_roster.get(target)
    if roster is None:
        return None
    score = _replay_week(week, roster, positions, roster_positions, history, projector)
    if score is None:
        return None

    # Head-to-head opponent shares the target's matchup_id.
    my_mid = roster.get("matchup_id")
    opp_pts: float | None = None
    if my_mid is not None:
        for rid, r in by_roster.items():
            if rid != target and r.get("matchup_id") == my_mid:
                opp_pts = float(r.get("points") or 0.0)
                break

    others = [float(r.get("points") or 0.0) for rid, r in by_roster.items() if rid != target]
    return score.engine_pts, score.actual_pts, opp_pts, others


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
