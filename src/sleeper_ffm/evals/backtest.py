"""Out-of-sample backtests — the ONE genuinely predictive validation family in this repo.

Everything else in ``evals/`` re-checks that a formula reproduces its own previously
recorded output (a regression detector, not a correctness check — see the 07-16 audit,
finding #11). The functions here are different: each fits or reads a model on one
season and scores it against a season it never saw, using realized outcomes as ground
truth. That is a real correctness signal, not just a change detector.

Three validations live in this module:

    * :func:`run_redzone_backtest` — the original: red-zone-opportunity expected-TD
      model (trained on one season) vs. a flat yardage baseline, scored out-of-sample.
      Fully hermetic (on-disk nflverse parquet cache only).
    * :func:`run_age_curve_backtest` — validates the dynasty age-curve's one-year FPAR
      projection (``model/dynasty.py``'s ``_PEAK_AGE``/``_DECAY_RATE``/``_ASCENT_RATE``)
      against realized next-season FPAR, vs. a "no aging" flat-carry baseline. Fully
      hermetic (on-disk nflverse parquet cache only).
    * :func:`run_season_sim_backtest` — validates Monte-Carlo playoff/title odds
      against one season's REALIZED bracket. Requires live Sleeper API calls (no
      on-disk cache of historical matchups/brackets exists in this repo) and is a
      single-season sample — read its docstring before citing a number from it.

``trade_acceptance_validation_status`` documents the one case where no ground-truth
data exists at all: there is no accepted/rejected/countered outcome log to score the
trade-acceptance formula against, so no backtest is attempted for it. See its docstring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import polars as pl

from sleeper_ffm.model.regression import _aggregate_rows, compute_td_regression
from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.nflverse.loader import load_id_map, load_pbp
from sleeper_ffm.scoring.engine import load_scoring

log = logging.getLogger(__name__)

_MIN_YARDS = 250


class BacktestUnavailableError(RuntimeError):
    """Raised when the cached data needed to run the backtest is missing."""


@dataclass
class BacktestResult:
    """Out-of-sample expected-TD accuracy for both models on one train→eval split."""

    train_season: int
    eval_season: int
    n_players: int
    mae_redzone: float
    mae_yardage: float
    improvement_pct: float  # (mae_yardage - mae_redzone) / mae_yardage, as a percentage


def _play_values(season: int) -> pl.DataFrame:
    """Play-level FP/TD values for a season, or empty if PBP isn't cached."""
    from sleeper_ffm.model.sabermetrics import pbp_play_value

    pbp = load_pbp(seasons=[season])
    if pbp.is_empty():
        return pbp
    return pbp_play_value(pbp, load_scoring())


def _position_by_player() -> dict[str, str]:
    """gsis_id → position from the nflverse ID crosswalk, skill positions only."""
    id_map = load_id_map()
    out: dict[str, str] = {}
    for r in id_map.select(["gsis_id", "position"]).iter_rows(named=True):
        gsis, pos = r.get("gsis_id"), r.get("position")
        if gsis and pos in SKILL_POSITIONS:
            out[gsis] = pos
    return out


