"""Weekly narrative context prompt builder.

Assembles current-week league data — roster state, matchup opponent, waiver
targets, top trade angles — into a structured prompt for Claude Code reasoning.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from sleeper_ffm.config import LEAGUE_ID, MY_ROSTER_ID
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)


@dataclass
class NarrativeContext:
    """Structured payload returned by GET /season/narrative."""

    week: int
    season: str
    season_type: str
    prompt: str
    sections: dict = field(default_factory=dict)
    assembled_at: str = ""


def _ordinal(n: int) -> str:
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    suffix = suffixes.get(n % 10, "th") if n % 100 not in (11, 12, 13) else "th"
    return f"{n}{suffix}"


def _roster_section(roster_id: int, rosters: list, sleeper_players: dict) -> str:
    """Summarize the target roster's players by position."""
    from sleeper_ffm.model.valuation import SKILL_POSITIONS

    roster = next((r for r in rosters if r.roster_id == roster_id), None)
    if not roster:
        return "(roster not found)"
    lines: list[str] = []
    pos_groups: dict[str, list[str]] = {}
    for pid in roster.starters:
        sp = sleeper_players.get(pid, {})
        pos = sp.get("position", "")
        if pos not in SKILL_POSITIONS:
            continue
        name = sp.get("full_name") or pid
        pos_groups.setdefault(pos, []).append(name)
    for pos in ["QB", "RB", "WR", "TE"]:
        if pos in pos_groups:
            lines.append(f"  {pos}: {', '.join(pos_groups[pos])}")
    return "\n".join(lines) if lines else "  (no skill-position starters found)"


