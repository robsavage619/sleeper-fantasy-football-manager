"""In-house team Elo, computed live from the nflverse schedule we already cache.

Why in-house, not the 538 dataset
---------------------------------
Rob pointed at FiveThirtyEight's ``nfl-elo`` dataset. Two facts killed the ingest and
made the compute the right call instead (verified 2026-07-20):

* **The dataset is dead.** 538 was shut down; the GitHub directory now holds only a
  README pointing at ``projects.fivethirtyeight.com/nfl-api/*.csv``, and the model stopped
  updating after the 2022 season. Ingesting a static CSV that *looks* authoritative but
  silently freezes is the exact stale-data trap this codebase already learned the hard way
  (see the nflverse single-file cache bug). A number that stops moving but keeps being
  trusted is worse than no number.
* **We don't need it.** Elo is one line of arithmetic per game, and every input it needs —
  game date, final score, home/away/neutral, and the starting QBs — is already in
  :func:`sleeper_ffm.nflverse.loader.load_schedules`, which refreshes every week and
  covers 2014-present. So we compute our own: live, auditable, and with parameters we
  control instead of a black box.

The model
---------
Standard Elo with the two corrections 538 validated for the NFL, so the ratings track a
well-studied benchmark rather than a hand-rolled variant:

* **Margin-of-victory multiplier** — a blowout moves the rating more than a one-score
  game, but with diminishing returns (``ln(margin+1)``).
* **Autocorrelation correction** — the same multiplier is damped when a heavy favorite
  wins, so dominant teams don't run away on the strength of beating up weak schedules.

Parameters (:class:`EloParams`) are ours: ``k=20`` update speed, ``home_advantage=48``
Elo points (the modern NFL value; zeroed at neutral sites), and a ``1/3`` regression
toward the 1505 league mean each new season so a team's rating carries over between years
without ossifying.

What this is and isn't
----------------------
* It rates **teams**, not players. It is a team-strength prior, and its natural consumers
  are the surfaces that reason about game outcomes and future schedule: playoff-weeks
  strength of schedule (where Vegas has posted no lines yet), the season simulation's team
  strengths, and opponent adjustment of historical player production.
* It is **not** a fantasy-points model and must not be wired in as one. Team strength maps
  to player scoring only indirectly.
* **QB-adjusted Elo is deliberately not built here.** 538's QB adjustment is a genuine
  modeling project (rolling per-QB value, rookie priors, in-game replacement), not a
  parameter tweak. The schedule carries ``home_qb_id`` / ``away_qb_id``, so the door is
  open — but half-building it would be worse than leaving it clearly unbuilt.

Honest limits
-------------
* Elo knows only who won and by how much. It has no injury, weather, or roster input.
* Cold-start: a new season regresses toward the mean, so Week 1 ratings lean on last
  year. Expansion/relocation franchises inherit the league-mean prior.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.config import DEFAULT_VALUE_SEASON

log = logging.getLogger(__name__)

_MEAN_ELO = 1505.0
_FIRST_SCHEDULE_SEASON = 2014


@dataclass(frozen=True)
class EloParams:
    """Tunable Elo parameters. Defaults are the modern-NFL values 538 converged on."""

    k: float = 20.0
    home_advantage: float = 48.0
    # Fraction of the gap to the league mean that is regressed away each new season.
    season_regression: float = 1.0 / 3.0
    mean: float = _MEAN_ELO


@dataclass(frozen=True)
class TeamRating:
    """One team's current Elo and the game count behind it."""

    team: str
    elo: float
    games: int
    last_season: int
    last_week: int


@dataclass
class EloBoard:
    """Every team's current Elo rating, best first."""

    ratings: list[TeamRating] = field(default_factory=list)
    through_season: int = 0
    through_week: int = 0
    params: EloParams = field(default_factory=EloParams)

    def rating(self, team: str) -> float:
        """Current Elo for a team, or the league mean if the team is unseen."""
        for r in self.ratings:
            if r.team == team:
                return r.elo
        return self.params.mean

    def win_probability(self, home: str, away: str, neutral: bool = False) -> float:
        """Home team's win probability for a hypothetical matchup."""
        hfa = 0.0 if neutral else self.params.home_advantage
        return expected_score(self.rating(home) + hfa, self.rating(away))


def expected_score(elo_a: float, elo_b: float) -> float:
    """Logistic expectation that A beats B given their (HFA-adjusted) Elos.

    Args:
        elo_a: Team A's rating, already including any home-field bonus.
        elo_b: Team B's rating.

    Returns:
        A's win probability in ``(0, 1)``.
    """
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def mov_multiplier(point_margin: float, elo_diff_winner: float) -> float:
    """538's margin-of-victory multiplier with the autocorrelation correction.

    Bigger wins move the rating more (``ln``-damped), but the move is shrunk when the
    winner was already the favorite — otherwise a strong team's rating spirals upward by
    running up the score on weak opponents.

    Args:
        point_margin: Absolute final scoring margin (>= 0).
        elo_diff_winner: Winner's pregame Elo minus loser's (HFA-adjusted), signed from
            the winner's perspective. Positive when the favorite won.

    Returns:
        The multiplier applied to the base rating shift.
    """
    return math.log(abs(point_margin) + 1.0) * (2.2 / (elo_diff_winner * 0.001 + 2.2))


