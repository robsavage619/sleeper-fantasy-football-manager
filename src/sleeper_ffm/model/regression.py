"""Regression flags — buy-low and sell-high candidates from unsustainable scoring.

Fantasy points are noisy; touchdowns are the noisiest part. A player scoring far more
TDs than expected is riding variance that tends to correct — a sell-high. One scoring
far fewer is getting unlucky on the same real usage — a buy-low the market hasn't
caught up to.

Two expected-TD models, picked automatically by data availability (``RegressionBoard.basis``):
    - **redzone-opportunity** (preferred): each target/carry priced by the observed
      touchdown probability of its yard-line bin (``sabermetrics.redzone_td_rates``, from
      play-by-play). Backtested out-of-sample by ``sleeper_ffm.evals.backtest`` (fit on
      one season, scored on the next): expected-TD MAE dropped ~25% vs the yardage
      baseline (24.6% fitting on 2024 and evaluating on 2025, n=235) — where a look came
      from predicts touchdowns much better than raw yardage volume does. The binary
      red-zone flag this replaced managed 19.3% on the same split. Reproduce with the
      ``regression.redzone_beats_yardage_oos`` tier-1 eval scenario.
    - **yardage** (fallback): actual TDs minus total yardage x position TD-per-yard
      rate. Used when play-by-play isn't cached for the season.

Both feed the same ``td_oe`` (actual - expected) and verdict logic — it complements the
descriptive TD-dependence figure already in :mod:`sleeper_ffm.model.sabermetrics` by
turning it into a directional, actionable call.

This is a lean, not a projection: usage can be real and sticky, and elite players do
sustain high TD rates. The flag says "the points ran ahead of / behind the process,"
which is a reason to look, not a verdict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.nflverse.loader import load_id_map, load_weekly

log = logging.getLogger(__name__)

# Minimum yardage volume before td_oe is meaningful (filters low-sample noise).
_MIN_YARDS: int = 250
# |td_oe| beyond this trips a directional flag.
_FLAG_TDS: float = 2.0

_YARD_COLS = ("rushing_yards", "receiving_yards")
_TD_COLS = ("rushing_tds", "receiving_tds")


@dataclass
class RegressionFlag:
    """One player's TD-over-expected signal."""

    player_id: str
    name: str
    position: str
    team: str
    total_yards: float
    total_tds: float
    expected_tds: float  # total_yards * position TD-per-yard baseline
    td_oe: float  # actual - expected; +ve = lucky (sell), -ve = unlucky (buy)
    verdict: str  # "SELL-HIGH" | "BUY-LOW" | "AGE-DECLINE" | "NEUTRAL"
    age: float | None = None
    rosterable: bool = True  # False = not currently on an NFL roster (can't be a real target)
    note: str = ""


@dataclass
class RegressionBoard:
    """Ranked regression candidates."""

    season: int
    baselines: dict  # position -> rate table (shape depends on `basis`)
    sell_high: list[RegressionFlag]  # most over-expected first
    buy_low: list[RegressionFlag]  # most under-expected first
    basis: str = "yardage"  # "redzone-opportunity" | "yardage" (PBP unavailable)
    warnings: list[str] = field(default_factory=list)


def _flag_from_expected(r: dict, expected: float) -> RegressionFlag:
    """Build one player's flag from any expected-TD basis (yardage or red-zone-opportunity)."""
    from sleeper_ffm.model.dynasty import is_age_declining

    pos = r["position"]
    age = r.get("age")
    td_oe = r["total_tds"] - expected
    if td_oe >= _FLAG_TDS:
        verdict = "SELL-HIGH"
        note = f"+{td_oe:.1f} TDs over expected — TD rate likely regresses down"
    elif td_oe <= -_FLAG_TDS:
        if is_age_declining(pos, age):
            verdict = "AGE-DECLINE"
            note = (
                f"{td_oe:.1f} TDs below expected, but age {age:.0f} is well past "
                f"{pos} peak — declining, not unlucky"
            )
        else:
            verdict = "BUY-LOW"
            note = f"{td_oe:.1f} TDs below expected — same usage, unlucky finish"
    else:
        verdict = "NEUTRAL"
        note = "TD rate roughly matches yardage volume"
    return RegressionFlag(
        player_id=r["sid"],
        name=r["name"],
        position=pos,
        team=r["team"],
        total_yards=round(r["total_yards"], 1),
        total_tds=round(r["total_tds"], 1),
        expected_tds=round(expected, 1),
        td_oe=round(td_oe, 1),
        verdict=verdict,
        age=age,
        rosterable=r.get("rosterable", True),
        note=note,
    )