def build_narrative_context(
    league_id: str = LEAGUE_ID,
    my_roster_id: int = MY_ROSTER_ID,
    season_hint: int | None = None,
) -> NarrativeContext:
    """Assemble weekly context from live Sleeper data into a Claude Code prompt.

    Fetches NFL state, my roster, this week's matchup opponent, waiver-wire adds,
    and owner profiles, then formats a structured reasoning prompt.

    Args:
        league_id: Sleeper league ID.
        my_roster_id: Rob's roster ID.
        season_hint: Override season year for data loading.

    Returns:
        NarrativeContext with the assembled prompt and section data.
    """
    with SleeperClient(league_id=league_id) as c:
        state = c.state_nfl()
        rosters = c.rosters()
        users = c.users()
        sleeper_players = c.players()
        trending_adds = c.trending("add", lookback_hours=48, limit=25)

        week = state.week or 1
        season = state.season or str(datetime.date.today().year)
        season_type = state.season_type or "off"

        # Only fetch matchups if in-season
        matchups: list[dict] = []
        if season_type == "regular" and week:
            try:
                matchups = c.matchups(week)
            except Exception:
                log.warning("narrative: could not fetch matchups for week %d", week)

    # Build name maps
    user_by_id = {u.user_id: u for u in users}
    name_by_roster: dict[int, str] = {}
    avatar_by_roster: dict[int, str | None] = {}
    for r in rosters:
        uid = r.owner_id or ""
        u = user_by_id.get(uid)
        name_by_roster[r.roster_id] = (u.display_name or uid) if u else uid
        avatar_by_roster[r.roster_id] = u.avatar if u else None

    my_roster = next((r for r in rosters if r.roster_id == my_roster_id), None)
    my_name = name_by_roster.get(my_roster_id, "Rob")

    # ── My starter lineup ────────────────────────────────────────────────────
    from sleeper_ffm.model.valuation import SKILL_POSITIONS

    starter_lines: list[str] = []
    bench_names: list[str] = []
    taxi_names: list[str] = []
    if my_roster:
        starters_set = set(my_roster.starters)
        taxi_set = set(my_roster.taxi or [])
        for pid in my_roster.players:
            sp = sleeper_players.get(pid, {})
            pos = sp.get("position", "")
            if pos not in SKILL_POSITIONS:
                continue
            name = sp.get("full_name") or pid
            if pid in starters_set:
                starter_lines.append(f"  {pos:3s}  {name}")
            elif pid in taxi_set:
                taxi_names.append(name)
            else:
                bench_names.append(name)

    roster_text = "\n".join(starter_lines) if starter_lines else "  (no starters)"

    # ── Matchup opponent ─────────────────────────────────────────────────────
    opponent_text = "(off-season — no matchup)"
    opponent_roster_id: int | None = None
    if matchups:
        my_matchup = next((m for m in matchups if m.get("roster_id") == my_roster_id), None)
        if my_matchup:
            my_matchup_id = my_matchup.get("matchup_id")
            opp = next(
                (m for m in matchups
                 if m.get("matchup_id") == my_matchup_id and m.get("roster_id") != my_roster_id),
                None,
            )
            if opp:
                opponent_roster_id = opp.get("roster_id")
                opp_name = name_by_roster.get(opponent_roster_id, "Unknown")
                my_pts = my_matchup.get("points", 0) or 0
                opp_pts = opp.get("points", 0) or 0
                opponent_text = (
                    f"{opp_name} (roster #{opponent_roster_id})\n"
                    f"  Current score: YOU {my_pts:.1f} — THEM {opp_pts:.1f}"
                )
                opp_starters = _roster_section(opponent_roster_id, rosters, sleeper_players)
                opponent_text += f"\n  Their starters:\n{opp_starters}"

    # ── Waiver wire ──────────────────────────────────────────────────────────
    rostered_ids: set[str] = set()
    for r in rosters:
        rostered_ids.update(r.players)

    waiver_lines: list[str] = []
    for tp in trending_adds[:10]:
        sp = sleeper_players.get(tp.player_id, {})
        pos = sp.get("position", "")
        if pos not in SKILL_POSITIONS:
            continue
        if tp.player_id in rostered_ids:
            continue
        team = sp.get("team") or "FA"
        name = sp.get("full_name") or tp.player_id
        waiver_lines.append(
            f"  {pos:3s}  {name:24s}  {team:4s}  +{tp.count} adds (48h)"
        )
        if len(waiver_lines) >= 7:
            break

    waiver_text = "\n".join(waiver_lines) if waiver_lines else "  (no trending adds)"

    # ── Trade intelligence ───────────────────────────────────────────────────
    trade_lines: list[str] = []
    my_picks = len(my_roster.taxi or []) if my_roster else 0
    my_pos: dict[str, int] = {}
    if my_roster:
        for pid in my_roster.players:
            pos = sleeper_players.get(pid, {}).get("position", "")
            if pos in SKILL_POSITIONS:
                my_pos[pos] = my_pos.get(pos, 0) + 1

    for r in rosters:
        if r.roster_id == my_roster_id:
            continue
        their_name = name_by_roster.get(r.roster_id, f"Roster {r.roster_id}")
        their_pos: dict[str, int] = {}
        for pid in r.players:
            pos = sleeper_players.get(pid, {}).get("position", "")
            if pos in SKILL_POSITIONS:
                their_pos[pos] = their_pos.get(pos, 0) + 1

        # Identify complementary positions
        gaps = []
        for pos in ["QB", "RB", "WR", "TE"]:
            mine = my_pos.get(pos, 0)
            theirs = their_pos.get(pos, 0)
            if mine > theirs + 3:
                gaps.append(f"your {pos} depth > their need")
            elif theirs > mine + 3:
                gaps.append(f"their {pos} depth > your need")
        if gaps:
            trade_lines.append(f"  {their_name}: {'; '.join(gaps[:2])}")
        if len(trade_lines) >= 4:
            break

    trade_text = "\n".join(trade_lines) if trade_lines else "  (no clear positional gaps detected)"

    # ── Bench / depth ────────────────────────────────────────────────────────
    bench_text = f"  {', '.join(bench_names[:10])}" if bench_names else "  (none)"
    taxi_text = f"  {', '.join(taxi_names)}" if taxi_names else "  (none)"

    # ── Assemble prompt ──────────────────────────────────────────────────────
    off_season_note = (
        "\n⚠️  OFF-SEASON MODE: No live scoring. Focus on roster construction,\n"
        "   draft prep, and trade positioning rather than start/sit.\n"
        if season_type != "regular"
        else ""
    )

    prompt = f"""# Weekly Dynasty War Room — {season} Week {week}
Season type: {season_type.upper()}
{off_season_note}
## My Team ({my_name})

### Current Starters
{roster_text}

### Bench
{bench_text}

### Taxi Squad (development)
{taxi_text}

## This Week's Matchup
{opponent_text}

## Waiver Wire — Top Available (48h trending)
{waiver_text}

## Trade Intelligence — Positional Angles
{trade_text}

---
## Your Task

You are the AI GM for {my_name}'s dynasty squad. Given the context above:

1. **Start/Sit Check**: Are my starters optimal? Any obvious upgrades on bench?
   Consider rest-of-season value, matchups, and injury risk.

2. **Waiver Priority**: Which 1-2 waiver targets are worth a bid? What's a fair
   FAAB offer (league uses $500 budget, Tue waivers)? Who to drop?

3. **Trade Opportunity**: Based on the positional gaps, propose one specific trade
   to send this week. Be concrete: player X for player Y (+ pick Z if needed).
   Frame it around the other GM's archetype and what they need.

4. **Dynasty Outlook**: Is this a win-now week, or should I think long-term?
   Any asset I should be moving while the market is right?

Post findings via: `sffm finding post --kind narrative --body '<json>'`
where JSON has keys: `startsit`, `waiver_add`, `waiver_drop`, `trade_proposal`,
`dynasty_angle`, `urgency` (LOW / MED / HIGH).
"""

    assembled_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    sections = {
        "starters": starter_lines,
        "bench": bench_names[:10],
        "taxi": taxi_names,
        "matchup": opponent_text,
        "waiver_adds": waiver_lines,
        "trade_angles": trade_lines,
    }

    return NarrativeContext(
        week=week,
        season=season,
        season_type=season_type,
        prompt=prompt,
        sections=sections,
        assembled_at=assembled_at,
    )