def run_redzone_backtest(
    train_season: int,
    eval_season: int,
    min_yards: int = _MIN_YARDS,
) -> BacktestResult:
    """Measure out-of-sample expected-TD MAE for both models on one train→eval split.

    Args:
        train_season: Season the TD rates / yardage baselines are fit on.
        eval_season: Held-out season the fitted models are scored against.
        min_yards: Minimum eval-season yardage for a player to enter the sample
            (the same low-sample noise guard the live engine uses).

    Returns:
        A :class:`BacktestResult` with both models' MAE and the relative improvement.

    Raises:
        BacktestUnavailableError: If either season lacks cached play-by-play, or no
            player clears ``min_yards`` in the eval season.
    """
    from sleeper_ffm.model.sabermetrics import player_redzone_opportunities, redzone_td_rates

    train_rows = _aggregate_rows(train_season)
    eval_rows = _aggregate_rows(eval_season)
    if not train_rows or not eval_rows:
        raise BacktestUnavailableError(f"weekly stats missing for {train_season} or {eval_season}")

    train_plays = _play_values(train_season)
    eval_plays = _play_values(eval_season)
    if train_plays.is_empty() or eval_plays.is_empty():
        raise BacktestUnavailableError(f"play-by-play missing for {train_season} or {eval_season}")

    pos_map = _position_by_player()

    # Fit both models on the train season only.
    trained_rates = redzone_td_rates(train_plays, pos_map)
    yardage_baselines, _ = compute_td_regression(train_rows, min_yards=min_yards)

    abs_err_rz: list[float] = []
    abs_err_yd: list[float] = []
    for r in eval_rows:
        pos = r["position"]
        gsis = r.get("gsis_id")
        if r["total_yards"] < min_yards or not gsis:
            continue
        pos_rates = trained_rates.get(pos)
        yd_rate = yardage_baselines.get(pos)
        if pos_rates is None or yd_rate is None:
            continue

        actual = r["total_tds"]
        opps = player_redzone_opportunities(eval_plays, gsis)
        expected_rz = sum(opps.get(k, 0.0) * pos_rates.get(k, 0.0) for k in opps)
        expected_yd = r["total_yards"] * yd_rate
        abs_err_rz.append(abs(actual - expected_rz))
        abs_err_yd.append(abs(actual - expected_yd))

    n = len(abs_err_rz)
    if n == 0:
        raise BacktestUnavailableError(f"no players cleared {min_yards} yards in {eval_season}")

    mae_rz = sum(abs_err_rz) / n
    mae_yd = sum(abs_err_yd) / n
    improvement = ((mae_yd - mae_rz) / mae_yd * 100.0) if mae_yd else 0.0
    return BacktestResult(
        train_season=train_season,
        eval_season=eval_season,
        n_players=n,
        mae_redzone=round(mae_rz, 4),
        mae_yardage=round(mae_yd, 4),
        improvement_pct=round(improvement, 2),
    )


# ---------------------------------------------------------------------------
# Age-curve one-year FPAR projection — validated against realized next-season FPAR
# ---------------------------------------------------------------------------

# Reference date used to compute a player's age "as of" a given season — the
# standard fantasy convention (roughly the start of the NFL season). Sourced from
# nflverse's ``birthdate`` column, NOT the live Sleeper age (which is "today's"
# age and would be 1-2 years stale for a backtest against a past season).
_AGE_REFERENCE_MONTH_DAY: tuple[int, int] = (9, 1)

# Ignore players below this train-season FPAR: replacement-level/scrub seasons are
# mostly noise (small-sample QB spot starts, waiver-wire flashes) and would swamp
# the signal the age curve is actually meant to capture — established producers'
# trajectories.
_MIN_TRAIN_FPAR: float = 10.0


@dataclass
class AgeCurveBacktestResult:
    """Out-of-sample validation of the dynasty age-curve's one-year FPAR projection.

    Compares two ways of predicting a player's ``eval_season`` FPAR from their
    ``train_season`` FPAR: applying one year of the position's age-curve growth/decay
    (ascending pre-peak, decaying post-peak) vs. a naive "no aging" flat carry-forward.
    """

    train_season: int
    eval_season: int
    n_players: int
    mae_age_curve: float
    mae_naive_flat: float
    improvement_pct: float  # (mae_naive_flat - mae_age_curve) / mae_naive_flat, as a %
    n_directional: int  # players the curve predicted a direction for (excludes at-peak)
    direction_hit_rate: float  # fraction where predicted sign matched actual FPAR change


def _season_age(birthdate: str | None, season: int) -> float | None:
    """Decimal age as of ``_AGE_REFERENCE_MONTH_DAY`` of ``season``, or None if unknown."""
    if not birthdate:
        return None
    try:
        year, month, day = (int(part) for part in birthdate.split("-"))
        born = date(year, month, day)
    except ValueError:
        return None
    reference = date(season, *_AGE_REFERENCE_MONTH_DAY)
    return (reference - born).days / 365.25


def _fpar_by_player(season: int) -> dict[str, tuple[float, str, float | None]]:
    """``{gsis_id: (fpar, position, age_at_season)}`` for one season's skill players.

    Reads only the on-disk nflverse cache: weekly stats (via
    :func:`sleeper_ffm.model.valuation.compute_season_totals`) for FPAR, and the ID
    crosswalk's ``birthdate`` column for season-specific age.
    """
    from sleeper_ffm.model.valuation import compute_season_totals, replacement_thresholds

    totals = compute_season_totals(seasons=[season])
    if totals.is_empty():
        return {}
    thresholds = replacement_thresholds(totals)

    id_map = load_id_map()
    birthdates: dict[str, str] = {}
    if "birthdate" in id_map.columns:
        for row in id_map.select(["gsis_id", "birthdate"]).iter_rows(named=True):
            gsis = row.get("gsis_id")
            bday = row.get("birthdate")
            if gsis and bday:
                birthdates[gsis] = bday

    out: dict[str, tuple[float, str, float | None]] = {}
    for row in totals.iter_rows(named=True):
        gsis = row["gsis_id"]
        pos = row["position"]
        if pos not in SKILL_POSITIONS or not gsis:
            continue
        repl = thresholds.get(pos, 0.0)
        fpar = max(0.0, float(row["season_fp"]) - repl)
        age = _season_age(birthdates.get(gsis), season)
        out[gsis] = (fpar, pos, age)
    return out


