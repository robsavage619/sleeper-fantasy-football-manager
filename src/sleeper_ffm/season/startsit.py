"""Start/sit optimizer: pick the optimal lineup from Rob's roster.

Solves the 1QB/3RB/3WR/1TE/2FLEX lineup and surfaces changes vs current starters.

Projection sources, best first:

1. **provider** (:mod:`sleeper_ffm.model.projections`) — rotowire's weekly projection,
   re-scored under this league's rules. Measured most accurate of the available options:
   MAE 4.497 vs 4.768 for a season-to-date average over 4,069 out-of-sample player-weeks
   (``evals/backtest.py::run_forecast_backtest``). Roughly a 6% accuracy gain on the
   numbers this optimizer actually sorts by.
2. **nflverse_avg** — last-4 or season-to-date average. The previous top source, kept as
   the fallback because the provider rides an undocumented endpoint.
3. **dynasty_value_proxy**, then a 5.0 default.

Every projection also carries a ``floor``/``ceiling`` from
:mod:`sleeper_ffm.model.forecast`'s simulation, recentred on whichever point estimate was
used. The provider ships one number per player; a lineup decision needs the spread, and a
Monte-Carlo distribution is the only honest way to price the league's threshold bonuses.

One correctness note worth keeping in view: the Vegas environment multiplier
(:func:`~sleeper_ffm.model.vegas.environment_multiplier`) is applied to the *fallback*
sources only. The provider's projection is already game-specific and already prices the
matchup and the total, so scaling it again would double-count the same information.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from sleeper_ffm.config import LATEST_COMPLETED_NFL_SEASON, MY_ROSTER_ID
from sleeper_ffm.model.dynasty import PlayerAsset, value_player
from sleeper_ffm.model.news_feed import availability_factor
from sleeper_ffm.model.valuation import SKILL_POSITIONS, build_player_assets
from sleeper_ffm.model.vegas import environment_multiplier
from sleeper_ffm.nflverse.loader import load_id_map, load_weekly
from sleeper_ffm.scoring.engine import load_scoring, score, stats_from_nflverse
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

_FLEX_POSITIONS = frozenset({"RB", "WR", "TE"})
_POS_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}
_SLOT_LABELS = ["QB", "RB1", "RB2", "RB3", "WR1", "WR2", "WR3", "TE", "FLEX1", "FLEX2"]


@dataclass
class PlayerProjection:
    """A rostered player with a weekly point projection."""

    player_id: str
    name: str
    position: str
    team: str
    projected_pts: float
    confidence: str  # "HIGH" | "MED" | "LOW"
    source: str  # "provider" | "nflverse_avg" | "dynasty_value_proxy" | "default"
    notes: str
    # Simulated p10/p90 around projected_pts. Both 0.0 when no distribution could be
    # built (no box-score history for the player) — check before ranking on them.
    floor: float = 0.0
    ceiling: float = 0.0
    # Live Sleeper injury designation, if any. When it forced a discount, projected_pts
    # already reflects it (see the availability pass in build_startsit).
    injury_status: str | None = None


@dataclass
class StartSitRecommendation:
    """Full start/sit analysis for a given week."""

    week: int
    season: int
    projected_starters: list[PlayerProjection]  # optimal lineup
    current_starters: list[PlayerProjection]  # current lineup
    changes: list[dict]  # [{start, sit, gain}]
    total_projected_pts: float
    current_projected_pts: float
    prompt: str
    data_quality: str
    warnings: list[str]


# ---------------------------------------------------------------------------
# nflverse FP lookup
# ---------------------------------------------------------------------------


def _load_weekly_fp_map(season: int, up_to_week: int) -> dict[str, dict]:
    """Build per-player FP stats from nflverse weekly data, keyed by sleeper_id.

    Args:
        season: NFL season year.
        up_to_week: Only include weeks strictly before this value (completed games).

    Returns:
        Dict mapping sleeper_id -> {games_played, season_avg, last4_avg, last4_games}.
        Empty dict on error or no data.
    """
    try:
        id_map = load_id_map()
        weekly = load_weekly(seasons=[season])
    except Exception as exc:
        log.warning("nflverse data unavailable for season %d: %s", season, exc)
        return {}

    if weekly.is_empty() or up_to_week <= 1:
        return {}

    required = {"season_type", "season", "week", "position", "player_id"}
    if not required.issubset(weekly.columns):
        log.warning("Weekly data missing expected columns")
        return {}

    scored_reg = weekly.filter(
        (pl.col("season_type") == "REG")
        & (pl.col("season") == season)
        & (pl.col("position").is_in(list(SKILL_POSITIONS)))
        & (pl.col("week") < up_to_week)
    )

    if scored_reg.is_empty():
        return {}

    scoring = load_scoring()
    fps = [score(stats_from_nflverse(row), scoring) for row in scored_reg.iter_rows(named=True)]
    scored_reg = scored_reg.with_columns(pl.Series("fp_sffm", fps, dtype=pl.Float64))

    season_df = scored_reg.group_by("player_id").agg(
        [
            pl.col("fp_sffm").len().alias("games_played"),
            pl.col("fp_sffm").mean().alias("season_avg"),
        ]
    )

    last4_df = scored_reg.group_by("player_id").agg(
        [
            pl.col("fp_sffm").sort_by(pl.col("week")).tail(4).mean().alias("last4_avg"),
            pl.col("fp_sffm").sort_by(pl.col("week")).tail(4).len().alias("last4_games"),
        ]
    )

    stats_df = season_df.join(last4_df, on="player_id", how="left")

    # Build gsis_id → sleeper_id mapping (same cast chain as valuation.py)
    id_slim = (
        id_map.select(["gsis_id", "sleeper_id"])
        .filter(pl.col("gsis_id").is_not_null() & pl.col("sleeper_id").is_not_null())
        .with_columns(
            pl.col("sleeper_id").cast(pl.Int64, strict=False).cast(pl.Utf8).alias("sleeper_id_str")
        )
        .filter(pl.col("sleeper_id_str").is_not_null())
        .select(["gsis_id", "sleeper_id_str"])
    )

    joined = stats_df.join(id_slim, left_on="player_id", right_on="gsis_id", how="left")

    result: dict[str, dict] = {}
    for row in joined.iter_rows(named=True):
        sid = row.get("sleeper_id_str")
        if not sid:
            continue
        result[sid] = {
            "games_played": int(row["games_played"] or 0),
            "season_avg": float(row["season_avg"] or 0.0),
            "last4_avg": float(row["last4_avg"] or 0.0),
            "last4_games": int(row["last4_games"] or 0),
        }

    return result


# ---------------------------------------------------------------------------
# Projection per player
# ---------------------------------------------------------------------------


@dataclass
class _WeekEstimate:
    """A provider point estimate and/or a simulated shape for one player-week."""

    points: float | None = None
    floor: float = 0.0
    ceiling: float = 0.0


def _week_estimates(
    season: int,
    week: int,
    skill_ids: list[str],
    sleeper_players: dict[str, dict],
) -> tuple[dict[str, _WeekEstimate], str | None]:
    """Provider projections plus simulated floor/ceiling for the rostered players.

    Both halves are best-effort. The provider rides an undocumented endpoint and the
    simulation needs cached nflverse history; either can be missing, and the caller
    degrades to the nflverse-average path rather than failing.

    Args:
        season: NFL season being projected.
        week: NFL week being projected.
        skill_ids: Sleeper player_ids to estimate.
        sleeper_players: Full Sleeper player dump, for position lookup.

    Returns:
        ``(estimates_by_player_id, warning)`` — ``warning`` is a human-readable note when
        the provider feed could not be reached, else None.
    """
    from sleeper_ffm.model.forecast import PositionalPriors, build_priors, forecast_player
    from sleeper_ffm.model.projections import ProjectionsUnavailableError, week_projections
    from sleeper_ffm.sleeper.graphql import SleeperGraphQLError

    out: dict[str, _WeekEstimate] = {}
    warning: str | None = None

    try:
        provider = week_projections(str(season), week)
    except (ProjectionsUnavailableError, SleeperGraphQLError, OSError) as exc:
        log.warning("startsit: provider projections unavailable (%s)", exc)
        provider = {}
        warning = "Provider projections unavailable; fell back to nflverse averages."

    for pid in skill_ids:
        if (p := provider.get(pid)) is not None:
            out[pid] = _WeekEstimate(points=p.league_points)

    # Simulated shape, from this player's own box scores. Only the rostered players are
    # simulated (tens, not thousands), so the Monte-Carlo cost here is trivial.
    #
    # Early in a season — and all off-season — the season being projected has no box
    # scores at all, which is precisely when a floor/ceiling is most wanted. Fall back to
    # the last completed season rather than returning no distribution.
    try:
        history, meta = _player_history(season, week)
        priors = build_priors(season) if history else PositionalPriors(season=season)
        if not history or not priors.rates:
            fallback = LATEST_COMPLETED_NFL_SEASON
            if fallback != season:
                log.info(
                    "startsit: no %s box scores yet; simulating spread off %s",
                    season,
                    fallback,
                )
                history, meta = _player_history(fallback, week=99)
                priors = build_priors(fallback)
    except (FileNotFoundError, OSError) as exc:
        log.warning("startsit: no history for simulated floor/ceiling (%s)", exc)
        return out, warning
    if not history or not priors.rates:
        return out, warning

    scoring = load_scoring()
    id_map = load_id_map()
    gsis_by_sleeper: dict[str, str] = {}
    if {"sleeper_id", "gsis_id"} <= set(id_map.columns):
        for r in id_map.select(["sleeper_id", "gsis_id"]).iter_rows(named=True):
            if r.get("sleeper_id") and r.get("gsis_id"):
                gsis_by_sleeper[str(r["sleeper_id"]).split(".")[0]] = str(r["gsis_id"])

    for pid in skill_ids:
        gsis = gsis_by_sleeper.get(pid)
        if not gsis:
            continue
        rows = history.get(gsis)
        if not rows:
            continue
        position = sleeper_players.get(pid, {}).get("position") or ""
        if position not in SKILL_POSITIONS:
            continue
        forecast = forecast_player(
            rows=rows,
            player_id=pid,
            name="",
            position=position,
            team=str(meta.get(gsis, {}).get("recent_team") or ""),
            opponent="",
            season=season,
            week=week,
            priors=priors,
            scoring=scoring,
        )
        estimate = out.get(pid, _WeekEstimate())
        # Recentre the simulated shape on the provider's mean when there is one; the
        # provider forecasts the level better, the simulation supplies the spread.
        shape = forecast.points
        if estimate.points is not None:
            shape = shape.recentered_to(estimate.points)
        out[pid] = _WeekEstimate(points=estimate.points, floor=shape.floor, ceiling=shape.ceiling)

    return out, warning


def _player_history(season: int, week: int) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Per-player weekly rows before ``week``, keyed by gsis_id, oldest first."""
    weekly = load_weekly([season])
    if weekly.is_empty():
        return {}, {}
    weekly = weekly.filter((pl.col("season_type") == "REG") & (pl.col("week") < week))
    history: dict[str, list[dict]] = {}
    meta: dict[str, dict] = {}
    for row in weekly.sort("week").iter_rows(named=True):
        pid = str(row["player_id"])
        history.setdefault(pid, []).append(row)
        meta[pid] = row
    return history, meta


