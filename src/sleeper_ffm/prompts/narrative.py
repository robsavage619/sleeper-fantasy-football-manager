"""Weekly narrative context prompt builder.

Assembles current-week league data — roster state, matchup opponent, waiver
targets, top trade angles — into a structured prompt for Claude Code reasoning.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from sleeper_ffm.api.routers.roster import _build_player_rows
from sleeper_ffm.config import DEFAULT_VALUE_SEASON, LEAGUE_ID, MY_ROSTER_ID
from sleeper_ffm.market.blend import build_player_blend
from sleeper_ffm.model.owner_dossier import _contention
from sleeper_ffm.model.owner_profile import _classify
from sleeper_ffm.model.valuation import SKILL_POSITIONS, build_player_assets
from sleeper_ffm.sleeper.client import SleeperClient
from sleeper_ffm.sleeper.models import Roster, TradedPick

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


@dataclass(frozen=True)
class _TradeRosterSummary:
    """Valuation-backed owner snapshot for narrative trade-angle generation."""

    roster_id: int
    display_name: str
    archetype: str
    window: str
    total_value: float
    value_rank: int
    players: list[dict]
    position_values: dict[str, float]
    position_counts: dict[str, int]
    position_ranks: dict[str, int]
    picks_owned: int
    picks_given: int


def _ordinal(n: int) -> str:
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    suffix = suffixes.get(n % 10, "th") if n % 100 not in (11, 12, 13) else "th"
    return f"{n}{suffix}"


def _valuation_season(season: str, season_hint: int | None) -> int:
    """Use the latest completed NFL season unless the caller explicitly overrides it."""
    if season_hint is not None:
        return season_hint
    try:
        current_season = int(season)
    except ValueError:
        return DEFAULT_VALUE_SEASON
    return min(current_season - 1, DEFAULT_VALUE_SEASON)


def _roster_section(roster_id: int, rosters: list, sleeper_players: dict) -> str:
    """Summarize the target roster's players by position."""
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


def _position_values(players: list[dict]) -> dict[str, float]:
    """Sum dynasty value by skill position."""
    return {
        pos: round(sum(p["dynasty_value"] for p in players if p["position"] == pos), 1)
        for pos in ["QB", "RB", "WR", "TE"]
    }


def _position_counts(players: list[dict]) -> dict[str, int]:
    """Count rostered players by skill position."""
    return {
        pos: sum(1 for p in players if p["position"] == pos) for pos in ["QB", "RB", "WR", "TE"]
    }


def _pick_inventory(roster_id: int, picks: list[TradedPick]) -> tuple[int, int]:
    """Infer current future-pick inventory from Sleeper's changed-hands pick feed."""
    current_year = datetime.date.today().year
    data_seasons = {p.season for p in picks if p.season.isdigit() and int(p.season) >= current_year}
    data_seasons |= {str(current_year), str(current_year + 1)}
    live_seasons = sorted(data_seasons)
    live_rounds = sorted({p.round for p in picks}) or [1, 2, 3, 4]

    traded_away = {
        (p.season, p.round) for p in picks if p.roster_id == roster_id and p.owner_id != roster_id
    }
    own_held = sum(
        1
        for season in live_seasons
        for round_ in live_rounds
        if (season, round_) not in traded_away
    )
    foreign_held = sum(
        1
        for p in picks
        if p.owner_id == roster_id and p.roster_id != roster_id and p.season in live_seasons
    )
    return own_held + foreign_held, len(traded_away)


