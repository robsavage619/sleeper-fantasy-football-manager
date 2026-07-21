"""Projection-ranked free-agent board — the engine's best-measured skill, made live.

The arena battery found the engine's genuine edge is *waiver ranking*: its top blind pickup
targets returned 50-100% more than a random add (37-60% ranking capture,
``evals/waiver_arena.py``), even though it only ties strong managers on lineup-setting. But
the live product never surfaced that ranking — ``wire_watch`` ranks the wire by snap-share
delta (a leading role signal), and ``faab_market`` prices bids; neither answers "who is the
highest-*value* player still available." This does.

It ranks every unrostered skill player by his current-week projection — the same league-
scored rotowire number the start/sit engine trusts (``projections.week_projections``),
availability-adjusted the same way — and cross-references Sleeper's trending-add count so a
riser the herd has already noticed is distinguishable from a quiet value the projection
alone surfaces. It complements ``wire_watch`` rather than replacing it: snaps lead the box
score, projections price it.

Availability follows the start/sit rule: the provider already prices injuries (measured —
Out-class players project ~0.3), so only a hard-out is zeroed here, and Questionable players
are shown at their provider number with the designation flagged for the reader to judge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sleeper_ffm.config import CURRENT_LEAGUE_YEAR, LEAGUE_ID
from sleeper_ffm.model.news_feed import availability_factor
from sleeper_ffm.model.projections import PlayerProjection

log = logging.getLogger(__name__)

_SKILL: frozenset[str] = frozenset({"QB", "RB", "WR", "TE"})
# Below this projection a free agent is roster filler, not a recommendation.
_MIN_PTS = 4.0
_DEFAULT_TOP_N = 12


@dataclass
class FreeAgent:
    """One available player, ranked by projected value."""

    player_id: str
    name: str
    position: str
    team: str
    projected_pts: float  # league-scored, hard-out-zeroed
    injury_status: str | None = None
    trending_add_count: int = 0  # Sleeper league-wide adds in the trend window
    note: str = ""


@dataclass
class FreeAgentBoard:
    """Best available players by projected value, overall and per position."""

    season: int
    week: int
    overall: list[FreeAgent]
    by_position: dict[str, list[FreeAgent]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def rank_free_agents(
    projections: dict[str, PlayerProjection],
    rostered: set[str],
    trending: dict[str, int],
    top_n: int = _DEFAULT_TOP_N,
    min_pts: float = _MIN_PTS,
) -> FreeAgentBoard:
    """Rank unrostered skill players by projected value. Pure — no I/O.

    Args:
        projections: League-scored provider projections keyed by Sleeper ``player_id``.
        rostered: Player ids on any roster in the league (excluded from the board).
        trending: ``{player_id: add count}`` from Sleeper's trending-add endpoint.
        top_n: How many to keep overall and per position.
        min_pts: Drop free agents projecting below this — roster filler, not a pickup.

    Returns:
        A :class:`FreeAgentBoard`. ``season``/``week`` are 0 here (the caller stamps them).
    """
    candidates: list[FreeAgent] = []
    for pid, proj in projections.items():
        if pid in rostered or proj.position not in _SKILL:
            continue
        # The provider already prices injuries, so only a hard-out is zeroed; Questionable
        # is shown at the provider number with the flag left for the reader.
        if availability_factor(proj.injury_status) == 0.0:
            continue
        if proj.league_points < min_pts:
            continue
        candidates.append(
            FreeAgent(
                player_id=pid,
                name=proj.name,
                position=proj.position,
                team=proj.team,
                projected_pts=round(proj.league_points, 1),
                injury_status=proj.injury_status,
                trending_add_count=trending.get(pid, 0),
            )
        )

    candidates.sort(key=lambda fa: fa.projected_pts, reverse=True)
    by_position: dict[str, list[FreeAgent]] = {}
    for pos in sorted(_SKILL):
        by_position[pos] = [fa for fa in candidates if fa.position == pos][:top_n]
    return FreeAgentBoard(
        season=0,
        week=0,
        overall=candidates[:top_n],
        by_position=by_position,
    )


def build_free_agent_board(
    season: int | None = None,
    week: int | None = None,
    top_n: int = _DEFAULT_TOP_N,
    league_id: str = LEAGUE_ID,
) -> FreeAgentBoard:
    """Assemble the live free-agent board for a league and week.

    Args:
        season: Season to project. Defaults to the current league year.
        week: NFL week to project. Defaults to the current week from Sleeper's NFL state
            (1 in the off-season).
        top_n: Board size overall and per position.
        league_id: League whose rosters define who is unavailable.

    Returns:
        A :class:`FreeAgentBoard`. Degrades to an empty board with a warning if projections
        are unavailable (the undocumented provider endpoint can go dark).
    """
    from sleeper_ffm.model.projections import ProjectionsUnavailableError, week_projections
    from sleeper_ffm.sleeper.client import SleeperClient

    season = season or CURRENT_LEAGUE_YEAR
    warnings: list[str] = []

    with SleeperClient() as client:
        rostered: set[str] = set()
        for roster in client.rosters(league_id):
            rostered.update(roster.players or [])
            rostered.update(roster.taxi or [])
            rostered.update(roster.reserve or [])
        if week is None:
            try:
                week = int(client.state_nfl().week or 0) or 1
            except Exception:  # off-season / state hiccup → project week 1
                week = 1
        trending = {t.player_id: t.count for t in client.trending("add", limit=200)}

    try:
        projections = week_projections(str(season), week)
    except ProjectionsUnavailableError as exc:
        log.warning("free_agents: projections unavailable (%s)", exc)
        return FreeAgentBoard(
            season=season,
            week=week,
            overall=[],
            warnings=[f"Projections unavailable for {season} wk {week}; board empty."],
        )

    board = rank_free_agents(projections, rostered, trending, top_n=top_n)
    board.season = season
    board.week = week
    board.warnings = warnings
    return board
