"""Rich per-owner dossier: valued roster, age/position breakdowns, contention window."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sleeper_ffm.api.routers.roster import _build_player_rows
from sleeper_ffm.config import DEFAULT_VALUE_SEASON, DRAFT_ID
from sleeper_ffm.model.owner_profile import _classify
from sleeper_ffm.model.valuation import build_player_assets
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)


@dataclass
class AgeBucket:
    """A dynasty age band with player count and summed dynasty value."""

    label: str
    min_age: int
    max_age: int
    count: int
    value: float


@dataclass
class PositionValue:
    """Summed dynasty value, count, and share of total for one position."""

    position: str
    value: float
    count: int
    pct: float


@dataclass
class PositionRank:
    """League-relative standing for one position: rank, average, and depth tier."""

    position: str
    value: float
    rank: int
    of: int
    league_avg: float
    tier: str


@dataclass
class ContentionWindow:
    """Value-weighted contention outlook for a roster."""

    score: float
    label: str
    window: str
    rationale: str


@dataclass
class OwnerDossier:
    """Full per-owner dossier matching the dossier endpoint contract."""

    roster_id: int
    user_id: str
    display_name: str
    avatar: str | None
    archetype: str
    archetype_rationale: str
    total_dynasty_value: float
    player_count: int
    avg_age: float
    avg_starter_age: float
    players: list[dict]
    age_buckets: list[AgeBucket]
    value_by_position: list[PositionValue]
    contention: ContentionWindow
    picks_owned: list[dict] = field(default_factory=list)
    picks_traded_away: list[dict] = field(default_factory=list)
    value_rank: int = 0
    league_size: int = 0
    top_heavy_pct: float = 0.0
    position_ranks: list = field(default_factory=list)


# Dynasty age bands, ascending. (label, min_age, max_age)
_AGE_BANDS: tuple[tuple[str, int, int], ...] = (
    ("≤23", 0, 23),
    ("24–26", 24, 26),  # noqa: RUF001
    ("27–29", 27, 29),  # noqa: RUF001
    ("30–32", 30, 32),  # noqa: RUF001
    ("33+", 33, 99),
)


def _age_buckets(players: list[dict]) -> list[AgeBucket]:
    """Bucket players into the five dynasty age bands with count and summed value."""
    buckets: list[AgeBucket] = []
    for label, lo, hi in _AGE_BANDS:
        in_band = [p for p in players if lo <= p["age"] <= hi]
        value = round(sum(p["dynasty_value"] for p in in_band), 1)
        buckets.append(
            AgeBucket(label=label, min_age=lo, max_age=hi, count=len(in_band), value=value)
        )
    return buckets


def _value_by_position(players: list[dict], total: float) -> list[PositionValue]:
    """Summed dynasty value, count, and pct-of-total for QB, RB, WR, TE."""
    ordered = ["QB", "RB", "WR", "TE"]
    result: list[PositionValue] = []
    for pos in ordered:
        rows = [p for p in players if p["position"] == pos]
        value = round(sum(p["dynasty_value"] for p in rows), 1)
        pct = round(value / total * 100, 1) if total else 0.0
        result.append(PositionValue(position=pos, value=value, count=len(rows), pct=pct))
    return result


_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")


def _position_totals(rows: list[dict]) -> dict[str, float]:
    """Sum dynasty value per position (QB/RB/WR/TE) for one roster's rows."""
    totals = {pos: 0.0 for pos in _POSITIONS}
    for p in rows:
        pos = p["position"]
        if pos in totals:
            totals[pos] += p["dynasty_value"]
    return totals


def _position_ranks(
    roster_id: int, roster_pos: dict[int, dict[str, float]], league_size: int
) -> list[PositionRank]:
    """League-relative rank, average, and depth tier per position for one roster."""
    ranks: list[PositionRank] = []
    for pos in _POSITIONS:
        order = sorted(roster_pos, key=lambda rid: (-roster_pos[rid][pos], rid))
        rank = order.index(roster_id) + 1
        league_avg = round(sum(roster_pos[rid][pos] for rid in roster_pos) / league_size, 1)
        frac = rank / league_size
        if frac <= 0.3:
            tier = "DEEP"
        elif frac <= 0.5:
            tier = "SOLID"
        elif frac <= 0.7:
            tier = "AVERAGE"
        else:
            tier = "THIN"
        ranks.append(
            PositionRank(
                position=pos,
                value=round(roster_pos[roster_id][pos], 1),
                rank=rank,
                of=league_size,
                league_avg=league_avg,
                tier=tier,
            )
        )
    return ranks


def _contention(players: list[dict], total: float) -> ContentionWindow:
    """Value-weighted contention window from youth vs veteran value shares."""
    youth_value = sum(p["dynasty_value"] for p in players if p["age"] <= 25)
    vet_value = sum(p["dynasty_value"] for p in players if p["age"] >= 30)
    youth_share = youth_value / total if total else 0.0
    vet_share = vet_value / total if total else 0.0

    score = round(max(0.0, min(100.0, 50 + (youth_share - vet_share) * 100)), 0)

    if score >= 70:
        label, window = "ASCENDING", "3+ year window"
    elif score >= 55:
        label, window = "OPENING", "2-3 year window"
    elif score >= 45:
        label, window = "OPEN", "win-now window"
    elif score >= 30:
        label, window = "CLOSING", "1-2 year window"
    else:
        label, window = "RETOOLING", "window closing"

    value_weighted_age = (
        sum(p["age"] * p["dynasty_value"] for p in players) / total if total else 0.0
    )
    rationale = (
        f"{round(youth_share * 100)}% of value in players ≤25, "
        f"{round(vet_share * 100)}% in players ≥30 "
        f"— value-weighted age {value_weighted_age:.1f}"
    )
    return ContentionWindow(score=score, label=label, window=window, rationale=rationale)