def _project_player(
    pid: str,
    sleeper_players: dict[str, dict],
    weekly_fp_map: dict[str, dict],
    dynasty_by_id: dict[str, PlayerAsset],
    season: int,
    week: int,
    estimates: dict[str, _WeekEstimate] | None = None,
) -> PlayerProjection:
    """Build a single player's weekly projection.

    Priority: provider → nflverse_avg → dynasty_value_proxy → default 5.0. The three
    fallback paths are scaled by the team's Vegas-implied scoring environment
    (:func:`environment_multiplier`); the provider path is not, because a weekly
    projection already prices the matchup and the game total.

    Args:
        pid: Sleeper player_id.
        sleeper_players: Full Sleeper player dump.
        weekly_fp_map: Per-player FP stats keyed by sleeper_id.
        dynasty_by_id: PlayerAsset lookup from build_player_assets.
        season: NFL season year, for the Vegas environment lookup.
        week: NFL week being projected, for the Vegas environment lookup.
        estimates: Provider points and simulated floor/ceiling from
            :func:`_week_estimates`. None disables both.

    Returns:
        PlayerProjection with best available estimate.
    """
    meta = sleeper_players.get(pid, {})
    name = meta.get("full_name") or f"Player {pid}"
    position = meta.get("position") or "?"
    team = meta.get("team") or "FA"
    env_mult = environment_multiplier(season, week, team)
    env_note = f"; vegas env x{env_mult:.2f}" if env_mult != 1.0 else ""
    estimate = (estimates or {}).get(pid, _WeekEstimate())
    spread_note = (
        f"; sim floor {estimate.floor:.1f}/ceil {estimate.ceiling:.1f}"
        if estimate.ceiling > 0
        else ""
    )

    if estimate.points is not None:
        return PlayerProjection(
            player_id=pid,
            name=name,
            position=position,
            team=team,
            projected_pts=max(0.0, round(estimate.points, 1)),
            confidence="HIGH",
            source="provider",
            # No env multiplier here by design: the provider's number is already
            # game-specific, so applying it again double-counts the matchup.
            notes=f"provider proj (league-scored): {estimate.points:.1f}{spread_note}",
            floor=estimate.floor,
            ceiling=estimate.ceiling,
        )

    if pid in weekly_fp_map:
        fp_data = weekly_fp_map[pid]
        games = fp_data["games_played"]
        s_avg = round(fp_data["season_avg"], 1)
        l4_avg = round(fp_data["last4_avg"], 1)
        l4_games = fp_data["last4_games"]

        if l4_games >= 4:
            pts = round(l4_avg * env_mult, 1)
            confidence = "HIGH"
            notes = f"4-wk avg: {l4_avg:.1f}, season avg: {s_avg:.1f}{env_note}"
        else:
            pts = round(s_avg * env_mult, 1)
            confidence = "MED"
            notes = f"season avg ({games} games): {s_avg:.1f}{env_note}"

        return PlayerProjection(
            player_id=pid,
            name=name,
            position=position,
            team=team,
            projected_pts=max(0.0, pts),
            confidence=confidence,
            source="nflverse_avg",
            notes=notes + spread_note,
            floor=estimate.floor,
            ceiling=estimate.ceiling,
        )

    if pid in dynasty_by_id:
        asset = dynasty_by_id[pid]
        dynasty_val = value_player(asset)
        pts = round((dynasty_val / 10.0) * env_mult, 1)
        return PlayerProjection(
            player_id=pid,
            name=name,
            position=position,
            team=team,
            projected_pts=max(0.0, pts),
            confidence="LOW",
            source="dynasty_value_proxy",
            notes=f"dynasty value: {dynasty_val:.1f} (no weekly data){env_note}",
            floor=estimate.floor,
            ceiling=estimate.ceiling,
        )

    return PlayerProjection(
        player_id=pid,
        name=name,
        position=position,
        team=team,
        projected_pts=round(5.0 * env_mult, 1),
        confidence="LOW",
        source="default",
        notes=f"no data available{env_note}",
    )


