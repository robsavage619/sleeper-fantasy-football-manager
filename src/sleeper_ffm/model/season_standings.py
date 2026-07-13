"""Season-by-season standings and playoff history per current manager.

Walks the full dynasty chain (``previous_league_id``) and, for every past
season, reads each roster's win/loss/points from ``roster.settings`` and the
winners bracket to determine playoff appearances and championships. Records are
attributed to the *current* manager (by Sleeper ``user_id``) so a manager's
whole track record follows them across roster-id changes.

The in-progress current season (zero games played) is excluded from career
aggregates and the trend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from sleeper_ffm.config import LEAGUE_ID
from sleeper_ffm.sleeper.client import SleeperClient
from sleeper_ffm.sleeper.models import BracketMatchup

log = logging.getLogger(__name__)


@dataclass
class SeasonRecord:
    """One manager's result in one completed season."""

    season: str
    wins: int
    losses: int
    ties: int
    fpts: float
    reg_finish: int  # 1 = best regular-season record that season
    of_teams: int
    made_playoffs: bool
    champion: bool


@dataclass
class ManagerTrack:
    """A current manager's full historical track record."""

    roster_id: int
    seasons: list[SeasonRecord] = field(default_factory=list)  # chronological
    seasons_played: int = 0
    career_wins: int = 0
    career_losses: int = 0
    career_ties: int = 0
    win_pct: float = 0.0
    titles: int = 0
    playoff_appearances: int = 0
    best_finish: int | None = None


def _fpts(settings: dict) -> float:
    whole = settings.get("fpts") or 0
    dec = settings.get("fpts_decimal")
    return float(whole) + (float(dec) / 100 if dec is not None else 0.0)


def _is_final_match(m: BracketMatchup) -> bool:
    """A championship match is fed by bracket winners, not by losers (3rd-place)."""
    return all(not (feed and "l" in feed) for feed in (m.t1_from, m.t2_from))


def _champion_roster(bracket: list[BracketMatchup]) -> int | None:
    if not bracket:
        return None
    max_round = max(m.r for m in bracket)
    finals = [m for m in bracket if m.r == max_round and m.w is not None]
    champ = next((m for m in finals if _is_final_match(m)), finals[0] if finals else None)
    return champ.w if champ else None


def _playoff_rosters(bracket: list[BracketMatchup]) -> set[int]:
    rosters: set[int] = set()
    for m in bracket:
        if m.t1 is not None:
            rosters.add(m.t1)
        if m.t2 is not None:
            rosters.add(m.t2)
    return rosters


def build_season_standings(league_id: str = LEAGUE_ID) -> dict[int, ManagerTrack]:
    """Return ``{current_roster_id: ManagerTrack}`` across all completed seasons."""
    with SleeperClient(league_id=league_id) as client:
        seasons = client.league_history(league_id=league_id)
        if not seasons:
            return {}

        current_rosters = client.rosters(league_id=seasons[0].league_id)
        user_to_current: dict[str, int] = {}
        tracks: dict[int, ManagerTrack] = {}
        for r in current_rosters:
            uid = r.owner_id or ""
            user_to_current[uid] = r.roster_id
            tracks[r.roster_id] = ManagerTrack(roster_id=r.roster_id)

        for league in seasons:
            season_str = league.season or league.league_id
            try:
                rosters = client.rosters(league_id=league.league_id)
            except httpx.HTTPError as exc:
                log.warning("standings: roster fetch failed for %s: %s", season_str, exc)
                continue

            # Completed rosters only (skip the not-yet-started current season).
            played = [
                r
                for r in rosters
                if (
                    r.settings.get("wins", 0)
                    + r.settings.get("losses", 0)
                    + r.settings.get("ties", 0)
                )
                > 0
            ]
            if not played:
                continue

            ranked = sorted(
                played,
                key=lambda r: (r.settings.get("wins", 0), _fpts(r.settings)),
                reverse=True,
            )
            finish_by_roster = {r.roster_id: i + 1 for i, r in enumerate(ranked)}

            try:
                bracket = client.winners_bracket(league_id=league.league_id)
            except httpx.HTTPError:
                bracket = []
            champ_roster = _champion_roster(bracket)
            playoff_rosters = _playoff_rosters(bracket)

            for r in played:
                cur = user_to_current.get(r.owner_id or "")
                if cur is None:
                    continue
                rec = SeasonRecord(
                    season=season_str,
                    wins=int(r.settings.get("wins", 0)),
                    losses=int(r.settings.get("losses", 0)),
                    ties=int(r.settings.get("ties", 0)),
                    fpts=round(_fpts(r.settings), 1),
                    reg_finish=finish_by_roster.get(r.roster_id, len(ranked)),
                    of_teams=len(ranked),
                    made_playoffs=r.roster_id in playoff_rosters,
                    champion=r.roster_id == champ_roster,
                )
                tracks[cur].seasons.append(rec)

    for track in tracks.values():
        track.seasons.sort(key=lambda s: s.season)
        track.seasons_played = len(track.seasons)
        track.career_wins = sum(s.wins for s in track.seasons)
        track.career_losses = sum(s.losses for s in track.seasons)
        track.career_ties = sum(s.ties for s in track.seasons)
        games = track.career_wins + track.career_losses + track.career_ties
        track.win_pct = (
            round((track.career_wins + 0.5 * track.career_ties) / games, 3) if games else 0.0
        )
        track.titles = sum(1 for s in track.seasons if s.champion)
        track.playoff_appearances = sum(1 for s in track.seasons if s.made_playoffs)
        finishes = [s.reg_finish for s in track.seasons]
        track.best_finish = min(finishes) if finishes else None

    return tracks
