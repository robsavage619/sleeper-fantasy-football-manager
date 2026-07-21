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

QB adjustment
-------------
:func:`walk_predictions` also runs a QB-adjusted track, 538's insight that a team is only
as strong as who is under center this week. Each start produces a box-score VALUE
(:func:`qb_game_value`, 538's coefficient formula); a per-QB rolling value tracks form; a
per-team rolling baseline tracks what the team has been getting from the position. The
pregame adjustment is ``(starter_value - team_baseline) / value_per_elo`` — start a QB
better than the team's norm and the rating rises, bench him for a backup and it falls.
Whether this actually predicts games better than plain team Elo is an empirical question,
not an assumption; :func:`sleeper_ffm.evals.backtest.run_elo_backtest` answers it — and the
answer is *barely*. Measured
----------------------------------------------------------------------------------------
``run_elo_backtest(through_season=2024, first_eval_season=2018)``, 1,935 decided games,
Brier score (lower better) and straight-up accuracy::

    home base-rate    0.2480      —
    team Elo          0.2226   63.3%
    QB-adjusted Elo   0.2219   63.5%
    Vegas (de-vigged) 0.2107   66.4%

Two verdicts fall out of that, and both are load-bearing:

* **Team Elo is real.** It beats the home base-rate comfortably and lands within ~5.7%
  (Brier) of the closing Vegas line — respectable for a model that sees only scores.
* **The QB adjustment is not worth it.** +0.31% Brier over team Elo is a rounding error,
  not the 1-2% 538 reported. It is kept because it is built, tested, and costs nothing to
  leave available, but it is **not** promoted as the default and nothing should depend on
  it beating the team track. Same lesson as the in-house forecast that lost to rotowire:
  measure, then don't oversell.

Because Vegas wins wherever a line exists, team Elo earns its keep only where Vegas is
*absent* — future weeks with no posted line, i.e. the fantasy-playoff strength of
schedule. That, and only that, is where it is wired in.

What this is and isn't
----------------------
* It rates **teams**, not players. Its natural consumer is playoff-weeks strength of
  schedule — the one place a live, forward-looking opponent-strength read beats what's
  already here (Vegas posts no lines that far out, and DvP there leans on last year).
* **Not** a valid input to the fantasy season simulation, despite an earlier claim of
  mine: that sim rates *fantasy* rosters keyed by ``roster_id``, a different domain from
  NFL team strength. Nor is it an obvious win for opponent adjustment, which already uses
  the more targeted defense-vs-position. Team strength maps to player scoring only
  indirectly; it is not a fantasy-points model.

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
    # --- QB adjustment ---
    # Weight on the latest start when updating a QB's rolling value (~10-game memory).
    qb_weight: float = 0.1
    # Box-score VALUE points per Elo point (538's scale).
    qb_value_per_elo: float = 3.3
    # Starting value for a QB with no history — a below-average-starter prior.
    qb_rookie_value: float = 40.0
    # How fast a team's own QB baseline tracks its recent starters.
    qb_baseline_weight: float = 0.1


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


# 538's QB game-VALUE coefficients (points). A neutral start lands near the league mean
# starter value; elite games run higher, disasters go negative.
_QB_VALUE = {
    "attempts": -2.2,
    "completions": 3.7,
    "passing_yards": 1.0 / 5.0,
    "passing_tds": 11.3,
    "interceptions": -14.1,
    "sacks_suffered": -8.0,
    "sack_yards_lost": -1.1,
    "rushing_yards": 0.6,
    "rushing_tds": 15.9,
}


def qb_game_value(stats: dict[str, float]) -> float:
    """538's single-game quarterback VALUE from a box-score line.

    Args:
        stats: nflverse weekly stat keys for one QB-game. Missing keys count as zero.

    Returns:
        The VALUE in 538's points. Roughly centered on the league starter average; a
        clean multi-TD game runs well above it, a multi-pick game below zero.
    """
    return sum(coef * float(stats.get(key, 0.0) or 0.0) for key, coef in _QB_VALUE.items())


@dataclass(frozen=True)
class GamePrediction:
    """One game's pregame win probabilities under each Elo variant, plus the outcome."""

    season: int
    week: int
    home_team: str
    away_team: str
    team_elo_prob: float  # home win prob, team Elo only
    qb_elo_prob: float  # home win prob, QB-adjusted Elo
    vegas_prob: float | None  # home win prob implied by the moneyline, when present
    home_won: bool
    tie: bool


def walk_predictions(
    through_season: int | None = None,
    params: EloParams | None = None,
    qb_values: dict[tuple[str, int, int], float] | None = None,
) -> list[GamePrediction]:
    """Replay the schedule and record each game's *pregame* prediction under each variant.

    This is the substrate for :func:`sleeper_ffm.evals.backtest.run_elo_backtest`: every
    probability is recorded strictly before the game's result is used to update any
    rating, so scoring these against outcomes is a genuine out-of-sample test.

    Args:
        through_season: Include games up to and including this season.
        params: Elo parameters.
        qb_values: ``{(qb_id, season, week): value}`` from :func:`load_qb_values`. When
            None, the QB track mirrors the team track (no adjustment).

    Returns:
        One :class:`GamePrediction` per completed game, in chronological order.
    """
    from sleeper_ffm.nflverse.loader import load_schedules

    params = params or EloParams()
    through_season = through_season or DEFAULT_VALUE_SEASON
    qb_values = qb_values or {}

    schedule = load_schedules()
    if schedule.is_empty():
        return []
    games = _completed_games(schedule, through_season, None)

    team_elo: dict[str, float] = {}
    qb_elo: dict[str, float] = {}  # team base for the QB-adjusted track
    qb_value: dict[str, float] = {}  # per-QB rolling value
    team_qb_baseline: dict[str, float] = {}  # per-team rolling QB value
    prev_season: int | None = None
    predictions: list[GamePrediction] = []

    for row in games.iter_rows(named=True):
        season = int(row["season"])
        week = int(row["week"])
        if prev_season is not None and season != prev_season:
            for team in team_elo:
                team_elo[team] = _regress_to_mean(team_elo[team], params)
            for team in qb_elo:
                qb_elo[team] = _regress_to_mean(qb_elo[team], params)
        prev_season = season

        home, away = row["home_team"], row["away_team"]
        for store in (team_elo, qb_elo):
            store.setdefault(home, params.mean)
            store.setdefault(away, params.mean)
        team_qb_baseline.setdefault(home, params.qb_rookie_value)
        team_qb_baseline.setdefault(away, params.qb_rookie_value)

        neutral = str(row.get("location") or "").lower() == "neutral"
        hfa = 0.0 if neutral else params.home_advantage

        team_prob = expected_score(team_elo[home] + hfa, team_elo[away])

        home_qb, away_qb = row.get("home_qb_id"), row.get("away_qb_id")
        home_qb_val = qb_value.get(home_qb, params.qb_rookie_value) if home_qb else None
        away_qb_val = qb_value.get(away_qb, params.qb_rookie_value) if away_qb else None
        home_adj = _qb_adjustment(home_qb_val, team_qb_baseline[home], params)
        away_adj = _qb_adjustment(away_qb_val, team_qb_baseline[away], params)
        qb_prob = expected_score(qb_elo[home] + hfa + home_adj, qb_elo[away] + away_adj)

        home_score, away_score = float(row["home_score"]), float(row["away_score"])
        tie = home_score == away_score
        home_won = home_score > away_score

        predictions.append(
            GamePrediction(
                season=season,
                week=week,
                home_team=home,
                away_team=away,
                team_elo_prob=round(team_prob, 4),
                qb_elo_prob=round(qb_prob, 4),
                vegas_prob=_moneyline_prob(row),
                home_won=home_won,
                tie=tie,
            )
        )

        # Post-game updates (never before the prediction is recorded).
        team_elo[home], team_elo[away] = update_pair(
            team_elo[home], team_elo[away], home_score, away_score, params, neutral=neutral
        )
        qb_elo[home], qb_elo[away] = update_pair(
            qb_elo[home], qb_elo[away], home_score, away_score, params, neutral=neutral
        )
        _update_qb(home_qb, home, season, week, qb_value, team_qb_baseline, qb_values, params)
        _update_qb(away_qb, away, season, week, qb_value, team_qb_baseline, qb_values, params)

    return predictions


def _qb_adjustment(qb_val: float | None, team_baseline: float, params: EloParams) -> float:
    """Elo points to add for a starter whose value differs from his team's norm."""
    if qb_val is None:
        return 0.0
    return (qb_val - team_baseline) / params.qb_value_per_elo


def _update_qb(
    qb_id: str | None,
    team: str,
    season: int,
    week: int,
    qb_value: dict[str, float],
    team_qb_baseline: dict[str, float],
    qb_values: dict[tuple[str, int, int], float],
    params: EloParams,
) -> None:
    """Roll a starter's value and his team's baseline forward after a start."""
    if not qb_id:
        return
    game_value = qb_values.get((qb_id, season, week))
    if game_value is None:
        return
    prior = qb_value.get(qb_id, params.qb_rookie_value)
    qb_value[qb_id] = prior * (1 - params.qb_weight) + game_value * params.qb_weight
    base = team_qb_baseline.get(team, params.qb_rookie_value)
    team_qb_baseline[team] = (
        base * (1 - params.qb_baseline_weight) + qb_value[qb_id] * params.qb_baseline_weight
    )


def _moneyline_prob(row: dict) -> float | None:
    """Vig-free home win probability from the two moneylines, or None if absent."""
    home_ml, away_ml = row.get("home_moneyline"), row.get("away_moneyline")
    if home_ml is None or away_ml is None:
        return None
    home_imp, away_imp = _american_to_prob(home_ml), _american_to_prob(away_ml)
    total = home_imp + away_imp
    if total <= 0:
        return None
    return round(home_imp / total, 4)  # de-vig by normalizing the two implied probs


def _american_to_prob(moneyline: float) -> float:
    """Implied probability from an American moneyline (with the vig still in)."""
    ml = float(moneyline)
    if ml < 0:
        return -ml / (-ml + 100.0)
    return 100.0 / (ml + 100.0)


def load_qb_values(through_season: int) -> dict[tuple[str, int, int], float]:
    """Per-start QB VALUE keyed by ``(qb_id, season, week)`` from cached weekly stats.

    Args:
        through_season: Latest season to load (from 2014).

    Returns:
        A lookup usable as :func:`walk_predictions`' ``qb_values`` argument. Empty when no
        weekly data is cached.
    """
    from sleeper_ffm.nflverse.loader import load_weekly

    seasons = list(range(_FIRST_SCHEDULE_SEASON, through_season + 1))
    weekly = load_weekly(seasons)
    if weekly.is_empty() or "position" not in weekly.columns:
        return {}
    qbs = weekly.filter(pl.col("position") == "QB")
    keys = [*_QB_VALUE, "player_id", "season", "week"]
    present = [c for c in keys if c in qbs.columns]
    out: dict[tuple[str, int, int], float] = {}
    for row in qbs.select(present).iter_rows(named=True):
        pid = row.get("player_id")
        if not pid:
            continue
        out[(str(pid), int(row["season"]), int(row["week"]))] = qb_game_value(row)
    return out


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
