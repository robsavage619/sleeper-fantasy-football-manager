"""Read-only Sleeper API client. No auth, no writes — writes go through the Playwright layer.

Includes ``league_history`` which walks ``previous_league_id`` to reconstruct every season of a
dynasty — the substrate for owner profiles and trade-alpha scoring.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import CACHE_DIR, LEAGUE_ID, SLEEPER_BASE
from sleeper_ffm.net import retry_call
from sleeper_ffm.sleeper.models import (
    BracketMatchup,
    Draft,
    DraftPick,
    League,
    NFLState,
    Roster,
    TradedPick,
    TrendingPlayer,
    User,
)

log = logging.getLogger(__name__)

_PLAYERS_CACHE = CACHE_DIR / "players_nfl.json"
_PLAYERS_TTL_SECONDS = 24 * 3600

# Statuses worth a retry: rate-limit and upstream/gateway hiccups. Everything else is a
# real answer on the first try.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class _TransientHTTPError(Exception):
    """A retryable HTTP status from Sleeper (rate-limit or upstream error)."""


@ttl_cache(key=lambda: "players")
def _load_players_from_disk() -> dict[str, dict]:
    """Parse the ~16MB player dump once and hold it in-process (TTL-cached).

    Avoids re-parsing the dump on every ``players()`` call — the per-partner
    dossier loop would otherwise pay that parse cost N times per request.
    """
    return json.loads(_PLAYERS_CACHE.read_text())


class SleeperClient:
    """Thin, cached, read-only wrapper over the Sleeper public API."""

    def __init__(self, league_id: str = LEAGUE_ID, timeout: float = 15.0) -> None:  # noqa: D107
        self.league_id = league_id
        self._http = httpx.Client(base_url=SLEEPER_BASE, timeout=timeout)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._http.close()

    def __enter__(self) -> SleeperClient:  # noqa: D105
        return self

    def __exit__(self, *exc: object) -> None:  # noqa: D105
        self.close()

    def _get(self, path: str) -> Any:
        def _do() -> Any:
            resp = self._http.get(path)
            # Retry only transient statuses (rate-limit / upstream hiccup); a 404 or other
            # 4xx is a real answer and propagates on the first try.
            if resp.status_code in _RETRYABLE_STATUS:
                raise _TransientHTTPError(f"{resp.status_code} on {path}")
            resp.raise_for_status()
            return resp.json()

        return retry_call(
            _do,
            exceptions=(httpx.TransportError, _TransientHTTPError),
            label=f"sleeper {path}",
        )

    # --- league ---------------------------------------------------------------
    def league(self, league_id: str | None = None) -> League:
        """Fetch a league season."""
        lid = league_id or self.league_id
        return League.model_validate(self._get(f"/league/{lid}"))

    def rosters(self, league_id: str | None = None) -> list[Roster]:
        """Fetch all rosters in a league."""
        lid = league_id or self.league_id
        return [Roster.model_validate(r) for r in self._get(f"/league/{lid}/rosters")]

    def users(self, league_id: str | None = None) -> list[User]:
        """Fetch all league members."""
        lid = league_id or self.league_id
        return [User.model_validate(u) for u in self._get(f"/league/{lid}/users")]

    def traded_picks(self, league_id: str | None = None) -> list[TradedPick]:
        """Fetch all traded draft picks (current + future)."""
        lid = league_id or self.league_id
        return [TradedPick.model_validate(p) for p in self._get(f"/league/{lid}/traded_picks")]

    def transactions(self, week: int, league_id: str | None = None) -> list[dict]:
        """Fetch waiver/free-agent/trade transactions for a scoring week."""
        lid = league_id or self.league_id
        return self._get(f"/league/{lid}/transactions/{week}")

    def matchups(self, week: int, league_id: str | None = None) -> list[dict]:
        """Fetch matchups for a week (includes league-scored ``players_points``)."""
        lid = league_id or self.league_id
        return self._get(f"/league/{lid}/matchups/{week}")

    # --- drafts ---------------------------------------------------------------
    def draft(self, draft_id: str) -> Draft:
        """Fetch a draft by id."""
        return Draft.model_validate(self._get(f"/draft/{draft_id}"))

    def draft_picks(self, draft_id: str) -> list[DraftPick]:
        """Fetch all made picks in a draft."""
        return [DraftPick.model_validate(p) for p in self._get(f"/draft/{draft_id}/picks")]

    # --- players --------------------------------------------------------------
    def players(self, force: bool = False) -> dict[str, dict]:
        """Fetch the full NFL player dump, cached to disk (daily TTL).

        The dump is ~5 MB and refreshed once a day by Sleeper; we cache it locally.
        """
        if not force and _fresh(_PLAYERS_CACHE, _PLAYERS_TTL_SECONDS):
            return _load_players_from_disk()
        data = self._get("/players/nfl")
        _PLAYERS_CACHE.write_text(json.dumps(data))
        _load_players_from_disk.cache_clear()  # type: ignore[attr-defined]
        return data

    # --- nfl state ------------------------------------------------------------
    def state_nfl(self) -> NFLState:
        """Fetch the current NFL calendar state (week, season_type, etc.)."""
        return NFLState.model_validate(self._get("/state/nfl"))

    # --- trending players -----------------------------------------------------
    def trending(
        self,
        kind: str = "add",
        lookback_hours: int = 24,
        limit: int = 25,
    ) -> list[TrendingPlayer]:
        """Fetch trending add or drop players across all Sleeper leagues.

        Args:
            kind: ``"add"`` or ``"drop"``.
            lookback_hours: Rolling window in hours (default 24).
            limit: Number of results (default 25, max 200).

        Returns:
            Trending players ordered by count descending.
        """
        qs = f"lookback_hours={lookback_hours}&limit={limit}"
        data = self._get(f"/players/nfl/trending/{kind}?{qs}")
        return [TrendingPlayer.model_validate(p) for p in data]

    # --- playoff brackets -----------------------------------------------------
    def winners_bracket(self, league_id: str | None = None) -> list[BracketMatchup]:
        """Fetch the winners-bracket playoff matchups."""
        lid = league_id or self.league_id
        data = self._get(f"/league/{lid}/winners_bracket")
        return [BracketMatchup.model_validate(m) for m in data]

    def losers_bracket(self, league_id: str | None = None) -> list[BracketMatchup]:
        """Fetch the losers-bracket consolation matchups."""
        lid = league_id or self.league_id
        data = self._get(f"/league/{lid}/losers_bracket")
        return [BracketMatchup.model_validate(m) for m in data]

    # --- draft extras ---------------------------------------------------------
    def draft_traded_picks(self, draft_id: str) -> list[TradedPick]:
        """Fetch pick trades that occurred *within* a specific draft."""
        return [TradedPick.model_validate(p) for p in self._get(f"/draft/{draft_id}/traded_picks")]

    def league_drafts(self, league_id: str | None = None) -> list[Draft]:
        """Fetch all drafts associated with a league."""
        lid = league_id or self.league_id
        return [Draft.model_validate(d) for d in self._get(f"/league/{lid}/drafts")]

    # --- users ----------------------------------------------------------------
    def user(self, username_or_id: str) -> User:
        """Fetch a user by username or user_id."""
        return User.model_validate(self._get(f"/user/{username_or_id}"))

    def user_leagues(self, user_id: str, season: str) -> list[League]:
        """Fetch all leagues a user is in for a given season."""
        data = self._get(f"/user/{user_id}/leagues/nfl/{season}")
        return [League.model_validate(lg) for lg in (data or [])]

    def user_drafts(self, user_id: str, season: str) -> list[Draft]:
        """Fetch all drafts a user participated in for a given season."""
        data = self._get(f"/user/{user_id}/drafts/nfl/{season}")
        return [Draft.model_validate(d) for d in (data or [])]

    # --- dynasty history ------------------------------------------------------
    def league_history(self, league_id: str | None = None) -> list[League]:
        """Walk ``previous_league_id`` to return every season, newest first.

        Returns:
            Leagues ordered current -> oldest. The substrate for owner profiling.
        """
        lid = league_id or self.league_id
        chain: list[League] = []
        seen: set[str] = set()
        while lid and lid not in seen and lid != "0":
            seen.add(lid)
            lg = self.league(lid)
            chain.append(lg)
            lid = lg.previous_league_id
        return chain


def _fresh(path: Path, ttl: float) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < ttl
