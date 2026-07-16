"""Scoring-leverage mispricing — players the national market misprices FOR THIS LEAGUE.

The dynasty trade market (FantasyCalc / DynastyProcess / KTC) prices every player on
*generic* full-PPR. This league scores with yardage and threshold bonuses (see
``scoring/engine._derive_bonuses``) on top of a non-standard base. A player whose
production profile is rewarded *more* by this league's rules than by generic PPR is
systematically **underpriced by the market for us** — and one rewarded less is
overpriced. That gap is invisible to anyone using an off-the-shelf tool, because only
we run the commissioner's exact scoring.

The engine re-scores every skill player's season under both rule sets and ranks the
per-player gap. A uniform league-wide difference (e.g. 6-pt vs 4-pt pass TDs) cancels
out: leverage is measured *relative to the player's own position median*, so what
survives is the player-specific profile edge, not the scoring level.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.market.blend import FC_TO_DYNASTY_SCALE, market_anchor
from sleeper_ffm.model.dynasty import is_age_declining
from sleeper_ffm.model.valuation import SKILL_POSITIONS, compute_season_totals

log = logging.getLogger(__name__)

# Canonical full-PPR — the market's implicit pricing basis. Standard 1-PPR, 4-pt
# passing TDs, 6-pt rushing/receiving TDs, no yardage or threshold bonuses, no
# positional premiums. The gap between a player's points under THIS dict and under
# the league's real settings is exactly the league-specific mispricing signal.
STANDARD_PPR: dict[str, float] = {
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "pass_int": -1.0,
    "pass_2pt": 2.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rush_2pt": 2.0,
    "rec": 1.0,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "rec_2pt": 2.0,
    "fum_lost": -2.0,
}

# Minimum games before a player's leverage ratio is trusted (small samples swing wildly).
_MIN_GAMES: int = 6
# |edge| beyond this (percent) trips a BUY/SELL verdict; inside it is FAIR.
_VERDICT_THRESHOLD: float = 4.0
_CALIBRATION: str = "SCORING-LEVERAGE-vs-STANDARD-PPR"


@dataclass
class MispricingEntry:
    """One player's league-vs-market scoring leverage."""

    player_id: str
    name: str
    position: str
    team: str
    games_played: int
    our_fp: float  # season FP under this league's exact scoring (17-game normalized)
    generic_fp: float  # same season under STANDARD_PPR
    leverage: float  # our_fp / generic_fp
    pos_median_leverage: float
    edge_pct: float  # (leverage / pos_median - 1) * 100; +ve = market underprices for us
    verdict: str  # "BUY" | "SELL" | "FAIR"
    age: float | None = None
    rosterable: bool = True  # False = not currently on an NFL roster (can't be a real target)
    market_value: float | None = None  # dynasty display units, None if unpriced
    value_gap: float | None = None  # market_value * edge_pct/100 (dyn units the market mis-states)
    note: str = ""


@dataclass
class MispricingBoard:
    """Ranked league-specific mispricing surface."""

    season: int
    calibration: str
    min_games: int
    market_source: str
    entries: list[MispricingEntry]  # all qualifying players, best BUY edge first
    buys: list[MispricingEntry]  # top positive-edge players
    sells: list[MispricingEntry]  # top negative-edge players
    warnings: list[str] = field(default_factory=list)


def _verdict(edge_pct: float) -> str:
    if edge_pct >= _VERDICT_THRESHOLD:
        return "BUY"
    if edge_pct <= -_VERDICT_THRESHOLD:
        return "SELL"
    return "FAIR"


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
        log.warning("mispricing: live Sleeper status unavailable (%s)", exc)
        return {}


