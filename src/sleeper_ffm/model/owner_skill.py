"""True Owner Skill Index — all-play, lineup efficiency, and roster value."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.config import LEAGUE_ID

log = logging.getLogger(__name__)


@dataclass
class OwnerSkillIndex:
    """Composite skill index for a single dynasty GM."""

    roster_id: int
    user_id: str
    display_name: str | None
    # All-play: how many weekly matchups would they win vs every other team
    allplay_wins: int           # total virtual wins across all weeks
    allplay_games: int          # total virtual games (weeks * (n_teams-1))
    allplay_pct: float          # allplay_wins / allplay_games, 0-1
    # Lineup efficiency: actual pts / optimal pts from their roster
    lineup_efficiency: float    # 0-1, e.g. 0.87 = started 87% of optimal lineup
    # Roster value relative to league average
    roster_value: int           # total dynasty value of their roster
    roster_value_pct: float     # their value / average value, e.g. 1.15 = 15% above avg
    # Composite skill score 0-100
    skill_score: float
    skill_tier: str             # 'ELITE' / 'STRONG' / 'AVERAGE' / 'WEAK'
    summary: str                # one human-readable line


def _tier(score: float) -> str:
    if score >= 75:
        return "ELITE"
    if score >= 55:
        return "STRONG"
    if score >= 35:
        return "AVERAGE"
    return "WEAK"


def build_owner_skill() -> list[OwnerSkillIndex]:
    """Compute the True Owner Skill Index for every team in the league.

    Fetches rosters, users, and 2024 matchup data from the Sleeper API, then
    computes all-play record, lineup efficiency, and roster dynasty value.

    Returns:
        List of OwnerSkillIndex sorted by skill_score descending.
    """
    from sleeper_ffm.model.valuation import build_player_assets
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        rosters = client.rosters(LEAGUE_ID)
        users = client.users(LEAGUE_ID)

        # Collect matchup data for weeks 1-17; stop on first exception (off-season)
        weekly_matchups: list[list[dict]] = []
        for week in range(1, 18):
            try:
                week_data = client.matchups(week, LEAGUE_ID)
                if not week_data:
                    break
                weekly_matchups.append(week_data)
            except Exception:
                log.debug("matchup fetch stopped at week %d (off-season or 404)", week)
                break

    log.info("fetched %d weeks of matchup data", len(weekly_matchups))

    # Build user lookup by user_id
    user_by_id: dict[str, object] = {u.user_id: u for u in users}

    # Map roster_id → owner_id
    roster_owner: dict[int, str] = {}
    for r in rosters:
        if r.owner_id:
            roster_owner[r.roster_id] = r.owner_id

    n_teams = len(rosters)

    # --- All-play accumulator per roster_id ---
    allplay_wins_acc: dict[int, int] = {r.roster_id: 0 for r in rosters}
    allplay_games_acc: dict[int, int] = {r.roster_id: 0 for r in rosters}

    # --- Lineup efficiency accumulator ---
    eff_sum: dict[int, float] = {r.roster_id: 0.0 for r in rosters}
    eff_count: dict[int, int] = {r.roster_id: 0 for r in rosters}

    for week_data in weekly_matchups:
        # Build {roster_id: points} for all-play
        scores: dict[int, float] = {}
        for entry in week_data:
            rid = entry.get("roster_id")
            pts = entry.get("points") or 0.0
            if rid is not None:
                scores[rid] = float(pts)

        # All-play: each team beats everyone it outscored
        score_list = sorted(scores.values())
        for rid, pts in scores.items():
            import bisect
            wins = bisect.bisect_left(score_list, pts)
            # Don't count ties against self; we're already beating strictly-lower scores
            allplay_wins_acc[rid] = allplay_wins_acc.get(rid, 0) + wins
            allplay_games_acc[rid] = allplay_games_acc.get(rid, 0) + (n_teams - 1)

        # Lineup efficiency per entry
        for entry in week_data:
            rid = entry.get("roster_id")
            if rid is None:
                continue
            starters: list[str] = entry.get("starters") or []
            players_points: dict[str, float] = entry.get("players_points") or {}

            actual_pts = sum(players_points.get(pid, 0.0) for pid in starters)
            all_pts = list(players_points.values())

            n_starters = len(starters)
            if n_starters > 0 and all_pts:
                all_pts_sorted = sorted(all_pts, reverse=True)
                optimal_pts = sum(all_pts_sorted[:n_starters])
                if optimal_pts > 0:
                    eff = min(actual_pts / optimal_pts, 1.0)
                    eff_sum[rid] = eff_sum.get(rid, 0.0) + eff
                    eff_count[rid] = eff_count.get(rid, 0) + 1

    # --- Roster dynasty value ---
    try:
        player_assets = build_player_assets(seasons=[2024])
        value_by_pid: dict[str, float] = {}
        from sleeper_ffm.model.dynasty import value_player
        for asset in player_assets:
            value_by_pid[asset.player_id] = value_player(asset)
    except Exception:
        log.warning("failed to build player assets; roster_value will be 0")
        value_by_pid = {}

    roster_values: dict[int, int] = {}
    for r in rosters:
        total = sum(value_by_pid.get(pid, 0.0) for pid in r.players)
        roster_values[r.roster_id] = round(total)

    avg_value = (
        sum(roster_values.values()) / len(roster_values) if roster_values else 1.0
    )
    if avg_value == 0:
        avg_value = 1.0

    # --- Build results ---
    results: list[OwnerSkillIndex] = []
    for r in rosters:
        rid = r.roster_id
        uid = roster_owner.get(rid, "")
        user = user_by_id.get(uid)
        display_name = getattr(user, "display_name", None) if user else None

        ap_wins = allplay_wins_acc.get(rid, 0)
        ap_games = allplay_games_acc.get(rid, 0)
        ap_pct = (ap_wins / ap_games) if ap_games > 0 else 0.0

        eff = (
            eff_sum.get(rid, 0.0) / eff_count.get(rid, 1)
            if eff_count.get(rid, 0) > 0
            else 0.85
        )

        rv = roster_values.get(rid, 0)
        rv_pct = rv / avg_value

        score = (
            ap_pct * 40.0
            + eff * 35.0
            + min(rv_pct, 1.5) / 1.5 * 25.0
        )
        score = round(min(max(score, 0.0), 100.0), 1)

        ap_display = round(ap_pct * 100)
        eff_display = round(eff * 100)
        rv_display = round((rv_pct - 1.0) * 100)
        rv_sign = "+" if rv_display >= 0 else ""
        summary = (
            f"All-play {ap_display}% · {eff_display}% lineup eff · "
            f"roster {rv_sign}{rv_display}% {'above' if rv_display >= 0 else 'below'} avg"
        )

        results.append(
            OwnerSkillIndex(
                roster_id=rid,
                user_id=uid,
                display_name=display_name,
                allplay_wins=ap_wins,
                allplay_games=ap_games,
                allplay_pct=round(ap_pct, 4),
                lineup_efficiency=round(eff, 4),
                roster_value=rv,
                roster_value_pct=round(rv_pct, 4),
                skill_score=score,
                skill_tier=_tier(score),
                summary=summary,
            )
        )

    results.sort(key=lambda x: x.skill_score, reverse=True)
    return results