# ---------------------------------------------------------------------------
# Lineup optimizer
# ---------------------------------------------------------------------------


def _solve_lineup(projections: list[PlayerProjection]) -> list[PlayerProjection]:
    """Pick the optimal lineup: 1 QB, 3 RB, 3 WR, 1 TE, 2 FLEX (RB/WR/TE).

    Fills positional slots first (most pts), then fills FLEX with best remaining
    skill-position players. Handles thin rosters gracefully.

    Args:
        projections: All roster players with projections.

    Returns:
        Ordered list: [QB, RB1, RB2, RB3, WR1, WR2, WR3, TE, FLEX1, FLEX2].
        May be shorter than 10 if not enough eligible players.
    """
    by_pos: dict[str, list[PlayerProjection]] = {}
    for p in projections:
        by_pos.setdefault(p.position, []).append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: x.projected_pts, reverse=True)

    used: set[str] = set()
    starters: list[PlayerProjection] = []

    for pos, count in [("QB", 1), ("RB", 3), ("WR", 3), ("TE", 1)]:
        available = [p for p in by_pos.get(pos, []) if p.player_id not in used]
        for p in available[:count]:
            starters.append(p)
            used.add(p.player_id)

    # FLEX: best remaining RB/WR/TE
    flex_pool = sorted(
        [p for p in projections if p.position in _FLEX_POSITIONS and p.player_id not in used],
        key=lambda x: x.projected_pts,
        reverse=True,
    )
    for p in flex_pool[:2]:
        starters.append(p)
        used.add(p.player_id)

    return starters


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def _apply_availability(
    projections: list[PlayerProjection],
    sleeper_players: dict[str, dict],
    warnings: list[str],
) -> None:
    """Discount each projection by the player's live Sleeper injury status, in place.

    The single place availability enters the live lineup solve. Reuses the canonical
    :func:`sleeper_ffm.model.news_feed.availability_factor` so start/sit shades identically
    to the intel feed and briefing. Records the injury status on each projection and appends
    a one-line warning naming the players that were zeroed or faded, so a discount never
    happens silently.

    Args:
        projections: The roster's projections (mutated: ``projected_pts``, ``notes``,
            ``injury_status``).
        sleeper_players: The live Sleeper player dump (source of ``injury_status``).
        warnings: The recommendation's warning list, appended to when players are discounted.
    """
    hit: list[str] = []
    for proj in projections:
        status = sleeper_players.get(proj.player_id, {}).get("injury_status")
        if not status:
            continue
        proj.injury_status = status
        factor = availability_factor(status)
        # Measured 2026-wk1: the rotowire provider already prices injuries — Out-class
        # players project ~0.3 and Questionables are already faded — so re-applying the
        # Questionable x0.8 on the provider path would double-count. Only the hard-zero
        # is kept there, as a safety net for the occasional stale feed that still lists an
        # Out player at a real number (seen up to 6.5). The injury-BLIND fallback sources
        # (nflverse avg / proxy / default) get the full discount.
        if proj.source == "provider" and factor > 0.0:
            continue
        if factor < 1.0:
            proj.projected_pts = round(proj.projected_pts * factor, 1)
            verb = "OUT->0" if factor == 0.0 else f"x{factor:g}"
            proj.notes += f"; injury {status} ({verb})"
            hit.append(f"{proj.name} ({status})")
    if hit:
        warnings.append(f"Injury-discounted {len(hit)} player(s): {', '.join(hit)}.")