def build_dossier(roster_id: int, season: int = DEFAULT_VALUE_SEASON) -> OwnerDossier:
    """Build the full dossier for one roster.

    Args:
        roster_id: Sleeper roster id to profile.
        season: NFL season year to use for FPAR computation.

    Returns:
        A populated :class:`OwnerDossier`.

    Raises:
        ValueError: If ``roster_id`` is not found in the league.
    """
    with SleeperClient() as c:
        rosters = c.rosters()
        users = c.users()
        sleeper_players = c.players()
        picks = c.traded_picks()
        draft = c.draft(DRAFT_ID)

    roster = next((r for r in rosters if r.roster_id == roster_id), None)
    if roster is None:
        raise ValueError(f"roster {roster_id} not found")

    user_by_id = {u.user_id: u for u in users}
    owner_id = roster.owner_id or ""
    user = user_by_id.get(owner_id)
    display_name = (user.display_name or owner_id) if user else owner_id
    avatar = user.avatar if user else None

    log.info("building dossier for roster %d, season=%d", roster_id, season)
    vet_assets = build_player_assets(seasons=[season], sleeper_players=sleeper_players)
    vet_map = {a.player_id: a for a in vet_assets}

    players = _build_player_rows(roster, vet_map, sleeper_players)
    total_dynasty_value = round(sum(p["dynasty_value"] for p in players), 1)

    ages = [p["age"] for p in players]
    avg_age = round(sum(ages) / len(ages), 1) if ages else 0.0
    starter_ages = [p["age"] for p in players if p["is_starter"]]
    avg_starter_age = round(sum(starter_ages) / len(starter_ages), 1) if starter_ages else avg_age

    import datetime

    current_year = datetime.date.today().year
    # Live seasons = any season appearing in traded_picks data (for current year+) plus the
    # current and next year as a floor (own picks that haven't been traded won't appear in data).
    data_seasons = {p.season for p in picks if int(p.season) >= current_year}
    data_seasons |= {str(current_year), str(current_year + 1)}
    live_seasons = sorted(data_seasons)
    draft_rounds = int(draft.settings.get("rounds", 4) or 4)
    live_rounds = list(range(1, draft_rounds + 1))

    # Slots this roster has traded away (their original pick, now held by others)
    traded_away_set = {
        (p.season, p.round) for p in picks if p.roster_id == roster_id and p.owner_id != roster_id
    }

    # Own original picks not traded away
    own_picks = sorted(
        [
            {"season": s, "round": r, "source": "own"}
            for s in live_seasons
            for r in live_rounds
            if (s, r) not in traded_away_set
        ],
        key=lambda x: (int(x["season"]), x["round"]),
    )

    # Foreign picks received from other teams
    foreign_picks = sorted(
        [
            {"season": p.season, "round": p.round, "source": "acquired"}
            for p in picks
            if p.owner_id == roster_id and p.roster_id != roster_id and p.season in live_seasons
        ],
        key=lambda x: (int(x["season"]), x["round"]),
    )

    picks_owned = own_picks + foreign_picks
    picks_traded_away = sorted(
        [{"season": s, "round": r} for s, r in traded_away_set],
        key=lambda x: (int(x["season"]), x["round"]),
    )

    archetype, archetype_rationale = _classify(
        len(roster.taxi or []), len(picks_traded_away), len(roster.players)
    )

    league_size = len(rosters)
    roster_totals: dict[int, float] = {}
    roster_pos: dict[int, dict[str, float]] = {}
    for r in rosters:
        if r.roster_id == roster_id:
            rows = players
        else:
            rows = _build_player_rows(r, vet_map, sleeper_players)
        roster_totals[r.roster_id] = sum(p["dynasty_value"] for p in rows)
        roster_pos[r.roster_id] = _position_totals(rows)

    value_order = sorted(rosters, key=lambda r: (-roster_totals[r.roster_id], r.roster_id))
    value_rank = next(i for i, r in enumerate(value_order, 1) if r.roster_id == roster_id)
    position_ranks = _position_ranks(roster_id, roster_pos, league_size)

    top_heavy_pct = (
        round(sum(p["dynasty_value"] for p in players[:3]) / total_dynasty_value * 100, 0)
        if total_dynasty_value
        else 0.0
    )

    return OwnerDossier(
        roster_id=roster_id,
        user_id=owner_id,
        display_name=display_name,
        avatar=avatar,
        archetype=archetype,
        archetype_rationale=archetype_rationale,
        total_dynasty_value=total_dynasty_value,
        player_count=len(players),
        avg_age=avg_age,
        avg_starter_age=avg_starter_age,
        players=players,
        age_buckets=_age_buckets(players),
        value_by_position=_value_by_position(players, total_dynasty_value),
        contention=_contention(players, total_dynasty_value),
        picks_owned=picks_owned,
        picks_traded_away=picks_traded_away,
        value_rank=value_rank,
        league_size=league_size,
        top_heavy_pct=top_heavy_pct,
        position_ranks=position_ranks,
    )