def _build_trade_summaries(
    rosters: list[Roster],
    name_by_roster: dict[int, str],
    sleeper_players: dict,
    picks: list[TradedPick],
    valuation_season: int,
) -> dict[int, _TradeRosterSummary]:
    """Build one valuation-backed trade summary per roster."""
    vet_assets = build_player_assets(seasons=[valuation_season], sleeper_players=sleeper_players)
    vet_map = {a.player_id: a for a in vet_assets}
    blend = build_player_blend(vet_assets)

    players_by_roster = {
        roster.roster_id: _build_player_rows(roster, vet_map, sleeper_players, blend=blend)
        for roster in rosters
    }
    total_values = {
        roster_id: round(sum(p["dynasty_value"] for p in players), 1)
        for roster_id, players in players_by_roster.items()
    }
    value_order = sorted(total_values, key=lambda roster_id: (-total_values[roster_id], roster_id))

    pos_values_by_roster = {
        roster_id: _position_values(players) for roster_id, players in players_by_roster.items()
    }
    position_ranks: dict[int, dict[str, int]] = {roster.roster_id: {} for roster in rosters}
    for pos in ["QB", "RB", "WR", "TE"]:
        order = sorted(
            pos_values_by_roster,
            key=lambda roster_id: (-pos_values_by_roster[roster_id][pos], roster_id),
        )
        for idx, roster_id in enumerate(order, 1):
            position_ranks[roster_id][pos] = idx

    summaries: dict[int, _TradeRosterSummary] = {}
    for roster in rosters:
        players = players_by_roster[roster.roster_id]
        total_value = total_values[roster.roster_id]
        picks_owned, picks_given = _pick_inventory(roster.roster_id, picks)
        archetype, _ = _classify(len(roster.taxi or []), picks_given, len(roster.players))
        contention = _contention(players, total_value)
        summaries[roster.roster_id] = _TradeRosterSummary(
            roster_id=roster.roster_id,
            display_name=name_by_roster.get(roster.roster_id, f"Roster {roster.roster_id}"),
            archetype=archetype,
            window=contention.window,
            total_value=total_value,
            value_rank=value_order.index(roster.roster_id) + 1,
            players=players,
            position_values=pos_values_by_roster[roster.roster_id],
            position_counts=_position_counts(players),
            position_ranks=position_ranks[roster.roster_id],
            picks_owned=picks_owned,
            picks_given=picks_given,
        )
    return summaries


def _format_asset(player: dict) -> str:
    """Format a player row for a compact trade-angle line."""
    team = player.get("team") or "FA"
    value = player["dynasty_value"]
    return f"{player['name']} ({player['position']} {team}, value {value:.0f})"


def _chip_from_position(players: list[dict], position: str, prefer_bench: bool) -> dict | None:
    """Choose a plausible trade chip from one position."""
    position_players = [p for p in players if p["position"] == position and p["dynasty_value"] > 0]
    if not position_players:
        return None

    if prefer_bench:
        bench = [p for p in position_players if not p["is_starter"]]
        if bench:
            return max(bench, key=lambda p: p["dynasty_value"])
        return min(position_players, key=lambda p: p["dynasty_value"])

    non_core = [p for p in position_players if not p["is_starter"]]
    if non_core:
        return max(non_core, key=lambda p: p["dynasty_value"])
    return sorted(position_players, key=lambda p: p["dynasty_value"], reverse=True)[
        min(1, len(position_players) - 1)
    ]


def _trade_adjustment(offer_value: float, ask_value: float, target: _TradeRosterSummary) -> str:
    """Suggest a simple pick/value adjustment for uneven player values."""
    delta = ask_value - offer_value
    if abs(delta) <= 15:
        return "straight-up range"
    if delta > 35:
        return "add a 2026 2nd or pivot to a cheaper target"
    if delta > 15:
        return "add a 2026 3rd or bench sweetener"
    if target.picks_owned > target.picks_given + 2:
        return "ask for a 2026 3rd back"
    return "ask for a depth player back"