def run_age_curve_backtest(
    train_season: int,
    eval_season: int,
    min_train_fpar: float = _MIN_TRAIN_FPAR,
) -> AgeCurveBacktestResult:
    """Validate the age curve's one-year FPAR projection against realized next-season FPAR.

    For each player with enough ``train_season`` production, projects one year forward
    two ways:
        * **age curve** — ``train_fpar * decay_rate[pos]`` if past positional peak,
          else ``train_fpar * ascent_rate[pos]`` (the same per-step multipliers
          ``model/dynasty.py``'s ``value_player`` compounds over the full projection
          horizon — this checks the very first step against reality).
        * **naive flat** — ``train_fpar`` unchanged (the "no aging" baseline the age
          curve is supposed to beat).

    Both are compared against the player's actual ``eval_season`` FPAR by mean
    absolute error. A separate directional check asks: excluding players the curve
    calls "at peak" (no predicted direction), did the predicted sign of change
    (up if pre-peak, down if post-peak) match the sign of the realized change?

    Args:
        train_season: Season FPAR/age are read from.
        eval_season: The following season, held out — its FPAR is never used to fit
            anything, only to score the prediction.
        min_train_fpar: Minimum train-season FPAR to enter the sample (noise guard).

    Returns:
        An :class:`AgeCurveBacktestResult`.

    Raises:
        BacktestUnavailableError: If either season lacks cached weekly stats, or no
            player with a known birthdate clears ``min_train_fpar`` in both seasons.
    """
    from sleeper_ffm.model.dynasty import _ASCENT_RATE, _DECAY_RATE, _PEAK_AGE

    train = _fpar_by_player(train_season)
    ev = _fpar_by_player(eval_season)
    if not train or not ev:
        raise BacktestUnavailableError(f"weekly stats missing for {train_season} or {eval_season}")

    err_curve: list[float] = []
    err_naive: list[float] = []
    direction_hits = 0
    n_directional = 0

    for gsis, (train_fpar, pos, age) in train.items():
        if train_fpar < min_train_fpar or age is None:
            continue
        eval_row = ev.get(gsis)
        if eval_row is None:
            continue
        actual_fpar = eval_row[0]

        peak_age = _PEAK_AGE.get(pos, 26)
        if age >= peak_age:
            predicted = train_fpar * _DECAY_RATE.get(pos, 0.88)
            predicted_direction = -1
        else:
            predicted = train_fpar * _ASCENT_RATE.get(pos, 1.05)
            predicted_direction = 1

        err_curve.append(abs(actual_fpar - predicted))
        err_naive.append(abs(actual_fpar - train_fpar))

        if actual_fpar > train_fpar:
            actual_direction = 1
        elif actual_fpar < train_fpar:
            actual_direction = -1
        else:
            actual_direction = 0
        if actual_direction != 0:
            n_directional += 1
            if actual_direction == predicted_direction:
                direction_hits += 1

    n = len(err_curve)
    if n == 0:
        raise BacktestUnavailableError(
            f"no players cleared {min_train_fpar} train FPAR with a known age in "
            f"{train_season}->{eval_season}"
        )

    mae_curve = sum(err_curve) / n
    mae_naive = sum(err_naive) / n
    improvement = ((mae_naive - mae_curve) / mae_naive * 100.0) if mae_naive else 0.0
    hit_rate = round(direction_hits / n_directional, 4) if n_directional else 0.0

    return AgeCurveBacktestResult(
        train_season=train_season,
        eval_season=eval_season,
        n_players=n,
        mae_age_curve=round(mae_curve, 4),
        mae_naive_flat=round(mae_naive, 4),
        improvement_pct=round(improvement, 2),
        n_directional=n_directional,
        direction_hit_rate=hit_rate,
    )


# ---------------------------------------------------------------------------
# Trade acceptance formula — no ground truth exists; document the gap, don't fake it
# ---------------------------------------------------------------------------