def compute_td_regression(
    rows: list[dict],
    min_yards: int = _MIN_YARDS,
) -> tuple[dict[str, float], list[RegressionFlag]]:
    """Compute position TD-per-yard baselines and per-player td_oe. Pure.

    Args:
        rows: ``[{sid, name, position, team, total_yards, total_tds, age?, rosterable?}, ...]``.
            ``age``/``rosterable`` are optional; when omitted no player is ever flagged
            AGE-DECLINE (matches pre-existing callers/tests).
        min_yards: Minimum yardage before a player is flagged.

    Returns:
        ``(baselines, flags)`` — ``{position: td_per_yard}`` and one flag per row.
    """
    baselines: dict[str, float] = {}
    for pos in SKILL_POSITIONS:
        pos_rows = [r for r in rows if r["position"] == pos]
        yards = sum(r["total_yards"] for r in pos_rows)
        tds = sum(r["total_tds"] for r in pos_rows)
        if yards > 0:
            baselines[pos] = tds / yards

    flags: list[RegressionFlag] = []
    for r in rows:
        rate = baselines.get(r["position"])
        if rate is None or r["total_yards"] < min_yards:
            continue
        flags.append(_flag_from_expected(r, r["total_yards"] * rate))
    return baselines, flags


def compute_redzone_td_regression(
    rows: list[dict],
    play_values: pl.DataFrame,
    position_by_player: dict[str, str],
    min_yards: int = _MIN_YARDS,
) -> tuple[dict[str, dict[str, float]], list[RegressionFlag]]:
    """Opportunity-based expected TDs — the calibrated upgrade over yardage.

    Where :func:`compute_td_regression` expects TDs from total yardage at a flat
    position rate, this prices each target/carry by the observed touchdown probability
    of the yard-line bin it came from
    (:func:`sleeper_ffm.model.sabermetrics.redzone_td_rates`). Backtested out-of-sample
    by :mod:`sleeper_ffm.evals.backtest` (fit on one season, scored on the next):
    expected-TD MAE dropped ~25% vs the yardage baseline (24.6% fitting on 2024 and
    evaluating on 2025) — where a look came from predicts touchdowns much better than
    how many yards a player racked up.

    Args:
        rows: Same per-player rows as :func:`compute_td_regression`, plus a
            ``"gsis_id"`` key — play-by-play is keyed by gsis_id, not the sleeper_id
            used in ``sid``/``RegressionFlag.player_id``.
        play_values: Output of ``sabermetrics.pbp_play_value``.
        position_by_player: ``gsis_id -> position`` lookup (from ``load_id_map``).
        min_yards: Minimum yardage before a player is flagged (same noise guard as v1).

    Returns:
        ``(rates, flags)`` — the per-yard-line-bin TD-rate table by position, and one
        flag per qualifying row.
    """
    from sleeper_ffm.model.sabermetrics import player_redzone_opportunities, redzone_td_rates

    rates = redzone_td_rates(play_values, position_by_player)

    flags: list[RegressionFlag] = []
    for r in rows:
        pos = r["position"]
        pos_rates = rates.get(pos)
        if pos_rates is None or r["total_yards"] < min_yards or not r.get("gsis_id"):
            continue
        opps = player_redzone_opportunities(play_values, r["gsis_id"])
        expected = sum(opps.get(k, 0.0) * pos_rates.get(k, 0.0) for k in opps)
        flags.append(_flag_from_expected(r, expected))
    return rates, flags


def _aggregate_rows(season: int, live_status: dict[str, dict] | None = None) -> list[dict]:
    """Aggregate one season's weekly stats to per-player yardage/TD totals.

    Args:
        season: NFL season year.
        live_status: Optional ``{sleeper_id: {"age", "team"}}`` from the live Sleeper
            player dump, used to attach current age/roster status to each row.
    """
    live_status = live_status or {}
    weekly = load_weekly(seasons=[season])
    if weekly.is_empty() or "season_type" not in weekly.columns:
        return []
    reg = weekly.filter(
        (pl.col("season_type") == "REG") & (pl.col("position").is_in(list(SKILL_POSITIONS)))
    )
    if reg.is_empty():
        return []

    yard_cols = [c for c in _YARD_COLS if c in reg.columns]
    td_cols = [c for c in _TD_COLS if c in reg.columns]
    if not yard_cols or not td_cols:
        return []

    agg = reg.group_by("player_id").agg(
        [
            *(pl.col(c).sum().alias(c) for c in yard_cols),
            *(pl.col(c).sum().alias(c) for c in td_cols),
            pl.col("position").last().alias("position"),
            pl.col("player_display_name").last().alias("name"),
            pl.col("recent_team").last().alias("team"),
        ]
    )

    id_map = load_id_map()
    id_slim = (
        id_map.select(["gsis_id", "sleeper_id"])
        .filter(pl.col("gsis_id").is_not_null() & pl.col("sleeper_id").is_not_null())
        .with_columns(
            pl.col("sleeper_id").cast(pl.Int64, strict=False).cast(pl.Utf8).alias("sleeper_id_str")
        )
        .filter(pl.col("sleeper_id_str").is_not_null())
        .select(["gsis_id", "sleeper_id_str"])
    )
    agg = agg.join(id_slim, left_on="player_id", right_on="gsis_id", how="left")

    rows: list[dict] = []
    for r in agg.iter_rows(named=True):
        total_yards = sum(float(r.get(c) or 0.0) for c in yard_cols)
        total_tds = sum(float(r.get(c) or 0.0) for c in td_cols)
        sid = r.get("sleeper_id_str") or ""
        status = live_status.get(sid, {})
        rows.append(
            {
                "sid": sid,
                "gsis_id": r.get("player_id") or "",
                "name": r.get("name") or "?",
                "position": r["position"],
                "team": r.get("team") or "FA",
                "total_yards": total_yards,
                "total_tds": total_tds,
                "age": status.get("age"),
                "rosterable": bool(status.get("team")) if live_status else True,
            }
        )
    return rows