def update_pair(
    elo_home: float,
    elo_away: float,
    home_score: float,
    away_score: float,
    params: EloParams,
    neutral: bool = False,
) -> tuple[float, float]:
    """Return both teams' post-game Elo after one result.

    Args:
        elo_home: Home team's pregame Elo (before HFA).
        elo_away: Away team's pregame Elo.
        home_score: Home team's final score.
        away_score: Away team's final score.
        params: Elo parameters.
        neutral: True to zero out home-field advantage.

    Returns:
        ``(elo_home_post, elo_away_post)``. A tie splits the result at 0.5 and applies no
        margin multiplier (there is no winner to key the autocorrelation term on).
    """
    hfa = 0.0 if neutral else params.home_advantage
    adj_home = elo_home + hfa
    expected_home = expected_score(adj_home, elo_away)

    if home_score > away_score:
        result, winner_diff = 1.0, adj_home - elo_away
    elif away_score > home_score:
        result, winner_diff = 0.0, elo_away - adj_home
    else:
        result, winner_diff = 0.5, 0.0

    margin = abs(home_score - away_score)
    mult = mov_multiplier(margin, winner_diff) if margin > 0 else 1.0
    shift = params.k * mult * (result - expected_home)
    return elo_home + shift, elo_away - shift


def _regress_to_mean(elo: float, params: EloParams) -> float:
    """Pull a rating a fraction of the way back to the league mean for a new season."""
    return elo + (params.mean - elo) * params.season_regression


def build_elo(
    through_season: int | None = None,
    through_week: int | None = None,
    params: EloParams | None = None,
) -> EloBoard:
    """Walk the cached schedule chronologically and return current team Elo.

    Args:
        through_season: Include games up to and including this season. Defaults to
            :data:`~sleeper_ffm.config.DEFAULT_VALUE_SEASON`.
        through_week: Within ``through_season`` only, stop after this week (inclusive).
            None includes the whole season. Ignored for earlier seasons, which are always
            counted in full.
        params: Elo parameters. Defaults to :class:`EloParams`.

    Returns:
        An :class:`EloBoard` of every team's current rating, highest first.
    """
    from sleeper_ffm.nflverse.loader import load_schedules

    params = params or EloParams()
    through_season = through_season or DEFAULT_VALUE_SEASON

    schedule = load_schedules()
    if schedule.is_empty():
        log.warning("elo: no schedule data; returning empty board")
        return EloBoard(through_season=through_season, params=params)

    games = _completed_games(schedule, through_season, through_week)
    if games.is_empty():
        log.warning("elo: no completed games through %s wk %s", through_season, through_week)
        return EloBoard(through_season=through_season, params=params)

    elo: dict[str, float] = {}
    games_played: dict[str, int] = {}
    last_seen: dict[str, tuple[int, int]] = {}
    prev_season: int | None = None

    for row in games.iter_rows(named=True):
        season = int(row["season"])
        if prev_season is not None and season != prev_season:
            # New season: regress everyone toward the mean before the first game counts.
            for team in elo:
                elo[team] = _regress_to_mean(elo[team], params)
        prev_season = season

        home, away = row["home_team"], row["away_team"]
        elo.setdefault(home, params.mean)
        elo.setdefault(away, params.mean)

        neutral = str(row.get("location") or "").lower() == "neutral"
        elo[home], elo[away] = update_pair(
            elo[home],
            elo[away],
            float(row["home_score"]),
            float(row["away_score"]),
            params,
            neutral=neutral,
        )
        for team in (home, away):
            games_played[team] = games_played.get(team, 0) + 1
            last_seen[team] = (season, int(row["week"]))

    ratings = [
        TeamRating(
            team=team,
            elo=round(value, 1),
            games=games_played.get(team, 0),
            last_season=last_seen.get(team, (through_season, 0))[0],
            last_week=last_seen.get(team, (through_season, 0))[1],
        )
        for team, value in elo.items()
    ]
    ratings.sort(key=lambda r: r.elo, reverse=True)

    last_week = max((r.last_week for r in ratings if r.last_season == through_season), default=0)
    return EloBoard(
        ratings=ratings,
        through_season=through_season,
        through_week=last_week,
        params=params,
    )


def _completed_games(
    schedule: pl.DataFrame,
    through_season: int,
    through_week: int | None,
) -> pl.DataFrame:
    """Chronologically-ordered completed games up to the requested cutoff."""
    df = schedule.filter(
        pl.col("home_score").is_not_null()
        & pl.col("away_score").is_not_null()
        & (pl.col("season") >= _FIRST_SCHEDULE_SEASON)
        & (pl.col("season") <= through_season)
    )
    if through_week is not None:
        df = df.filter((pl.col("season") < through_season) | (pl.col("week") <= through_week))
    sort_cols = ["season", "week"]
    if "gameday" in df.columns:
        sort_cols.append("gameday")
    return df.sort(sort_cols)
