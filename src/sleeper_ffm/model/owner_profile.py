"""Owner behavioral profiles built from live Sleeper data."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass

from sleeper_ffm.config import DRAFT_ID, LEAGUE_ID
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)


@dataclass
class OwnerProfile:
    """Behavioral snapshot of one dynasty owner."""

    user_id: str
    display_name: str
    roster_id: int
    avatar: str | None
    player_count: int
    starter_count: int
    taxi_count: int
    reserve_count: int
    # Current roster composition
    positions: dict[str, int]
    # Traded picks inventory
    picks_owned: int  # picks currently held by this roster
    picks_given: int  # picks originally from this roster now held by others
    # Simple archetype based on available signals
    archetype: str  # "REBUILDER" | "CONTENDER" | "BALANCED" | "UNKNOWN"
    archetype_rationale: str


def build_owner_profiles(league_id: str = LEAGUE_ID) -> list[OwnerProfile]:
    """Build behavioral profiles for every owner in the league.

    Fetches users, rosters, traded picks, and the player dump in one session,
    then applies position counts and a simple archetype heuristic.

    Args:
        league_id: Sleeper league ID to profile.

    Returns:
        One OwnerProfile per roster, ordered by roster_id ascending.
    """
    with SleeperClient(league_id=league_id) as c:
        users = c.users(league_id=league_id)
        rosters = c.rosters(league_id=league_id)
        picks = c.traded_picks(league_id=league_id)
        players_dump = c.players()
        try:
            draft = c.draft(DRAFT_ID)
            draft_rounds = int(draft.settings.get("rounds", 4) or 4)
        except Exception as exc:
            log.warning("could not load draft rounds (%s); defaulting to 4", exc)
            draft_rounds = 4

    user_by_id = {u.user_id: u for u in users}
    profiles: list[OwnerProfile] = []

    for roster in sorted(rosters, key=lambda r: r.roster_id):
        owner_id = roster.owner_id or ""
        user = user_by_id.get(owner_id)
        display_name = (user.display_name or owner_id) if user else owner_id
        avatar: str | None = getattr(user, "avatar", None) if user else None

        # Position counts from the full player dump
        pos_counts: Counter[str] = Counter()
        for pid in roster.players:
            p_data = players_dump.get(pid, {})
            pos = p_data.get("position")
            if pos:
                pos_counts[pos] += 1

        taxi_list = roster.taxi or []
        reserve_list = roster.reserve or []

        # Pick inventory using the same logic as owner_dossier: traded_picks only shows picks
        # that have changed hands, so own untouched future picks must be inferred from the
        # full (season, round) space minus any slots this roster traded away.
        import datetime

        current_year = datetime.date.today().year
        data_seasons = {p.season for p in picks if int(p.season) >= current_year}
        data_seasons |= {str(current_year), str(current_year + 1)}
        live_seasons = sorted(data_seasons)
        # Round space must come from the draft's configured rounds, not from traded picks:
        # a round nobody has traded still exists for every owner. Inferring rounds from the
        # traded-picks set (previous behaviour) silently dropped own untouched picks in those
        # rounds while foreign_held still counted them — an asymmetric, understated count.
        live_rounds = list(range(1, draft_rounds + 1))

        traded_away = {
            (p.season, p.round)
            for p in picks
            if p.roster_id == roster.roster_id and p.owner_id != roster.roster_id
        }
        own_held = sum(1 for s in live_seasons for r in live_rounds if (s, r) not in traded_away)
        foreign_held = sum(
            1
            for p in picks
            if p.owner_id == roster.roster_id
            and p.roster_id != roster.roster_id
            and p.season in live_seasons
        )
        picks_owned = own_held + foreign_held
        picks_given = len(traded_away)

        archetype, rationale = _classify(len(taxi_list), picks_given, len(roster.players))

        profiles.append(
            OwnerProfile(
                user_id=owner_id,
                display_name=display_name,
                roster_id=roster.roster_id,
                avatar=avatar,
                player_count=len(roster.players),
                starter_count=len(roster.starters),
                taxi_count=len(taxi_list),
                reserve_count=len(reserve_list),
                positions=dict(pos_counts),
                picks_owned=picks_owned,
                picks_given=picks_given,
                archetype=archetype,
                archetype_rationale=rationale,
            )
        )

    return profiles


def _classify(taxi_count: int, picks_given: int, player_count: int) -> tuple[str, str]:
    """Apply the archetype heuristic; first match wins.

    Uses picks_given (own picks traded away) rather than picks_owned, since with the corrected
    pick count everyone holds 6-10 picks and an absolute threshold doesn't discriminate.
    Actively giving away future picks is the real rebuild signal.
    """
    if taxi_count >= 2 and picks_given >= 3:
        return (
            "REBUILDER",
            (
                f"taxi={taxi_count} dev players, traded away {picks_given} own picks"
                " — accumulating youth and draft capital"
            ),
        )
    if player_count >= 28 and taxi_count == 0:
        return (
            "CONTENDER",
            (
                f"player_count={player_count} (>=28) with no taxi spots"
                " — full roster depth, no development track"
            ),
        )
    return (
        "BALANCED",
        (
            f"taxi={taxi_count}, picks_given={picks_given}, player_count={player_count}"
            " — no dominant rebuild or win-now signal"
        ),
    )