def _live_player_status() -> dict[str, dict]:
    """Fetch ``{sleeper_id: {"age", "team"}}`` from the live Sleeper player dump."""
    try:
        from sleeper_ffm.sleeper.client import SleeperClient

        with SleeperClient() as client:
            return {
                sid: {"age": p.get("age"), "team": p.get("team")}
                for sid, p in client.players().items()
            }
    except Exception as exc:
        log.warning("regression: live Sleeper status unavailable (%s)", exc)
        return {}


def _redzone_regression_inputs(
    season: int,
) -> tuple[pl.DataFrame, dict[str, str]] | None:
    """Load PBP + position lookup for the yard-line TD model, or None if unavailable."""
    try:
        from sleeper_ffm.model.sabermetrics import pbp_play_value
        from sleeper_ffm.nflverse.loader import load_pbp
        from sleeper_ffm.scoring.engine import load_scoring

        pbp = load_pbp(seasons=[season])
        if pbp.is_empty():
            return None
        play_values = pbp_play_value(pbp, load_scoring())
        if play_values.is_empty():
            return None

        position_by_player = dict(
            load_id_map()
            .filter(pl.col("gsis_id").str.starts_with("00-"))
            .select(["gsis_id", "position"])
            .drop_nulls()
            .iter_rows()
        )
        return play_values, position_by_player
    except Exception as exc:
        log.debug("regression: red-zone PBP inputs unavailable (%s)", exc)
        return None


def build_regression(season: int | None = None, top: int = 15) -> RegressionBoard:
    """Build the regression board for a season.

    Uses the red-zone-opportunity TD model (backtested more accurate than yardage)
    when play-by-play is available for the season, falling back to the yardage
    baseline otherwise — see ``RegressionBoard.basis``.

    Returns:
        A :class:`RegressionBoard` with sell-high and buy-low shortlists. Players not
        currently on an NFL roster, or far enough past positional peak age that a
        low TD rate reads as decline rather than bad luck, are excluded from
        ``buy_low``/``sell_high`` (visible in the raw flags only).
    """
    season = season or DEFAULT_VALUE_SEASON
    warnings: list[str] = []
    live_status = _live_player_status()
    if not live_status:
        warnings.append("Live roster status unavailable; buy-low not filtered for age/free agency.")
    rows = _aggregate_rows(season, live_status)
    if not rows:
        warnings.append(f"No weekly stats available for {season}; regression board empty.")
        return RegressionBoard(
            season=season, baselines={}, sell_high=[], buy_low=[], warnings=warnings
        )

    redzone_inputs = _redzone_regression_inputs(season)
    if redzone_inputs is not None:
        play_values, position_by_player = redzone_inputs
        baselines, flags = compute_redzone_td_regression(rows, play_values, position_by_player)
        basis = "redzone-opportunity"
    else:
        baselines, flags = compute_td_regression(rows)
        basis = "yardage"
        warnings.append(f"Play-by-play unavailable for {season}; using the yardage TD baseline.")

    sell = sorted(
        [f for f in flags if f.verdict == "SELL-HIGH" and f.rosterable],
        key=lambda f: f.td_oe,
        reverse=True,
    )[:top]
    buy = sorted(
        [f for f in flags if f.verdict == "BUY-LOW" and f.rosterable], key=lambda f: f.td_oe
    )[:top]
    return RegressionBoard(
        season=season,
        baselines=baselines,
        sell_high=sell,
        buy_low=buy,
        basis=basis,
        warnings=warnings,
    )