def trade_acceptance_validation_status() -> dict:
    """Report whether the trade-acceptance formula can currently be backtested.

    ``model/trade_acceptance.py``'s ``_acceptance_score`` has no fit-on-one-season/
    score-on-the-next analog, because there is no ground truth to score it against:
    a real backtest would need historical (offer, outcome) pairs — did the partner
    actually accept, reject, or counter — and no such log exists.

    ``model/offer_log.py`` (the only persistent record of offers this app has made)
    tracks a single ``sent`` boolean: whether Rob acted on a recommendation, not what
    the partner did with it. There is no ``accepted``/``rejected``/``countered`` field
    anywhere in the log, the router, or the model. Inventing a plausible-looking
    "N% accuracy" number here would be worse than reporting the gap honestly (07-16
    audit finding #12 flags exactly this: hand-picked constants presented with a
    precision they haven't earned).

    This function inspects the live offer log so the gap is checked in code, not
    just asserted in a docstring — if outcome logging is ever added (07-16 audit
    P1 finding #6, "closed loop: recommend -> act -> outcome -> learn"), this
    function's ``validated`` field is the first thing that should flip to True,
    and a real backtest should be built at that point.

    Returns:
        A dict with ``validated`` (always False today), ``offers_logged``, and
        ``reason``.
    """
    from sleeper_ffm.model.offer_log import list_offers

    offers = list_offers()
    outcome_fields = {"accepted", "rejected", "countered", "outcome"}
    has_outcome_data = any(outcome_fields & set(offer) for offer in offers)

    return {
        "validated": has_outcome_data,
        "offers_logged": len(offers),
        "reason": (
            "offer_log.py tracks only `sent` (bool) -- whether Rob acted on a "
            "recommendation -- not what the partner actually did with it. There is "
            "no accepted/rejected/countered outcome field in the offer log, so there "
            "is no ground-truth dataset to fit or score the acceptance formula "
            "against. No backtest is attempted; see this function's docstring."
            if not has_outcome_data
            else "Outcome fields were found in the offer log -- a real backtest is "
            "now possible and should be built; this status check no longer applies."
        ),
    }


# ---------------------------------------------------------------------------
# Season-sim playoff/title odds — validated against one season's REALIZED bracket
# ---------------------------------------------------------------------------

# Regular-season week to cut strength estimation off at, before the odds are
# computed and compared to the eventual (already-known) bracket result. Deliberately
# mid-season: early enough that the outcome isn't a foregone conclusion, late enough
# that per-team scoring has settled past small-sample noise.
_DEFAULT_STRENGTH_CUTOFF_WEEK: int = 8


@dataclass
class SeasonSimBacktestResult:
    """Single-season calibration check: simulated playoff/title odds vs. what happened.

    Read the docstring on :func:`run_season_sim_backtest` before treating this as a
    calibration statistic -- n=1 realized season is a sanity check, not statistical
    validation.
    """

    season: str
    strength_through_week: int
    n_teams: int
    playoff_teams: int
    champion_roster_id: int
    champion_title_odds: float  # the simulated title probability for the actual champ
    champion_odds_rank: int  # the champion's rank by simulated title odds (1 = favorite)
    playoff_field_predicted_correctly: int  # of the realized playoff field, how many the
    # sim's top-`playoff_teams`-by-playoff_odds also placed in the field
    mean_title_odds_of_field: float  # sanity check: should exceed the non-field mean


