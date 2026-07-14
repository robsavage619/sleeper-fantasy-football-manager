"""Standings-based rookie-draft order projection.

Sleeper's own ``draft_order`` field on a draft object stays ``null`` until the
commissioner (or auto-randomize) explicitly locks it in — but this league's
rookie draft order actually follows a fixed convention: reverse order of the
prior season's full final standings. Full standings combine the playoff
bracket's own placement games (1st via the championship, 3rd via the 3rd-place
game, 5th via the 5th-place game, ...) for playoff qualifiers, then non-playoff
teams filling the remaining places in reverse order of regular-season finish
(the best non-qualifier gets the best remaining place).

Verified empirically: applying this exact rule to the 2024 season reproduces
the real, Sleeper-confirmed 2025 draft order on all 10 slots. That is strong
evidence, not proof for all time — a commissioner could still override it, and
it is surfaced everywhere as a *projection*, never as an official confirmed
slot, until Sleeper's own ``draft_order`` is actually set.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.sleeper.client import SleeperClient
from sleeper_ffm.sleeper.models import BracketMatchup, Roster

log = logging.getLogger(__name__)


def _fpts(settings: dict) -> float:
    whole = settings.get("fpts") or 0
    dec = settings.get("fpts_decimal")
    return float(whole) + (float(dec) / 100 if dec is not None else 0.0)


def _final_placement(played_rosters: list[Roster], bracket: list[BracketMatchup]) -> dict[int, int]:
    """Full 1..N final placement for one completed season, keyed by roster_id."""
    placement: dict[int, int] = {}
    for m in bracket:
        if m.place is None:
            continue
        if m.w is not None:
            placement[m.w] = m.place
        if m.loser is not None:
            placement[m.loser] = m.place + 1

    # Anyone who appears in the bracket at all is a playoff qualifier, even if
    # they didn't land in a placement game (e.g. an odd-sized consolation bracket).
    playoff_rosters = set(placement)
    for m in bracket:
        for rid in (m.t1, m.t2):
            if rid is not None:
                playoff_rosters.add(rid)

    non_playoff = [r for r in played_rosters if r.roster_id not in playoff_rosters]
    ranked_non_playoff = sorted(
        non_playoff,
        key=lambda r: (r.settings.get("wins", 0), _fpts(r.settings)),
        reverse=True,
    )
    next_place = (max(placement.values()) if placement else 0) + 1
    for r in ranked_non_playoff:
        if r.roster_id not in placement:
            placement[r.roster_id] = next_place
            next_place += 1

    return placement


@dataclass
class DraftOrderProjection:
    """A projected (not Sleeper-confirmed) rookie-draft slot order."""

    slot_to_roster_id: dict[int, int]  # 1-indexed slot -> natural roster owner
    source_season: str  # the completed season this was derived from


def project_draft_order(league_id: str) -> DraftOrderProjection | None:
    """Project this season's rookie-draft slot order from last season's final standings.

    Returns None if there's no completed prior season to project from (e.g. a
    brand-new league) or its bracket/roster data is unavailable.
    """
    with SleeperClient(league_id=league_id) as client:
        seasons = client.league_history(league_id=league_id)
        if len(seasons) < 2:
            return None
        prior = seasons[1]  # seasons[0] is the current, in-progress league

        try:
            rosters = client.rosters(league_id=prior.league_id)
        except Exception as exc:
            log.warning("draft_order projection: roster fetch failed for %s: %s", prior.season, exc)
            return None

        played = [
            r
            for r in rosters
            if (r.settings.get("wins", 0) + r.settings.get("losses", 0) + r.settings.get("ties", 0))
            > 0
        ]
        if not played:
            return None

        try:
            bracket = client.winners_bracket(league_id=prior.league_id)
        except Exception as exc:
            log.warning(
                "draft_order projection: bracket fetch failed for %s: %s", prior.season, exc
            )
            bracket = []

    placement = _final_placement(played, bracket)
    if not placement:
        return None

    n = len(placement)
    slot_to_roster_id = {n + 1 - place: rid for rid, place in placement.items()}
    return DraftOrderProjection(
        slot_to_roster_id=slot_to_roster_id,
        source_season=prior.season or "",
    )
