"""Pydantic models for the Sleeper read API. Lenient by design — Sleeper adds fields freely."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class League(_Base):
    """A Sleeper league season. ``previous_league_id`` chains to prior seasons."""

    league_id: str
    name: str | None = None
    season: str | None = None
    status: str | None = None
    sport: str | None = None
    total_rosters: int | None = None
    previous_league_id: str | None = None
    draft_id: str | None = None
    roster_positions: list[str] = []
    settings: dict = {}
    scoring_settings: dict = {}


class Roster(_Base):
    """One team's roster within a league."""

    roster_id: int
    owner_id: str | None = None
    players: list[str] = []
    starters: list[str] = []
    reserve: list[str] | None = None
    taxi: list[str] | None = None
    settings: dict = {}


class User(_Base):
    """A league member."""

    user_id: str
    display_name: str | None = None
    avatar: str | None = None
    metadata: dict = {}


class TradedPick(_Base):
    """A future/current draft pick that has changed hands.

    ``roster_id`` is the pick's original owner; ``owner_id`` currently holds it.
    """

    season: str
    round: int
    roster_id: int
    owner_id: int
    previous_owner_id: int | None = None


class Draft(_Base):
    """A draft (annual rookie/offseason draft in dynasty)."""

    draft_id: str
    league_id: str | None = None
    type: str | None = None
    status: str | None = None
    season: str | None = None
    settings: dict = {}
    metadata: dict = {}


class DraftPick(_Base):
    """A single made pick within a draft."""

    round: int
    pick_no: int
    player_id: str | None = None
    roster_id: int | None = None
    picked_by: str | None = None
    metadata: dict | None = None


class NFLState(_Base):
    """Current NFL calendar state from Sleeper (week, season, season type)."""

    week: int | None = None
    season: str | None = None
    season_type: str | None = None
    display_week: int | None = None
    season_start_date: str | None = None
    previous_season: str | None = None
    league_season: str | None = None


class TrendingPlayer(_Base):
    """A trending add or drop from the waiver-wire trend endpoint."""

    player_id: str
    count: int


class BracketMatchup(_Base):
    """A single playoff-bracket matchup (winners or losers bracket)."""

    r: int  # round
    m: int  # matchup id
    t1: int | None = None  # roster_id team 1
    t2: int | None = None  # roster_id team 2
    w: int | None = None  # winner roster_id
    loser: int | None = Field(None, alias="l")  # Sleeper key is "l"; aliased to avoid E741
    # A placement game (e.g. championship, 3rd-place, 5th-place); winner gets
    # `place`, loser gets `place + 1`. None for a normal bracket-advancement match.
    place: int | None = Field(None, alias="p")
    t1_from: dict | None = None
    t2_from: dict | None = None
