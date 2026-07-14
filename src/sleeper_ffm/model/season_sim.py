"""Monte-Carlo season simulation → playoff and championship equity.

Turns roster strength into the only currency that matters in a dynasty *contend*
window: probability of a title. Each remaining fantasy week, every team draws a score
from a normal centered on its weekly strength; head-to-head results accumulate into
wins and points-for; the field is seeded and a single-elimination bracket is played
out; repeat thousands of times.

The value is downstream: once a title probability exists, any move — a trade, a waiver,
a start/sit — can be scored by its *delta* on championship equity instead of by raw
asset value. "This trade is +4 value" becomes "this trade is +6% to win it all," which
is the number that should actually drive a contender's decisions.

Two layers, mirroring the rest of the codebase:
    * pure, seeded simulation core (``simulate`` / ``round_robin_schedule`` / bracket) —
      deterministic given a seed, unit-tested without any I/O;
    * ``build_season_sim`` — assembles team strengths from rostered players' per-game FP
      and runs the core, degrading to a balanced round-robin when no live fantasy
      schedule exists yet (the normal off-season state).
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, LEAGUE_ID, MY_ROSTER_ID

log = logging.getLogger(__name__)

# Standard fantasy lineup for this league (1QB / no K / no DST): QB, 2RB, 3WR, TE, 2FLEX.
_LINEUP_SLOTS: tuple[tuple[str, int], ...] = (("QB", 1), ("RB", 2), ("WR", 3), ("TE", 1))
_FLEX_COUNT: int = 2
_FLEX_POS: frozenset[str] = frozenset({"RB", "WR", "TE"})
# Week-to-week fantasy scoring noise: a floor plus a fraction of the team's mean.
_STD_FLOOR: float = 18.0
_STD_FRACTION: float = 0.18
_DEFAULT_SIMS: int = 4000
_DEFAULT_SEED: int = 20260714


@dataclass
class TeamOdds:
    """Simulated season outcomes for one roster."""

    roster_id: int
    strength: float  # projected weekly points (lineup mean)
    playoff_odds: float  # fraction of sims making the playoff field
    title_odds: float  # fraction of sims winning the championship
    bye_odds: float  # fraction earning a first-round bye
    avg_wins: float
    avg_seed: float
    is_me: bool = False


@dataclass
class SeasonSim:
    """Full Monte-Carlo season projection."""

    season: int
    n_sims: int
    regular_weeks: int
    playoff_teams: int
    schedule_source: str  # "sleeper" | "round_robin"
    teams: list[TeamOdds]  # sorted by title odds desc
    warnings: list[str] = field(default_factory=list)


def round_robin_schedule(team_ids: list[int], weeks: int) -> list[tuple[int, int, int]]:
    """Build a balanced round-robin as ``[(week, home, away), ...]``.

    Uses the circle method, cycling if ``weeks`` exceeds one full rotation. A bye
    (odd team count) is represented by the sentinel dropping that pairing.
    """
    ids = list(team_ids)
    if len(ids) < 2:
        return []
    bye = None
    if len(ids) % 2:
        bye = -1
        ids = [*ids, bye]
    n = len(ids)
    fixtures: list[tuple[int, int, int]] = []
    rotation = ids[:]
    for wk in range(1, weeks + 1):
        for i in range(n // 2):
            home, away = rotation[i], rotation[n - 1 - i]
            if bye not in (home, away):
                fixtures.append((wk, home, away))
        # rotate all but the first element
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    return fixtures


def _play_game(
    a: int, b: int, strength: dict[int, float], std: dict[int, float], rng: random.Random
) -> int:
    """Return the winner of one game (ties broken by a coin flip)."""
    sa = rng.gauss(strength[a], std[a])
    sb = rng.gauss(strength[b], std[b])
    if sa == sb:
        return a if rng.random() < 0.5 else b
    return a if sa > sb else b


def _sim_bracket(
    seeded: list[int], strength: dict[int, float], std: dict[int, float], rng: random.Random
) -> tuple[int, set[int]]:
    """Play a reseeding single-elimination bracket; return (champion, teams_with_byes)."""
    alive = list(seeded)
    byes_awarded: set[int] = set()
    first_round = True
    while len(alive) > 1:
        n = len(alive)
        lower_pow2 = 2 ** int(math.log2(n))
        byes = (2 * lower_pow2 - n) if n != lower_pow2 else 0
        bye_teams = alive[:byes]
        if first_round:
            byes_awarded = set(bye_teams)
            first_round = False
        playing = alive[byes:]
        winners: list[int] = []
        i, j = 0, len(playing) - 1
        while i < j:
            winners.append(_play_game(playing[i], playing[j], strength, std, rng))
            i += 1
            j -= 1
        alive = sorted(bye_teams + winners, key=seeded.index)
    return alive[0], byes_awarded


def simulate(
    strength: dict[int, float],
    schedule: list[tuple[int, int, int]],
    playoff_teams: int,
    std: dict[int, float] | None = None,
    n_sims: int = _DEFAULT_SIMS,
    seed: int = _DEFAULT_SEED,
) -> dict[int, dict[str, float]]:
    """Monte-Carlo simulate the season; return per-team aggregate outcomes.

    Args:
        strength: ``{roster_id: mean weekly points}``.
        schedule: Remaining ``(week, home, away)`` fantasy matchups.
        playoff_teams: Size of the playoff field.
        std: ``{roster_id: weekly std}``; derived from strength if None.
        n_sims: Number of simulated seasons.
        seed: RNG seed for determinism.

    Returns:
        ``{roster_id: {playoff, title, bye, wins, seed}}`` with fractional odds and
        averaged wins/seed over all sims.
    """
    ids = list(strength.keys())
    if std is None:
        std = {t: max(_STD_FLOOR, _STD_FRACTION * strength[t]) for t in ids}
    rng = random.Random(seed)

    tally = {t: {"playoff": 0, "title": 0, "bye": 0, "wins": 0.0, "seed": 0.0} for t in ids}

    for _ in range(n_sims):
        wins = dict.fromkeys(ids, 0)
        points = dict.fromkeys(ids, 0.0)
        for _wk, home, away in schedule:
            sh = rng.gauss(strength[home], std[home])
            sa = rng.gauss(strength[away], std[away])
            points[home] += sh
            points[away] += sa
            if sh >= sa:
                wins[home] += 1
            else:
                wins[away] += 1
        # Seed by (wins, points-for).
        standings = sorted(ids, key=lambda t: (wins[t], points[t]), reverse=True)
        field_ids = standings[:playoff_teams]
        champion, byes = _sim_bracket(field_ids, strength, std, rng)
        for rank, t in enumerate(standings, start=1):
            tally[t]["wins"] += wins[t]
            tally[t]["seed"] += rank
        for t in field_ids:
            tally[t]["playoff"] += 1
        for t in byes:
            tally[t]["bye"] += 1
        tally[champion]["title"] += 1

    out: dict[int, dict[str, float]] = {}
    for t in ids:
        out[t] = {
            "playoff": tally[t]["playoff"] / n_sims,
            "title": tally[t]["title"] / n_sims,
            "bye": tally[t]["bye"] / n_sims,
            "wins": round(tally[t]["wins"] / n_sims, 2),
            "seed": round(tally[t]["seed"] / n_sims, 2),
        }
    return out


def _lineup_strength(per_game: dict[str, tuple[str, float]]) -> float:
    """Sum a roster's optimal lineup of per-game FP into a weekly team mean.

    Args:
        per_game: ``{player_id: (position, per_game_fp)}`` for one roster.

    Returns:
        Projected weekly points for the roster's best legal lineup.
    """
    by_pos: dict[str, list[float]] = {}
    for pos, fp in per_game.values():
        by_pos.setdefault(pos, []).append(fp)
    for pos in by_pos:
        by_pos[pos].sort(reverse=True)

    total = 0.0
    used_flex_pool: list[float] = []
    for pos, count in _LINEUP_SLOTS:
        vals = by_pos.get(pos, [])
        total += sum(vals[:count])
        used_flex_pool.extend(vals[count:] if pos in _FLEX_POS else [])
    used_flex_pool.sort(reverse=True)
    total += sum(used_flex_pool[:_FLEX_COUNT])
    return round(total, 1)


def _playoff_settings() -> tuple[int, int]:
    """Return (playoff_teams, regular_weeks) from the cached league settings."""
    import json

    from sleeper_ffm.config import DATA_DIR

    try:
        with open(DATA_DIR / "league_settings.json") as fh:
            s = json.load(fh).get("settings", {})
        playoff_teams = int(s.get("playoff_teams", 6))
        regular_weeks = int(s.get("playoff_week_start", 15)) - 1
        return playoff_teams, regular_weeks
    except (OSError, ValueError, KeyError):
        return 6, 14


def build_season_sim(n_sims: int = _DEFAULT_SIMS, seed: int = _DEFAULT_SEED) -> SeasonSim:
    """Assemble team strengths from rosters and Monte-Carlo the season.

    Returns:
        A :class:`SeasonSim`. Degrades to a balanced round-robin schedule when no live
        fantasy schedule is available (the normal off-season case).
    """
    from sleeper_ffm.model.valuation import compute_season_totals
    from sleeper_ffm.sleeper.client import SleeperClient

    warnings: list[str] = []
    with SleeperClient() as c:
        rosters = c.rosters(LEAGUE_ID)
        players = c.players()

    totals = compute_season_totals(seasons=[DEFAULT_VALUE_SEASON])
    per_game_fp: dict[str, float] = {}
    if not totals.is_empty() and "sleeper_id_str" in totals.columns:
        for row in totals.iter_rows(named=True):
            sid = row.get("sleeper_id_str")
            if sid:
                # season_fp is already normalized to a 17-game total → /17 = per game.
                per_game_fp[sid] = float(row.get("season_fp") or 0.0) / 17.0
    else:
        warnings.append("No scored season totals; team strengths fall back to roster size only.")

    strength: dict[int, float] = {}
    for r in rosters:
        pg: dict[str, tuple[str, float]] = {}
        for pid in r.players or []:
            meta = players.get(pid, {})
            pos = meta.get("position")
            if pos in _FLEX_POS or pos == "QB":
                pg[pid] = (pos, per_game_fp.get(pid, 0.0))
        strength[r.roster_id] = max(_lineup_strength(pg), _STD_FLOOR)

    playoff_teams, regular_weeks = _playoff_settings()
    schedule = round_robin_schedule(list(strength.keys()), regular_weeks)
    schedule_source = "round_robin"
    warnings.append(
        "Live fantasy schedule not used (off-season / unavailable); simulated over a "
        "balanced round-robin, so odds reflect roster strength, not a specific slate."
    )

    odds = simulate(strength, schedule, playoff_teams, n_sims=n_sims, seed=seed)
    id_to_owner = {r.roster_id: r for r in rosters}
    teams = [
        TeamOdds(
            roster_id=rid,
            strength=strength[rid],
            playoff_odds=round(o["playoff"], 4),
            title_odds=round(o["title"], 4),
            bye_odds=round(o["bye"], 4),
            avg_wins=o["wins"],
            avg_seed=o["seed"],
            is_me=(rid == MY_ROSTER_ID and id_to_owner.get(rid) is not None),
        )
        for rid, o in odds.items()
    ]
    teams.sort(key=lambda t: t.title_odds, reverse=True)

    return SeasonSim(
        season=DEFAULT_VALUE_SEASON,
        n_sims=n_sims,
        regular_weeks=regular_weeks,
        playoff_teams=playoff_teams,
        schedule_source=schedule_source,
        teams=teams,
        warnings=warnings,
    )
