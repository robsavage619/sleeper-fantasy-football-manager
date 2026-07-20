"""Read-only client for Sleeper's GraphQL API — projections, season outlooks, player news.

The REST v1 API (:mod:`sleeper_ffm.sleeper.client`) carries no projections at all, which
left the start/sit, matchup, and intel surfaces with no forward-looking input. This
endpoint has them: ``weekly_stats(category="proj")`` returns rotowire projections for
every player, and — the part that matters — projects *component volume* (``pass_att``,
``rush_att``, ``rec_tgt``, ``rec``), not just fantasy points. Volume feeds opportunity
models; a points total does not.

The response rows are keyed by Sleeper ``player_id`` and embed a ``player`` map with
name/position/team/injury status, so nothing here needs the name fold in
:mod:`sleeper_ffm.names` or a join against the 16MB player dump.

Stability
---------
This endpoint is undocumented and internal — the same schema serves DMs, wallets, and tax
forms. It exists to serve Sleeper's own app, not us, and can change without notice. Treat
every call as best-effort and degrade rather than hard-fail at the surfaces that use it.

Broken server-side filters
--------------------------
``positions`` and ``player_ids`` are accepted by the schema and then return **zero rows
with no error** (verified 2026-07-19 against ``weekly_stats`` and
``stats_for_players_in_week``). They are deliberately not exposed by this client: a filter
that silently returns nothing is a worse failure than no filter at all. Fetch the week and
filter client-side.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sleeper_ffm.config import SLEEPER_GRAPHQL
from sleeper_ffm.net import retry_call

log = logging.getLogger(__name__)

# Same retry policy as the REST client: rate-limit and upstream hiccups only.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

_STATS_FIELDS = "player_id team opponent category company week season stats player"

_WEEKLY_STATS = f"""
query WeeklyStats($season: String, $week: Int, $category: String, $season_type: String) {{
  weekly_stats(
    category: $category
    season: $season
    week: $week
    season_type: $season_type
    sport: "nfl"
    order_by: "pts_ppr"
  ) {{ {_STATS_FIELDS} }}
}}
"""

_SEASON_STATS = f"""
query SeasonStats($season: String, $category: String, $season_type: String) {{
  season_stats(
    category: $category
    season: $season
    season_type: $season_type
    sport: "nfl"
    order_by: "pts_ppr"
  ) {{ {_STATS_FIELDS} }}
}}
"""

_PLAYER_OUTLOOK = """
query Outlook($season: String, $player_id: String) {
  get_player_outlook(season: $season, player_id: $player_id, sport: "nfl") {
    player_id source published metadata
  }
}
"""

_PLAYER_NEWS = """
query News($player_id: String, $limit: Int) {
  get_player_news(player_id: $player_id, limit: $limit, sport: "nfl") {
    player_id source published metadata
  }
}
"""


class SleeperGraphQLError(RuntimeError):
    """The GraphQL endpoint returned an ``errors`` array or an unusable payload."""


class _TransientHTTPError(Exception):
    """A retryable HTTP status from Sleeper (rate-limit or upstream error)."""


class SleeperGraphQLClient:
    """Thin, read-only wrapper over Sleeper's GraphQL endpoint.

    Mirrors :class:`~sleeper_ffm.sleeper.client.SleeperClient` in shape: context manager,
    bounded retry on transient statuses, no auth, no writes.
    """

    def __init__(self, timeout: float = 20.0) -> None:  # noqa: D107
        # Projection payloads are ~9k rows / several MB, so the default timeout is
        # higher than the REST client's.
        self._http = httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._http.close()

    def __enter__(self) -> SleeperGraphQLClient:  # noqa: D105
        return self

    def __exit__(self, *exc: object) -> None:  # noqa: D105
        self.close()

    def _query(self, document: str, field: str, **variables: Any) -> list[dict]:
        """Execute ``document`` and return the row list under ``field``.

        Args:
            document: The GraphQL query document.
            field: Root field name to unwrap from ``data``.
            **variables: GraphQL variables bound into the document.

        Returns:
            The rows under ``data[field]``. A single-object field is wrapped in a list.

        Raises:
            SleeperGraphQLError: The response carried an ``errors`` array, or ``data``
                was missing entirely.
        """

        def _do() -> Any:
            resp = self._http.post(
                SLEEPER_GRAPHQL,
                json={"query": document, "variables": variables},
            )
            if resp.status_code in _RETRYABLE_STATUS:
                raise _TransientHTTPError(f"{resp.status_code} on {field}")
            resp.raise_for_status()
            return resp.json()

        payload = retry_call(
            _do,
            exceptions=(httpx.TransportError, _TransientHTTPError),
            label=f"sleeper graphql {field}",
        )

        if payload.get("errors"):
            raise SleeperGraphQLError(f"{field}: {payload['errors']}")
        if "data" not in payload:
            raise SleeperGraphQLError(f"{field}: response carried no data block")

        rows = payload["data"].get(field)
        if rows is None:
            return []
        if isinstance(rows, dict):
            return [rows]
        return rows

    def weekly_stats(
        self,
        season: str,
        week: int,
        category: str = "proj",
        season_type: str = "regular",
    ) -> list[dict]:
        """Fetch every player's stat or projection row for one week.

        Args:
            season: Season year as a string, e.g. ``"2026"``.
            week: NFL week number.
            category: ``"proj"`` for projections, ``"stat"`` for actuals.
            season_type: ``"regular"``, ``"post"``, or ``"pre"``.

        Returns:
            One row per player (~9k for ``proj``, ~2k for ``stat``). Empty means the week
            genuinely has no data upstream — callers should treat that as unavailable
            rather than as zero projections.
        """
        rows = self._query(
            _WEEKLY_STATS,
            "weekly_stats",
            season=season,
            week=week,
            category=category,
            season_type=season_type,
        )
        if not rows:
            log.warning(
                "sleeper graphql: weekly_stats returned 0 rows (season=%s week=%s category=%s)",
                season,
                week,
                category,
            )
        return rows

    def season_stats(
        self,
        season: str,
        category: str = "proj",
        season_type: str = "regular",
    ) -> list[dict]:
        """Fetch every player's full-season stat or projection row.

        Args:
            season: Season year as a string, e.g. ``"2026"``.
            category: ``"proj"`` for projections, ``"stat"`` for actuals.
            season_type: ``"regular"``, ``"post"``, or ``"pre"``.

        Returns:
            One row per player.
        """
        rows = self._query(
            _SEASON_STATS,
            "season_stats",
            season=season,
            category=category,
            season_type=season_type,
        )
        if not rows:
            log.warning(
                "sleeper graphql: season_stats returned 0 rows (season=%s category=%s)",
                season,
                category,
            )
        return rows

    def player_outlook(self, player_id: str, season: str) -> str | None:
        """Fetch the analyst season outlook blurb for one player.

        Args:
            player_id: Sleeper player id.
            season: Season year as a string.

        Returns:
            The outlook prose, or ``None`` when the player has no outlook on file.
        """
        rows = self._query(
            _PLAYER_OUTLOOK, "get_player_outlook", player_id=player_id, season=season
        )
        return _first_description(rows)

    def player_news(self, player_id: str, limit: int = 5) -> list[str]:
        """Fetch recent analyst news blurbs for one player, newest first.

        Args:
            player_id: Sleeper player id.
            limit: Maximum blurbs to return.

        Returns:
            Blurb texts, newest first. Empty when the player has no news on file.
        """
        rows = self._query(_PLAYER_NEWS, "get_player_news", player_id=player_id, limit=limit)
        rows = sorted(rows, key=lambda r: r.get("published") or 0, reverse=True)
        out = [text for row in rows if (text := _description(row))]
        return out


def _description(row: dict) -> str | None:
    metadata = row.get("metadata") or {}
    text = metadata.get("description") or metadata.get("analysis")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _first_description(rows: list[dict]) -> str | None:
    for row in rows:
        if text := _description(row):
            return text
    return None