def _build_trade_angles(
    summaries: dict[int, _TradeRosterSummary],
    my_roster_id: int,
    league_size: int,
) -> list[str]:
    """Return valuation-backed, player-specific trade angles for the narrative prompt."""
    my_summary = summaries[my_roster_id]
    angles: list[tuple[float, str]] = []

    for roster_id, target in summaries.items():
        if roster_id == my_roster_id:
            continue

        my_surplus = [
            pos
            for pos in ["QB", "RB", "WR", "TE"]
            if my_summary.position_ranks[pos] <= 4 and target.position_ranks[pos] >= 6
        ]
        their_surplus = [
            pos
            for pos in ["QB", "RB", "WR", "TE"]
            if target.position_ranks[pos] <= 4 and my_summary.position_ranks[pos] >= 6
        ]
        if not my_surplus:
            continue

        offer_pos = max(
            my_surplus,
            key=lambda pos: my_summary.position_values[pos] - target.position_values[pos],
        )
        ask_pos = (
            max(
                their_surplus,
                key=lambda pos: target.position_values[pos] - my_summary.position_values[pos],
            )
            if their_surplus
            else ""
        )

        offer = _chip_from_position(my_summary.players, offer_pos, prefer_bench=True)
        ask = _chip_from_position(target.players, ask_pos, prefer_bench=False) if ask_pos else None
        if offer is None:
            continue

        if ask:
            adjustment = _trade_adjustment(offer["dynasty_value"], ask["dynasty_value"], target)
            action = f"send {_format_asset(offer)} for {_format_asset(ask)}; {adjustment}"
        elif target.archetype == "CONTENDER":
            action = f"sell {_format_asset(offer)} for a 2026 2nd/3rd pick package"
        else:
            action = f"package {_format_asset(offer)} toward their younger {offer_pos} upgrade"

        fit_score = (
            max(0, league_size + 1 - my_summary.position_ranks[offer_pos])
            + target.position_ranks[offer_pos]
            + (target.total_value - my_summary.total_value) / 100
        )
        need = (
            f"{offer_pos} need (their rank {_ordinal(target.position_ranks[offer_pos])}, "
            f"your rank {_ordinal(my_summary.position_ranks[offer_pos])})"
        )
        if ask_pos:
            need += (
                f"; your {ask_pos} need (their rank {_ordinal(target.position_ranks[ask_pos])}, "
                f"your rank {_ordinal(my_summary.position_ranks[ask_pos])})"
            )
        line = (
            f"  {target.display_name}: {target.archetype}, {target.window}, "
            f"value rank {_ordinal(target.value_rank)}. {need}. Action: {action}."
        )
        angles.append((fit_score, line))

    return [line for _, line in sorted(angles, key=lambda item: item[0], reverse=True)[:4]]


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
        picks = c.traded_picks()

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
                (
                    m
                    for m in matchups
                    if m.get("matchup_id") == my_matchup_id and m.get("roster_id") != my_roster_id
                ),
                None,
            )
            if opp is not None:
                raw_opponent_roster_id = opp.get("roster_id")
                if isinstance(raw_opponent_roster_id, int):
                    opponent_roster_id = raw_opponent_roster_id
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
        waiver_lines.append(f"  {pos:3s}  {name:24s}  {team:4s}  +{tp.count} adds (48h)")
        if len(waiver_lines) >= 7:
            break

    waiver_text = "\n".join(waiver_lines) if waiver_lines else "  (no trending adds)"

    # ── Trade intelligence ───────────────────────────────────────────────────
    trade_lines: list[str] = []
    if my_roster:
        valuation_season = _valuation_season(season, season_hint)
        summaries = _build_trade_summaries(
            rosters=rosters,
            name_by_roster=name_by_roster,
            sleeper_players=sleeper_players,
            picks=picks,
            valuation_season=valuation_season,
        )
        trade_lines = _build_trade_angles(
            summaries=summaries,
            my_roster_id=my_roster_id,
            league_size=len(rosters),
        )

    trade_text = "\n".join(trade_lines) if trade_lines else "  (no clear valuation-backed fits)"

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

    assembled_at = datetime.datetime.now(datetime.UTC).isoformat()

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