def build_mispricing(
    seasons: list[int] | None = None,
    min_games: int = _MIN_GAMES,
    market: dict[str, float] | None = None,
    top: int = 15,
) -> MispricingBoard:
    """Rank players by how much this league's scoring mis-values them vs the market.

    Args:
        seasons: Seasons to score (default: latest completed NFL season). Multiple
            seasons are summed per player before the leverage ratio is taken.
        min_games: Minimum games a player must have to appear (noise guard).
        market: ``{sleeper_id: fc_value}`` override; fetched via ``market_anchor`` if None.
        top: Size of the ``buys`` / ``sells`` shortlists.

    Returns:
        A :class:`MispricingBoard`. Degrades to an empty board (with a warning) if
        weekly data is unavailable.
    """
    seasons = seasons or [DEFAULT_VALUE_SEASON]
    warnings: list[str] = []

    live_status = _live_player_status()
    if not live_status:
        warnings.append(
            "Live roster status unavailable; buy/sell not filtered for age or free agency."
        )

    ours = compute_season_totals(seasons=seasons)
    generic = compute_season_totals(seasons=seasons, scoring=STANDARD_PPR)
    if ours.is_empty() or generic.is_empty():
        warnings.append(f"No weekly nflverse data for {seasons}; mispricing board empty.")
        return MispricingBoard(
            season=seasons[-1],
            calibration=_CALIBRATION,
            min_games=min_games,
            market_source="none",
            entries=[],
            buys=[],
            sells=[],
            warnings=warnings,
        )

    # Collapse multi-season to one row per player (sum FP and games across seasons).
    def _collapse(df: pl.DataFrame, fp_alias: str) -> pl.DataFrame:
        return df.group_by("gsis_id").agg(
            [
                pl.col(fp_alias).sum().alias(fp_alias),
                pl.col("games_played").sum().alias("games_played"),
                pl.col("position").last().alias("position"),
                pl.col("name").last().alias("name"),
                pl.col("team").last().alias("team"),
                pl.col("sleeper_id_str").last().alias("sleeper_id_str"),
            ]
        )

    ours_c = _collapse(ours.rename({"season_fp": "our_fp"}), "our_fp")
    gen_c = _collapse(generic.rename({"season_fp": "generic_fp"}), "generic_fp").select(
        ["gsis_id", "generic_fp"]
    )
    joined = ours_c.join(gen_c, on="gsis_id", how="inner")

    if market is None:
        market = market_anchor()
    market_source = "fantasycalc/dynastyprocess" if market else "none"
    if not market:
        warnings.append("Market anchor unavailable; edges shown without market_value/value_gap.")

    # First pass: raw leverage per qualifying player, grouped by position for medians.
    rows: list[dict] = []
    for r in joined.iter_rows(named=True):
        pos = r["position"]
        if pos not in SKILL_POSITIONS:
            continue
        games = int(r["games_played"] or 0)
        our_fp = float(r["our_fp"] or 0.0)
        gen_fp = float(r["generic_fp"] or 0.0)
        if games < min_games or gen_fp <= 0.0 or our_fp <= 0.0:
            continue
        rows.append(
            {
                "sid": r["sleeper_id_str"],
                "name": r["name"] or "?",
                "position": pos,
                "team": r["team"] or "FA",
                "games": games,
                "our_fp": round(our_fp, 1),
                "generic_fp": round(gen_fp, 1),
                "leverage": our_fp / gen_fp,
            }
        )

    pos_medians: dict[str, float] = {}
    for pos in SKILL_POSITIONS:
        levs = [row["leverage"] for row in rows if row["position"] == pos]
        if levs:
            pos_medians[pos] = statistics.median(levs)

    entries: list[MispricingEntry] = []
    for row in rows:
        sid = row["sid"]
        pos = row["position"]
        median = pos_medians.get(pos)
        if not median:
            continue
        edge_pct = round((row["leverage"] / median - 1.0) * 100, 1)
        mkt_val = None
        value_gap = None
        if sid and sid in market and market[sid] > 0:
            mkt_val = round(market[sid] * FC_TO_DYNASTY_SCALE, 1)
            value_gap = round(mkt_val * edge_pct / 100.0, 1)

        status = live_status.get(sid or "", {})
        age = status.get("age")
        rosterable = bool(status.get("team")) if live_status else True

        verdict = _verdict(edge_pct)
        note = (
            f"scores {abs(edge_pct):.0f}% "
            f"{'above' if edge_pct >= 0 else 'below'} the typical {pos} "
            "under our rules vs generic PPR"
        )
        if verdict == "BUY" and is_age_declining(pos, age):
            verdict = "FAIR"
            note = (
                f"scoring edge is real ({edge_pct:+.0f}%) but age {age:.0f} is well past "
                f"{pos} peak — not a real buy-low"
            )
        if not rosterable:
            note += "; not currently on an NFL roster"

        entries.append(
            MispricingEntry(
                player_id=sid or "",
                name=row["name"],
                position=pos,
                team=row["team"],
                games_played=row["games"],
                our_fp=row["our_fp"],
                generic_fp=row["generic_fp"],
                leverage=round(row["leverage"], 3),
                pos_median_leverage=round(median, 3),
                edge_pct=edge_pct,
                age=age,
                rosterable=rosterable,
                verdict=verdict,
                market_value=mkt_val,
                value_gap=value_gap,
                note=note,
            )
        )

    entries.sort(key=lambda e: e.edge_pct, reverse=True)
    # Free agents can't be acquired as a real dynasty target — visible in entries for
    # transparency, but excluded from the actionable buy/sell shortlists.
    buys = [e for e in entries if e.verdict == "BUY" and e.rosterable][:top]
    # Sells ranked most-negative first, priced-in players prioritized (market_value desc).
    sells = sorted(
        [e for e in entries if e.verdict == "SELL" and e.rosterable],
        key=lambda e: (e.edge_pct, -(e.market_value or 0.0)),
    )[:top]

    log.info(
        "mispricing: %d qualifying players, %d buys, %d sells (season=%s)",
        len(entries),
        len(buys),
        len(sells),
        seasons,
    )
    return MispricingBoard(
        season=seasons[-1],
        calibration=_CALIBRATION,
        min_games=min_games,
        market_source=market_source,
        entries=entries,
        buys=buys,
        sells=sells,
        warnings=warnings,
    )