def run_season_sim_backtest(
    season: str,
    strength_through_week: int = _DEFAULT_STRENGTH_CUTOFF_WEEK,
    n_sims: int = 4000,
    seed: int = 20260714,
) -> SeasonSimBacktestResult:
    """Validate Monte-Carlo playoff/title odds against one season's REALIZED bracket.

    DATA LIMITATION -- read this before citing a number from this function:

    Unlike :func:`run_redzone_backtest` and :func:`run_age_curve_backtest`, this
    validation is NOT hermetic. It requires live Sleeper API calls: historical
    per-week matchup scores and the realized playoff bracket have no on-disk cache
    anywhere in this repo (``sleeper/client.py`` disk-caches only the player dump;
    everything else -- rosters, matchups, brackets -- is an in-process TTL memo over
    a live HTTP call, never persisted). Building a hermetic version would require
    adding a historical-snapshot cache this codebase doesn't have; that's out of
    scope here, so this function degrades to :class:`BacktestUnavailableError` when
    the league/season/network isn't reachable, the same pattern
    ``tests/test_reconciliation.py`` already uses for its live-network checks.

    Even when it runs successfully, this is a SINGLE-SEASON SAMPLE: one realized
    champion and one realized playoff field. That is nowhere near enough data to
    confirm or refute probability calibration in the statistical sense (you would
    want dozens of season-outcomes to check whether teams given ~20% title odds
    actually win ~20% of the time). What this function DOES check, honestly:
        1. Did the eventual champion have above-average simulated title odds
           (a weak but real signal -- a well-specified model shouldn't rate the
           actual champion as a long shot most of the time)?
        2. How much overlap is there between the simulated top playoff-odds teams
           and the realized playoff field?
    Neither is a claim of calibration. Report the raw numbers, not a verdict.

    Args:
        season: Season string (e.g. ``"2024"``) to walk to via ``league_history()``.
        strength_through_week: Estimate each team's strength from weeks 1..this week
            only (must be well before the realized outcome is known from the data
            used to build the sim, i.e. before the playoffs started).
        n_sims: Monte-Carlo iterations.
        seed: RNG seed for determinism.

    Returns:
        A :class:`SeasonSimBacktestResult`.

    Raises:
        BacktestUnavailableError: If the season isn't found, the bracket hasn't
            resolved (season still in progress / never played), or no matchup data
            is available through ``strength_through_week``.
    """
    from sleeper_ffm.model.season_sim import round_robin_schedule, simulate
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        try:
            history = client.league_history()
        except Exception as exc:  # live network / API failure
            raise BacktestUnavailableError(f"league history unavailable: {exc}") from exc

        league = next((lg for lg in history if lg.season == season), None)
        if league is None:
            raise BacktestUnavailableError(f"season {season} not found in league history")

        try:
            rosters = client.rosters(league_id=league.league_id)
            bracket = client.winners_bracket(league_id=league.league_id)
        except Exception as exc:
            raise BacktestUnavailableError(f"rosters/bracket fetch failed: {exc}") from exc

        if not bracket or not any(m.w is not None for m in bracket):
            raise BacktestUnavailableError(f"season {season} has no resolved playoff bracket yet")

        weekly_points: dict[int, list[float]] = {r.roster_id: [] for r in rosters}
        for week in range(1, strength_through_week + 1):
            try:
                matchups = client.matchups(week, league_id=league.league_id)
            except Exception as exc:
                raise BacktestUnavailableError(
                    f"matchups fetch failed for week {week}: {exc}"
                ) from exc
            for m in matchups or []:
                rid = m.get("roster_id")
                pts = m.get("points")
                if rid in weekly_points and pts is not None:
                    weekly_points[rid].append(float(pts))

    strength = {
        rid: (sum(pts) / len(pts) if pts else 0.0) for rid, pts in weekly_points.items()
    }
    strength = {rid: s for rid, s in strength.items() if s > 0.0}
    if len(strength) < 4:
        raise BacktestUnavailableError(
            f"too few teams with scored matchups through week {strength_through_week}"
        )

    bracket_team_ids = {m.t1 for m in bracket} | {m.t2 for m in bracket}
    playoff_field: list[int] = sorted(t for t in bracket_team_ids if t is not None)
    champion_match = max(
        (m for m in bracket if m.place == 1 and m.w is not None), key=lambda m: m.r, default=None
    )
    if champion_match is None or champion_match.w is None:
        raise BacktestUnavailableError(f"season {season} bracket has no resolved championship game")
    champion = champion_match.w

    settings = league.settings or {}
    playoff_teams = int(settings.get("playoff_teams", 6))
    regular_weeks = int(settings.get("playoff_week_start", 15)) - 1

    schedule = round_robin_schedule(list(strength.keys()), max(regular_weeks, 1))
    odds = simulate(strength, schedule, playoff_teams, n_sims=n_sims, seed=seed)

    ranked = sorted(odds.items(), key=lambda kv: kv[1]["title"], reverse=True)
    champion_rank = next((i for i, (rid, _) in enumerate(ranked, start=1) if rid == champion), -1)
    sim_top_field = {rid for rid, _ in ranked[:playoff_teams]}
    overlap = len(sim_top_field & set(playoff_field))

    field_title_odds = [odds[rid]["title"] for rid in playoff_field if rid in odds]
    mean_field_odds = sum(field_title_odds) / len(field_title_odds) if field_title_odds else 0.0

    return SeasonSimBacktestResult(
        season=season,
        strength_through_week=strength_through_week,
        n_teams=len(strength),
        playoff_teams=playoff_teams,
        champion_roster_id=champion,
        champion_title_odds=round(odds.get(champion, {}).get("title", 0.0), 4),
        champion_odds_rank=champion_rank,
        playoff_field_predicted_correctly=overlap,
        mean_title_odds_of_field=round(mean_field_odds, 4),
    )
