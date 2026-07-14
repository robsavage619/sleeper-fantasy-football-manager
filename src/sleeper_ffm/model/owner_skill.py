"""True Owner Skill Index — all-play, lineup efficiency, and roster value."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.config import DATA_DIR, DEFAULT_VALUE_SEASON, LEAGUE_ID
from sleeper_ffm.sleeper.client import SleeperClient
from sleeper_ffm.sleeper.models import Roster

log = logging.getLogger(__name__)

# Positions eligible for a FLEX slot in this league (standard RB/WR/TE flex).
_FLEX_ELIGIBLE: frozenset[str] = frozenset({"RB", "WR", "TE"})
# Slots that never start a player (bench / injured-reserve / taxi).
_NON_STARTING_SLOTS: frozenset[str] = frozenset({"BN", "IR", "TAXI"})


def _roster_positions() -> list[str]:
    """Load the league's roster-slot layout from data/league_settings.json (BN etc. included)."""
    import json

    path = DATA_DIR / "league_settings.json"
    try:
        with path.open() as fh:
            positions = json.load(fh).get("roster_positions", [])
        return [str(p) for p in positions]
    except (OSError, ValueError, KeyError) as exc:
        log.warning("could not load roster_positions (%s); using QB/2RB/2WR/TE/2FLEX", exc)
        return ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX"]


def optimal_lineup_points(
    players_points: dict[str, float],
    player_positions: dict[str, str],
    roster_positions: list[str],
) -> float:
    """Best legal lineup score given each slot's position eligibility.

    Fills dedicated position slots (QB/RB/WR/TE) with the best available player at that position,
    then fills FLEX slots with the best remaining flex-eligible player. Greedy is optimal here
    because FLEX eligibility is a superset of the dedicated skill positions.

    Args:
        players_points: {player_id: week points} for the whole roster.
        player_positions: {player_id: position}.
        roster_positions: League slot layout (e.g. ["QB", "RB", "RB", ..., "FLEX", "BN"]).

    Returns:
        Total points of the optimal legal starting lineup.
    """
    pools: dict[str, list[float]] = {pos: [] for pos in ("QB", "RB", "WR", "TE")}
    for pid, pts in players_points.items():
        pos = player_positions.get(pid)
        if pos in pools:
            pools[pos].append(float(pts))
    for pos in pools:
        pools[pos].sort(reverse=True)

    total = 0.0
    flex_slots = 0
    for slot in roster_positions:
        if slot in _NON_STARTING_SLOTS:
            continue
        if slot == "FLEX":
            flex_slots += 1
            continue
        if pools.get(slot):
            total += pools[slot].pop(0)

    remaining = sorted(
        (pts for pos in _FLEX_ELIGIBLE for pts in pools.get(pos, [])), reverse=True
    )
    total += sum(remaining[:flex_slots])
    return round(total, 2)


@dataclass
class OwnerSkillIndex:
    """Composite skill index for a single dynasty GM."""

    roster_id: int
    user_id: str
    display_name: str | None
    # All-play: how many weekly matchups would they win vs every other team
    allplay_wins: int  # total virtual wins across all weeks
    allplay_games: int  # total virtual games (weeks * (n_teams-1))
    allplay_pct: float  # allplay_wins / allplay_games, 0-1
    actual_wins: float  # standings wins, ties count as 0.5
    actual_losses: int
    actual_ties: int
    actual_games: float
    expected_wins: float  # all-play equivalent wins across actual schedule weeks
    schedule_luck: float  # actual_wins - expected_wins; positive = lucky
    skill_season: str
    # Lineup efficiency: actual pts / optimal pts from their roster. None when lineup data is
    # missing for every week — reported honestly rather than filled with a fabricated default.
    lineup_efficiency: float | None  # 0-1, e.g. 0.87 = started 87% of optimal lineup
    # Roster value relative to league average
    roster_value: int  # total dynasty value of their roster
    roster_value_pct: float  # their value / average value, e.g. 1.15 = 15% above avg
    # Composite skill score 0-100
    skill_score: float
    skill_tier: str  # 'ELITE' / 'STRONG' / 'AVERAGE' / 'WEAK'
    summary: str  # one human-readable line
    lineup_data_missing: bool = False  # True when lineup_efficiency could not be computed


def _tier(score: float) -> str:
    if score >= 75:
        return "ELITE"
    if score >= 55:
        return "STRONG"
    if score >= 35:
        return "AVERAGE"
    return "WEAK"


def _find_skill_sample(client: SleeperClient) -> tuple[str, list[Roster], list[list[dict]]]:
    """Return the latest league season with matchup data."""
    for league in client.league_history(LEAGUE_ID):
        weekly_matchups: list[list[dict]] = []
        for week in range(1, 18):
            try:
                week_data = client.matchups(week, league.league_id)
            except Exception:
                log.debug("matchup fetch stopped at %s week %d", league.season, week)
                break
            if not week_data:
                break
            weekly_matchups.append(week_data)
        if weekly_matchups:
            rosters = client.rosters(league.league_id)
            return league.season or "", rosters, weekly_matchups

    return "", [], []


