"""CFBD college prospect loader — fetches usage/recruiting data and scores dynasty value."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from sleeper_ffm.names import normalize_name

log = logging.getLogger(__name__)

CFBD_BASE = "https://api.collegefootballdata.com"
_SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

# CFBD position labels → normalised
_POS_MAP = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "HB": "RB",
    "FB": "RB",
}


@dataclass
class ProspectProfile:
    """Dynasty prospect enriched with CFBD usage and recruiting signals.

    ``usage_rate`` is CFBD's ``usage.overall`` — the share of the team's
    offensive plays this player was involved in. CFBD does not track pass
    targets, so this is a play-involvement proxy, not literal target share.
    """

    player_id: str | None
    name: str
    position: str
    college: str
    year: int
    age: float | None
    usage_rate: float
    yards_per_reception: float
    breakout_age: float | None
    recruiting_rank: int | None
    stars: int | None
    dynasty_prospect_score: float
    rationale: str


def _cfbd_headers() -> dict[str, str]:
    key = os.environ.get("CFBD_API_KEY", "")
    if not key:
        raise ValueError(
            "CFBD_API_KEY environment variable is not set. "
            "Get a free key at https://collegefootballdata.com/key and "
            "export CFBD_API_KEY=<your-key>."
        )
    return {"Authorization": f"Bearer {key}"}


def _fallback_sleeper_prospects(year: int, top: int) -> list[ProspectProfile]:
    """Build a prospect board from Sleeper rookie dynasty rankings."""
    from sleeper_ffm.sleeper.client import SleeperClient

    max_years_exp = 0 if year >= 2026 else 1
    with SleeperClient() as client:
        players_dump = client.players()

    profiles: list[ProspectProfile] = []
    for pid, player in players_dump.items():
        pos = _POS_MAP.get((player.get("position") or "").upper())
        if pos not in _SKILL_POSITIONS:
            continue

        years_exp = player.get("years_exp")
        if years_exp is None or years_exp > max_years_exp:
            continue

        search_rank = player.get("search_rank")
        if search_rank is None:
            continue

        raw_age = player.get("age")
        age = float(raw_age) if raw_age else None
        metadata = player.get("metadata") or {}
        college = player.get("college") or metadata.get("college") or "—"
        name = player.get("full_name") or player.get("search_full_name") or f"Player {pid}"
        score = round(max(1.0, 100.0 - min(float(search_rank), 250.0) / 2.5), 1)
        profiles.append(
            ProspectProfile(
                player_id=pid,
                name=name,
                position=pos,
                college=college,
                year=year,
                age=age,
                usage_rate=0.0,
                yards_per_reception=0.0,
                breakout_age=None,
                recruiting_rank=None,
                stars=None,
                dynasty_prospect_score=score,
                rationale=(
                    f"Sleeper dynasty fallback: search rank #{search_rank}, {years_exp} years exp"
                ),
            )
        )

    profiles.sort(key=lambda p: p.dynasty_prospect_score, reverse=True)
    return profiles[:top]


def _fetch_usage(year: int, client: httpx.Client) -> list[dict]:
    """Fetch /player/usage for the given year."""
    try:
        resp = client.get(
            f"{CFBD_BASE}/player/usage",
            params={"year": year, "seasonType": "regular"},
            headers=_cfbd_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        log.warning("CFBD /player/usage request failed: %s", exc)
        return []


def _fetch_recruiting(year: int, client: httpx.Client) -> dict[str, dict]:
    """Fetch /recruiting/players and return name -> record map."""
    try:
        resp = client.get(
            f"{CFBD_BASE}/recruiting/players",
            params={"year": year, "classification": "HighSchool"},
            headers=_cfbd_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        recruits: list[dict] = resp.json()
    except httpx.HTTPError as exc:
        log.warning("CFBD /recruiting/players request failed: %s", exc)
        return {}
    return {normalize_name(r.get("name", "")): r for r in recruits if r.get("name")}


def _fetch_player_season_stats(
    year: int, client: httpx.Client
) -> dict[str, dict[str, dict[str, float]]]:
    """Fetch /stats/player/season and pivot long-format rows into a per-player stat tree.

    CFBD returns one row per (player, category, statType), e.g.
    ``{"player": "X", "category": "receiving", "statType": "YPR", "stat": "13.2"}``.
    This pivots to ``{normalised_name: {category: {statType: float}}}``.

    Note: an earlier version of this loader called ``/stats/season/advanced``,
    which is TEAM-level only (no per-player field at all) and silently
    returned nothing useful. This is the real player-level source, verified
    against CFBD's own API server source.
    """
    try:
        resp = client.get(
            f"{CFBD_BASE}/stats/player/season",
            params={"year": year, "seasonType": "regular"},
            headers=_cfbd_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        rows: list[dict] = resp.json()
    except httpx.HTTPError as exc:
        log.warning("CFBD /stats/player/season request failed: %s", exc)
        return {}

    pivoted: dict[str, dict[str, dict[str, float]]] = {}
    for row in rows:
        name = row.get("player")
        category = row.get("category")
        stat_type = row.get("statType")
        raw_stat = row.get("stat")
        if not name or not category or not stat_type or raw_stat is None:
            continue
        try:
            value = float(raw_stat)
        except (TypeError, ValueError):
            continue
        key = normalize_name(name)
        pivoted.setdefault(key, {}).setdefault(category, {})[stat_type] = value
    return pivoted


def _build_sleeper_index(players_dump: dict[str, dict]) -> dict[str, str]:
    """Return normalised-name -> player_id index from Sleeper dump."""
    index: dict[str, str] = {}
    for pid, p in players_dump.items():
        fn = p.get("full_name") or p.get("search_full_name")
        if fn:
            index[normalize_name(fn)] = pid
    return index


def _score_wr_te(
    usage: dict,
    season_stats: dict,
    recruiting_rank: int | None,
) -> tuple[float, float, float, str]:
    """Return (usage_rate, ypr, raw_score, rationale) for WR/TE.

    ``usage_rate`` is CFBD's ``usage.overall`` — share of team offensive plays
    this player was involved in. CFBD does not track targets, so this is a
    play-involvement proxy, not literal target share.
    """
    usage_data = usage.get("usage", {}) or {}
    usage_rate = float(usage_data.get("overall", 0) or usage_data.get("passingDowns", 0) or 0)

    receiving = season_stats.get("receiving", {}) or {}
    ypr = float(receiving.get("YPR", 0) or 0)
    if not ypr and receiving.get("YDS") and receiving.get("REC"):
        ypr = receiving["YDS"] / receiving["REC"]

    rank_bonus = 15 if (recruiting_rank is not None and recruiting_rank < 50) else 0
    raw = usage_rate * 200 + ypr * 3 + rank_bonus

    rationale = f"{usage_rate:.1%} usage rate, {ypr:.1f} YPR"
    if rank_bonus:
        rationale += f", top-50 recruit (#{recruiting_rank})"
    return usage_rate, ypr, raw, rationale


def _score_rb(
    usage: dict,
    season_stats: dict,
    age: float | None,
    recruiting_rank: int | None,
) -> tuple[float, str]:
    """Return (raw_score, rationale) for RB."""
    rushing = season_stats.get("rushing", {}) or {}
    total_yards = float(rushing.get("YDS", 0) or 0)

    age_bonus = 10 if (age is not None and age < 22) else 0
    rank_bonus = 15 if (recruiting_rank is not None and recruiting_rank < 50) else 0
    raw = total_yards / 10 + age_bonus + rank_bonus

    rationale = f"{int(total_yards)} rush yds"
    if age_bonus:
        rationale += f", age {age:.1f}" if age else ""
    if rank_bonus:
        rationale += f", top-50 recruit (#{recruiting_rank})"
    return raw, rationale


def _score_qb(
    season_stats: dict,
    recruiting_rank: int | None,
) -> tuple[float, str]:
    """Return (raw_score, rationale) for QB."""
    passing = season_stats.get("passing", {}) or {}
    comp_pct = float(passing.get("PCT", 0) or 0)
    ypa = float(passing.get("YPA", 0) or 0)
    if not ypa and passing.get("YDS") and passing.get("ATT"):
        ypa = passing["YDS"] / passing["ATT"]

    rank_bonus = 10 if (recruiting_rank is not None and recruiting_rank < 100) else 0
    raw = comp_pct * 0.5 + ypa * 5 + rank_bonus

    rationale = f"{comp_pct:.1f}% comp, {ypa:.1f} YPA"
    if rank_bonus:
        rationale += f", top-100 recruit (#{recruiting_rank})"
    return raw, rationale


def fetch_bio(name: str) -> dict | None:
    """Fetch height/weight/hometown bio via CFBD /player/search.

    Returns None when CFBD_API_KEY is not configured or no match is found.
    """
    try:
        headers = _cfbd_headers()
    except ValueError:
        return None

    with httpx.Client(timeout=20) as client:
        try:
            resp = client.get(
                f"{CFBD_BASE}/player/search",
                params={"searchTerm": name},
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            matches: list[dict] = resp.json()
        except httpx.HTTPError as exc:
            log.warning("CFBD /player/search request failed: %s", exc)
            return None

    norm_name = normalize_name(name)
    match = next(
        (m for m in matches if normalize_name(m.get("name", "")) == norm_name),
        matches[0] if matches else None,
    )
    if match is None:
        return None
    return {
        "height": match.get("height"),
        "weight": match.get("weight"),
        "hometown": match.get("hometown"),
        "jersey": match.get("jersey"),
    }


def _extract_stat_row(pos: str, usage_entry: dict, season_stats: dict) -> dict:
    """Return a compact per-season stat snapshot keyed for the given position."""
    if pos in ("WR", "TE"):
        usage_data = usage_entry.get("usage", {}) or {}
        usage_rate = float(usage_data.get("overall", 0) or usage_data.get("passingDowns", 0) or 0)
        receiving = season_stats.get("receiving", {}) or {}
        ypr = float(receiving.get("YPR", 0) or 0)
        if not ypr and receiving.get("YDS") and receiving.get("REC"):
            ypr = receiving["YDS"] / receiving["REC"]
        return {
            "usage_rate": round(usage_rate, 3),
            "yards_per_reception": round(ypr, 1),
        }
    if pos == "RB":
        rushing = season_stats.get("rushing", {}) or {}
        return {"rushing_yards": int(rushing.get("YDS", 0) or 0)}
    if pos == "QB":
        passing = season_stats.get("passing", {}) or {}
        ypa = float(passing.get("YPA", 0) or 0)
        if not ypa and passing.get("YDS") and passing.get("ATT"):
            ypa = passing["YDS"] / passing["ATT"]
        return {
            "completion_pct": round(float(passing.get("PCT", 0) or 0), 1),
            "yards_per_attempt": round(ypa, 1),
        }
    return {}


def fetch_season_history(
    name: str,
    position: str,
    draft_year: int,
    lookback: int = 2,
) -> list[dict]:
    """Fetch up to `lookback` prior seasons plus the draft year for a named player.

    Returns an empty list when CFBD_API_KEY is not configured or no matching
    season data is found (name-matched against each year's full usage list,
    since CFBD does not expose a single-player lookup).
    """
    try:
        _cfbd_headers()
    except ValueError:
        return []

    norm_name = normalize_name(name)
    history: list[dict] = []
    with httpx.Client(timeout=20) as client:
        for offset in range(lookback, -1, -1):
            yr = draft_year - offset
            usage_list = _fetch_usage(yr, client)
            usage_entry = next(
                (
                    u
                    for u in usage_list
                    if normalize_name(u.get("player") or u.get("name") or "") == norm_name
                ),
                None,
            )
            if usage_entry is None:
                continue
            season_stats_map = _fetch_player_season_stats(yr, client)
            player_stats = season_stats_map.get(norm_name, {})
            stat_row = _extract_stat_row(position, usage_entry, player_stats)
            if stat_row:
                history.append({"season": yr, **stat_row})
    return history


def load_prospects(year: int = 2025, top: int = 200) -> list[ProspectProfile]:
    """Fetch CFBD data and return scored dynasty prospect profiles.

    Falls back to Sleeper rookie dynasty rankings when the CFBD feed is not
    configured or does not return usage data.

    Args:
        year: Draft class year (2025 or 2026).
        top: Number of top prospects to return.

    Returns:
        Prospects sorted by dynasty_prospect_score descending.
    """
    try:
        _cfbd_headers()
    except ValueError as exc:
        log.warning("CFBD key unavailable, using Sleeper prospect fallback: %s", exc)
        return _fallback_sleeper_prospects(year=year, top=top)

    from sleeper_ffm.sleeper.client import SleeperClient

    with httpx.Client(timeout=20) as http_client:
        usage_list = _fetch_usage(year, http_client)
        recruiting_map = _fetch_recruiting(year, http_client)
        season_stats_map = _fetch_player_season_stats(year, http_client)

    if not usage_list:
        log.warning(
            "No CFBD usage data returned for year=%s; using Sleeper prospect fallback",
            year,
        )
        return _fallback_sleeper_prospects(year=year, top=top)

    # Sleeper player index for name matching
    try:
        with SleeperClient() as sc:
            players_dump = sc.players()
        sleeper_index = _build_sleeper_index(players_dump)
    except Exception as exc:
        log.warning("Could not load Sleeper player dump for matching: %s", exc)
        sleeper_index = {}

    raw_profiles: list[tuple[float, ProspectProfile]] = []

    for entry in usage_list:
        raw_pos = (entry.get("position") or "").upper()
        pos = _POS_MAP.get(raw_pos)
        if pos not in _SKILL_POSITIONS:
            continue

        name = entry.get("player") or entry.get("name") or ""
        if not name:
            continue

        college = entry.get("team") or entry.get("school") or ""
        norm_name = normalize_name(name)

        player_id = sleeper_index.get(norm_name)
        recruit = recruiting_map.get(norm_name, {})
        player_season_stats = season_stats_map.get(norm_name, {})

        recruiting_rank: int | None = None
        stars: int | None = None
        if recruit:
            r = recruit.get("ranking") or recruit.get("ranking")
            recruiting_rank = int(r) if r else None
            s = recruit.get("stars")
            stars = int(s) if s else None

        age: float | None = None
        if player_id and player_id in (players_dump if sleeper_index else {}):
            raw_age = players_dump.get(player_id, {}).get("age")
            age = float(raw_age) if raw_age else None

        usage_rate = 0.0
        ypr = 0.0
        rationale = ""
        raw_score = 0.0

        if pos in ("WR", "TE"):
            usage_rate, ypr, raw_score, rationale = _score_wr_te(
                entry, player_season_stats, recruiting_rank
            )
        elif pos == "RB":
            raw_score, rationale = _score_rb(entry, player_season_stats, age, recruiting_rank)
        elif pos == "QB":
            raw_score, rationale = _score_qb(player_season_stats, recruiting_rank)

        profile = ProspectProfile(
            player_id=player_id,
            name=name,
            position=pos,
            college=college,
            year=year,
            age=age,
            usage_rate=usage_rate,
            yards_per_reception=ypr,
            breakout_age=None,  # requires multi-year data; reserved for future pass
            recruiting_rank=recruiting_rank,
            stars=stars,
            dynasty_prospect_score=0.0,  # normalised below
            rationale=rationale,
        )
        raw_profiles.append((raw_score, profile))

    if not raw_profiles:
        return []

    max_score = max(s for s, _ in raw_profiles) or 1.0
    results: list[ProspectProfile] = []
    for raw_score, profile in raw_profiles:
        profile.dynasty_prospect_score = round((raw_score / max_score) * 100, 1)
        results.append(profile)

    results.sort(key=lambda p: p.dynasty_prospect_score, reverse=True)
    return results[:top]