# ---------------------------------------------------------------------------
# Changes computation
# ---------------------------------------------------------------------------


def _compute_changes(
    optimal: list[PlayerProjection],
    current: list[PlayerProjection],
) -> list[dict]:
    """Compute start/sit changes from current to optimal lineup.

    Args:
        optimal: Optimal lineup from _solve_lineup.
        current: Current Sleeper lineup.

    Returns:
        List of {start, sit, gain} dicts, sorted by gain descending.
    """
    optimal_ids = {p.player_id for p in optimal}
    current_ids = {p.player_id for p in current}

    starts = sorted(
        [p for p in optimal if p.player_id not in current_ids],
        key=lambda p: p.projected_pts,
        reverse=True,
    )
    sits = sorted(
        [p for p in current if p.player_id not in optimal_ids],
        key=lambda p: p.projected_pts,
    )

    changes: list[dict] = []
    used_sits: set[str] = set()

    def _pair(start: PlayerProjection, sit: PlayerProjection) -> None:
        used_sits.add(sit.player_id)
        changes.append(
            {
                "start": start.player_id,
                "sit": sit.player_id,
                "gain": round(start.projected_pts - sit.projected_pts, 1),
            }
        )

    # Same-position swaps first (a QB only ever replaces a QB).
    for start in starts:
        same_pos = [
            s for s in sits if s.player_id not in used_sits and s.position == start.position
        ]
        if same_pos:
            _pair(start, min(same_pos, key=lambda p: p.projected_pts))

    # Remaining swaps must be FLEX-legal (RB/WR/TE interchange only) — never
    # pair a QB against a non-QB.
    paired_starts = {c["start"] for c in changes}
    for start in starts:
        if start.player_id in paired_starts or start.position not in _FLEX_POSITIONS:
            continue
        flex_sits = [
            s for s in sits if s.player_id not in used_sits and s.position in _FLEX_POSITIONS
        ]
        if flex_sits:
            _pair(start, min(flex_sits, key=lambda p: p.projected_pts))

    return sorted(changes, key=lambda x: x["gain"], reverse=True)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(
    week: int,
    season: int,
    all_projections: list[PlayerProjection],
    optimal: list[PlayerProjection],
    current: list[PlayerProjection],
    changes: list[dict],
    proj_by_id: dict[str, PlayerProjection],
) -> str:
    """Build a structured Claude Code prompt for start/sit reasoning.

    Args:
        week: NFL week being optimized.
        season: NFL season year.
        all_projections: All roster players (for full roster table).
        optimal: Optimal lineup from optimizer.
        current: Current Sleeper starters.
        changes: Computed changes list.
        proj_by_id: Player lookup for name resolution in changes.

    Returns:
        Formatted prompt string ready to paste into Claude Code.
    """
    # Sort all projections: position order then pts desc
    sorted_proj = sorted(
        all_projections,
        key=lambda p: (_POS_ORDER.get(p.position, 9), -p.projected_pts),
    )

    # Roster projections table
    roster_rows = [
        "| Player | Pos | Team | Proj | Source | Notes |",
        "|--------|-----|------|------|--------|-------|",
    ]
    for p in sorted_proj:
        roster_rows.append(
            f"| {p.name} | {p.position} | {p.team} | {p.projected_pts:.1f}"
            f" | {p.source} | {p.notes} |"
        )

    # Optimal lineup table
    opt_rows = ["| Slot | Player | Pos | Projected |", "|------|--------|-----|-----------|"]
    for slot, p in zip(_SLOT_LABELS, optimal, strict=False):
        opt_rows.append(f"| {slot} | {p.name} | {p.position} | {p.projected_pts:.1f} |")

    # Current lineup table
    cur_rows = ["| Slot | Player | Pos | Projected |", "|------|--------|-----|-----------|"]
    for slot, p in zip(_SLOT_LABELS, current, strict=False):
        cur_rows.append(f"| {slot} | {p.name} | {p.position} | {p.projected_pts:.1f} |")

    # Changes section
    if changes:
        change_lines = []
        for c in changes:
            start_p = proj_by_id.get(c["start"])
            sit_p = proj_by_id.get(c["sit"])
            start_name = start_p.name if start_p else c["start"]
            sit_name = sit_p.name if sit_p else c["sit"]
            change_lines.append(f"- START {start_name} over {sit_name} (+{c['gain']:.1f} pts)")
        changes_text = "\n".join(change_lines)
    else:
        changes_text = "No changes recommended — current lineup is optimal."

    return f"""## START/SIT OPTIMIZER — WEEK {week} {season}

### MY ROSTER PROJECTIONS
{chr(10).join(roster_rows)}

### OPTIMAL LINEUP (model)
{chr(10).join(opt_rows)}

### CURRENT STARTERS
{chr(10).join(cur_rows)}

### RECOMMENDED CHANGES
{changes_text}

### REQUEST
Evaluate these start/sit recommendations. Consider:
- Injury risk, weather, game script
- Matchup quality (opponent defensive rank by position if you have that context)
- Boom/bust variance vs. safe floor
- Any players NOT in nflverse data that I should know about

Respond with: KEEP or CHANGE for each recommendation, plus brief reasoning.
Post your finding via: `sffm finding startsit --body '<json>'`
where JSON has keys: `recommendations` (list of {{player_id, decision, reason}}) and `summary`.
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_startsit(week: int, season: int) -> StartSitRecommendation:
    """Build a start/sit recommendation for the given week.

    Loads Rob's roster from Sleeper, projects weekly points for each skill-position
    player, solves the optimal lineup, and compares to current starters.

    Args:
        week: NFL week to optimize for (1-18). Used as the upper bound for
            completed-game lookback (last N weeks before this week).
        season: NFL season year (e.g. 2025).

    Returns:
        StartSitRecommendation with optimal lineup, current lineup, changes, and prompt.
    """
    with SleeperClient() as c:
        rosters = c.rosters()
        sleeper_players = c.players()

    my_roster = next((r for r in rosters if r.roster_id == MY_ROSTER_ID), None)
    if my_roster is None:
        raise ValueError(f"Roster {MY_ROSTER_ID} not found in league")

    # All player IDs on my roster (including taxi/reserve)
    all_ids: set[str] = set(my_roster.players or [])
    all_ids.update(my_roster.taxi or [])
    all_ids.update(my_roster.reserve or [])

    skill_ids = [
        pid for pid in all_ids if sleeper_players.get(pid, {}).get("position") in SKILL_POSITIONS
    ]
    log.info(
        "startsit: %d skill-position players on roster for week %d %d",
        len(skill_ids),
        week,
        season,
    )

    # nflverse weekly FP lookup
    weekly_fp_map = _load_weekly_fp_map(season, week)
    log.info("startsit: nflverse data for %d players", len(weekly_fp_map))
    warnings: list[str] = []
    if not weekly_fp_map:
        warnings.append(
            f"No weekly nflverse projection data available for {season} before week {week}."
        )

    # Dynasty assets for proxy fallback
    try:
        dynasty_list = build_player_assets(seasons=[season], sleeper_players=sleeper_players)
        dynasty_by_id = {p.player_id: p for p in dynasty_list}
    except Exception as exc:
        log.warning("Dynasty assets unavailable: %s", exc)
        warnings.append(
            "Dynasty value fallback unavailable; some players may use default projections."
        )
        dynasty_by_id = {}

    # Provider projections + simulated floor/ceiling (both best-effort).
    estimates, provider_warning = _week_estimates(season, week, skill_ids, sleeper_players)
    if provider_warning:
        warnings.append(provider_warning)

    # Build projections for all roster players
    projections = [
        _project_player(pid, sleeper_players, weekly_fp_map, dynasty_by_id, season, week, estimates)
        for pid in skill_ids
    ]

    # Availability pass — the arena's biggest, validated lever, ported live. None of the
    # four projection sources consults injury status, so an Out/IR player would rank like a
    # healthy one; here every projection is discounted by his live Sleeper designation
    # (Out/IR/Doubtful -> 0, Questionable -> 0.8) before the lineup is solved. Applied
    # uniformly after the fact so it covers provider/nflverse/proxy/default alike.
    _apply_availability(projections, sleeper_players, warnings)

    provider_count = sum(1 for p in projections if p.source == "provider")
    log.info("startsit: %d/%d projections from the provider", provider_count, len(projections))
    default_count = sum(1 for p in projections if p.source == "default")
    proxy_count = sum(1 for p in projections if p.source == "dynasty_value_proxy")
    if default_count:
        warnings.append(f"{default_count} player projection(s) used the 5.0 point default.")
    if proxy_count:
        warnings.append(f"{proxy_count} player projection(s) used dynasty-value proxy fallback.")
    data_quality = "FULL" if not warnings else "DEGRADED"

    # Optimal lineup
    optimal = _solve_lineup(projections)

    # Current starters from Sleeper (skill positions only)
    proj_by_id = {p.player_id: p for p in projections}
    current_starters = [proj_by_id[pid] for pid in (my_roster.starters or []) if pid in proj_by_id]

    changes = _compute_changes(optimal, current_starters)

    total_proj = round(sum(p.projected_pts for p in optimal), 1)
    current_proj = round(sum(p.projected_pts for p in current_starters), 1)

    prompt = _build_prompt(
        week, season, projections, optimal, current_starters, changes, proj_by_id
    )

    return StartSitRecommendation(
        week=week,
        season=season,
        projected_starters=optimal,
        current_starters=current_starters,
        changes=changes,
        total_projected_pts=total_proj,
        current_projected_pts=current_proj,
        prompt=prompt,
        data_quality=data_quality,
        warnings=warnings,
    )