def build_owner_skill() -> list[OwnerSkillIndex]:
    """Compute the True Owner Skill Index for every team in the league.

    Fetches current rosters plus the latest season with matchup data, then
    computes all-play record, lineup efficiency, and roster dynasty value.

    Returns:
        List of OwnerSkillIndex sorted by skill_score descending.
    """
    from sleeper_ffm.model.valuation import build_player_assets

    with SleeperClient() as client:
        rosters = client.rosters(LEAGUE_ID)
        users = client.users(LEAGUE_ID)
        sleeper_players = client.players()
        skill_season, skill_rosters, weekly_matchups = _find_skill_sample(client)

    player_positions: dict[str, str] = {
        pid: str(p.get("position") or "") for pid, p in sleeper_players.items()
    }
    roster_positions = _roster_positions()

    log.info("fetched %d weeks of matchup data for %s", len(weekly_matchups), skill_season)

    # Build user lookup by user_id
    user_by_id: dict[str, object] = {u.user_id: u for u in users}

    # Map roster_id → owner_id
    roster_owner: dict[int, str] = {}
    for r in rosters:
        if r.owner_id:
            roster_owner[r.roster_id] = r.owner_id

    skill_roster_owner: dict[int, str] = {}
    owner_standings: dict[str, tuple[float, int, int]] = {}
    for r in skill_rosters:
        if not getattr(r, "owner_id", None):
            continue
        owner_id = r.owner_id or ""
        skill_roster_owner[r.roster_id] = owner_id
        wins = float(r.settings.get("wins", 0) or 0)
        losses = int(r.settings.get("losses", 0) or 0)
        ties = int(r.settings.get("ties", 0) or 0)
        owner_standings[owner_id] = (wins + ties * 0.5, losses, ties)

    # All-play games come from the historical skill season, so the denominator must use that
    # season's team count — not the current league size, which may differ after expansion/folds.
    n_teams = len(skill_rosters) or len(rosters)

    # --- All-play accumulator per owner_id ---
    allplay_wins_acc: dict[str, int] = {r.owner_id or "": 0 for r in rosters}
    allplay_games_acc: dict[str, int] = {r.owner_id or "": 0 for r in rosters}

    # --- Lineup efficiency accumulator ---
    eff_sum: dict[str, float] = {r.owner_id or "": 0.0 for r in rosters}
    eff_count: dict[str, int] = {r.owner_id or "": 0 for r in rosters}

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

            owner_id = skill_roster_owner.get(rid)
            if owner_id is None:
                continue
            wins = bisect.bisect_left(score_list, pts)
            # Don't count ties against self; we're already beating strictly-lower scores
            allplay_wins_acc[owner_id] = allplay_wins_acc.get(owner_id, 0) + wins
            allplay_games_acc[owner_id] = allplay_games_acc.get(owner_id, 0) + (n_teams - 1)

        # Lineup efficiency per entry
        for entry in week_data:
            rid = entry.get("roster_id")
            if rid is None:
                continue
            owner_id = skill_roster_owner.get(rid)
            if owner_id is None:
                continue
            starters: list[str] = entry.get("starters") or []
            players_points: dict[str, float] = entry.get("players_points") or {}

            actual_pts = sum(players_points.get(pid, 0.0) for pid in starters)
            optimal_pts = optimal_lineup_points(
                players_points, player_positions, roster_positions
            )
            if starters and players_points and optimal_pts > 0:
                eff = min(actual_pts / optimal_pts, 1.0)
                eff_sum[owner_id] = eff_sum.get(owner_id, 0.0) + eff
                eff_count[owner_id] = eff_count.get(owner_id, 0) + 1

    # --- Roster dynasty value ---
    try:
        player_assets = build_player_assets(seasons=[DEFAULT_VALUE_SEASON])
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

    avg_value = sum(roster_values.values()) / len(roster_values) if roster_values else 1.0
    if avg_value == 0:
        avg_value = 1.0

    # --- Build results ---
    results: list[OwnerSkillIndex] = []
    for r in rosters:
        rid = r.roster_id
        uid = roster_owner.get(rid, "")
        user = user_by_id.get(uid)
        display_name = getattr(user, "display_name", None) if user else None

        ap_wins = allplay_wins_acc.get(uid, 0)
        ap_games = allplay_games_acc.get(uid, 0)
        ap_pct = (ap_wins / ap_games) if ap_games > 0 else 0.0

        has_eff = eff_count.get(uid, 0) > 0
        eff: float | None = eff_sum.get(uid, 0.0) / eff_count[uid] if has_eff else None
        actual_wins, actual_losses, actual_ties = owner_standings.get(uid, (0.0, 0, 0))
        actual_games = actual_wins + actual_losses + actual_ties * 0.5
        expected_wins = ap_pct * actual_games
        schedule_luck = actual_wins - expected_wins

        rv = roster_values.get(rid, 0)
        rv_pct = rv / avg_value

        # Skill score weights all-play (40), lineup efficiency (35), roster value (25). When
        # lineup data is missing, drop that channel and renormalize the remaining 65 to 100 —
        # never invent an efficiency to fill the slot.
        rv_term = min(rv_pct, 1.5) / 1.5 * 25.0
        if eff is not None:
            score = ap_pct * 40.0 + eff * 35.0 + rv_term
        else:
            score = (ap_pct * 40.0 + rv_term) * (100.0 / 65.0)
        score = round(min(max(score, 0.0), 100.0), 1)

        ap_display = round(ap_pct * 100)
        eff_display = f"{round(eff * 100)}%" if eff is not None else "n/a"
        rv_display = round((rv_pct - 1.0) * 100)
        rv_sign = "+" if rv_display >= 0 else ""
        summary = (
            f"All-play {ap_display}% · {eff_display} lineup eff · "
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
                actual_wins=round(actual_wins, 1),
                actual_losses=actual_losses,
                actual_ties=actual_ties,
                actual_games=round(actual_games, 1),
                expected_wins=round(expected_wins, 2),
                schedule_luck=round(schedule_luck, 2),
                skill_season=skill_season,
                lineup_efficiency=round(eff, 4) if eff is not None else None,
                lineup_data_missing=eff is None,
                roster_value=rv,
                roster_value_pct=round(rv_pct, 4),
                skill_score=score,
                skill_tier=_tier(score),
                summary=summary,
            )
        )

    results.sort(key=lambda x: x.skill_score, reverse=True)
    return results