def mispricing_summary(board: MispricingBoard, limit: int = 8) -> str:
    """Render a compact markdown briefing section for the master prompt."""
    if not board.entries:
        return "## League-Specific Mispricing\n_No data available._\n"
    lines = [
        "## League-Specific Mispricing (our scoring vs generic PPR)",
        f"_Calibration: {board.calibration}; season {board.season}; "
        f"min {board.min_games} games; market: {board.market_source}._",
        "",
        "**BUY — market underprices these for our rules:**",
        "| Player | Pos | Team | Edge | Mkt Val | Value Gap |",
        "|--------|-----|------|------|---------|-----------|",
    ]
    for e in board.buys[:limit]:
        mv = f"{e.market_value:.0f}" if e.market_value is not None else "—"
        vg = f"+{e.value_gap:.0f}" if e.value_gap is not None else "—"
        lines.append(f"| {e.name} | {e.position} | {e.team} | +{e.edge_pct:.1f}% | {mv} | {vg} |")
    lines += [
        "",
        "**SELL — market overprices these vs what they do for us:**",
        "| Player | Pos | Team | Edge | Mkt Val | Value Gap |",
        "|--------|-----|------|------|---------|-----------|",
    ]
    for e in board.sells[:limit]:
        mv = f"{e.market_value:.0f}" if e.market_value is not None else "—"
        vg = f"{e.value_gap:.0f}" if e.value_gap is not None else "—"
        lines.append(f"| {e.name} | {e.position} | {e.team} | {e.edge_pct:.1f}% | {mv} | {vg} |")
    return "\n".join(lines) + "\n"
