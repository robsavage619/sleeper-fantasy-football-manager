"""Forward-looking player projections, scored under this league's exact rules.

Every other engine in this codebase reasons backward from what already happened
(opponent-adjusted history, aging curves, market prices). This is the one forward input:
rotowire's weekly projections, served by Sleeper's GraphQL endpoint
(:mod:`sleeper_ffm.sleeper.graphql`).

Two deliberate choices about how that raw feed is used:

**League-exact points, not the provider's.** The provider ships ``pts_ppr``/``pts_half_ppr``
under generic settings. Those are wrong for this league — it has its own
``scoring_settings`` including threshold bonuses. So the projected *component* line
(``pass_yd``, ``rec``, ``rush_td``, ...) is already in Sleeper's stat vocabulary and gets
fed straight through :func:`sleeper_ffm.scoring.engine.score`, the same function that
scores real box scores. :attr:`PlayerProjection.provider_points` is retained beside it as
a cross-check, not as the number to use.

**Volume, not just points.** ``opportunity`` (projected carries + targets) and
``opportunity_share`` (that player's cut of his own team's projected touches) are the
signals a points total washes out. A back-up handcuff with a rising share and a low point
total is exactly the mispricing the dynasty surfaces exist to find.

Known distortion — threshold bonuses under-fire
-----------------------------------------------
:func:`~sleeper_ffm.scoring.engine.score` derives step bonuses from the stat line, so a
projection of 95.4 rush yards scores no 100-yard bonus even though the real distribution
clears 100 a meaningful share of the time. Points are therefore biased slightly low for
high-variance workhorses. This is a property of scoring an expected value with a step
function, not a bug in the scoring engine; correcting it needs a distribution, not a mean.
Documented rather than silently patched.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.scoring.engine import load_scoring, score
from sleeper_ffm.sleeper.graphql import SleeperGraphQLClient

log = logging.getLogger(__name__)

# Projections refresh on the provider's cadence (roughly daily out of season, more often
# in-season as news lands). An hour in-process is well inside that.
_PROJECTION_TTL = 3600.0

_SKILL: frozenset[str] = frozenset({"QB", "RB", "WR", "TE"})


class ProjectionsUnavailableError(RuntimeError):
    """No projection rows came back for the requested week.

    Raised rather than returning an empty mapping so a caller cannot mistake "the feed is
    down" for "every player is projected at zero" — the two look identical downstream and
    only one of them should reach a briefing.
    """


@dataclass(frozen=True)
class PlayerProjection:
    """One player's projected week, scored under this league's rules."""

    player_id: str
    name: str
    position: str
    team: str
    opponent: str
    league_points: float
    provider_points: float
    stats: dict[str, float] = field(default_factory=dict)
    injury_status: str | None = None

    @property
    def opportunity(self) -> float:
        """Projected touches: carries plus targets."""
        return self.stats.get("rush_att", 0.0) + self.stats.get("rec_tgt", 0.0)

    @property
    def points_delta(self) -> float:
        """League points minus provider points.

        Large positive values mean this league's settings reward the player's projected
        line more than generic PPR does — a systematic edge over anyone reading the
        provider's number straight.
        """
        return round(self.league_points - self.provider_points, 2)


@ttl_cache(ttl=_PROJECTION_TTL, key=lambda season, week, **_: (season, week))
def week_projections(season: str, week: int) -> dict[str, PlayerProjection]:
    """Fetch and score every player's projection for one week.

    Args:
        season: Season year as a string, e.g. ``"2026"``.
        week: NFL week number.

    Returns:
        Projections keyed by Sleeper ``player_id``, skill positions only.

    Raises:
        ProjectionsUnavailableError: The feed returned no usable rows.
    """
    with SleeperGraphQLClient() as client:
        rows = client.weekly_stats(season=season, week=week, category="proj")

    scoring = load_scoring()
    out: dict[str, PlayerProjection] = {}
    skipped = 0
    for row in rows:
        projection = _to_projection(row, scoring)
        if projection is None:
            skipped += 1
            continue
        out[projection.player_id] = projection

    if not out:
        raise ProjectionsUnavailableError(
            f"no usable projection rows for season={season} week={week} "
            f"({len(rows)} rows fetched, {skipped} unusable)"
        )
    log.info(
        "projections: %d skill players for %s week %s (%d rows skipped)",
        len(out),
        season,
        week,
        skipped,
    )
    return out


def opportunity_shares(projections: dict[str, PlayerProjection]) -> dict[str, float]:
    """Compute each player's share of his own team's projected touches.

    Args:
        projections: Output of :func:`week_projections`.

    Returns:
        ``player_id`` -> share in ``[0, 1]``. Players on a team with no projected touches
        are omitted rather than assigned a misleading zero.
    """
    team_totals: dict[str, float] = defaultdict(float)
    for projection in projections.values():
        if projection.team:
            team_totals[projection.team] += projection.opportunity

    shares: dict[str, float] = {}
    for player_id, projection in projections.items():
        total = team_totals.get(projection.team, 0.0)
        if total > 0:
            shares[player_id] = round(projection.opportunity / total, 4)
    return shares


def _to_projection(row: dict, scoring: dict[str, float]) -> PlayerProjection | None:
    """Convert one GraphQL row to a scored projection, or None if unusable."""
    player_id = row.get("player_id")
    player = row.get("player") or {}
    stats = row.get("stats") or {}
    if not player_id or not player or not stats:
        return None

    position = player.get("position") or ""
    if position not in _SKILL:
        return None

    numeric = {key: float(val) for key, val in stats.items() if isinstance(val, int | float)}
    name = " ".join(part for part in (player.get("first_name"), player.get("last_name")) if part)

    return PlayerProjection(
        player_id=str(player_id),
        name=name,
        position=position,
        team=row.get("team") or player.get("team") or "",
        opponent=row.get("opponent") or "",
        league_points=score(numeric, scoring),
        provider_points=round(float(numeric.get("pts_ppr", 0.0)), 2),
        stats=numeric,
        injury_status=player.get("injury_status"),
    )
