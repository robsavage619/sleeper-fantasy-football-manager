"""CFBD college prospect loader — fetches usage/recruiting data and scores dynasty value."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

CFBD_BASE = "https://api.collegefootballdata.com"
_SUFFIX_RE = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", re.IGNORECASE)
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
    """Dynasty prospect enriched with CFBD usage and recruiting signals."""

    player_id: str | None
    name: str
    position: str
    college: str
    year: int
    age: float | None
    target_share: float
    yards_per_reception: float
    breakout_age: float | None
    recruiting_rank: int | None
    stars: int | None
    dynasty_prospect_score: float
    rationale: str


def _normalise_name(name: str) -> str:
    """Lowercase, strip suffixes, collapse whitespace."""
    return _SUFFIX_RE.sub("", name.lower().strip())


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
                target_share=0.0,
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
    return {_normalise_name(r.get("name", "")): r for r in recruits if r.get("name")}


def _fetch_advanced(year: int, client: httpx.Client) -> dict[str, dict]:
    """Fetch /stats/season/advanced and return name -> record map."""
    try:
        resp = client.get(
            f"{CFBD_BASE}/stats/season/advanced",
            params={"year": year, "seasonType": "regular"},
            headers=_cfbd_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        stats: list[dict] = resp.json()
    except httpx.HTTPError as exc:
        log.warning("CFBD /stats/season/advanced request failed: %s", exc)
        return {}
    return {_normalise_name(s.get("player", "")): s for s in stats if s.get("player")}


def _build_sleeper_index(players_dump: dict[str, dict]) -> dict[str, str]:
    """Return normalised-name -> player_id index from Sleeper dump."""
    index: dict[str, str] = {}
    for pid, p in players_dump.items():
        fn = p.get("full_name") or p.get("search_full_name")
        if fn:
            index[_normalise_name(fn)] = pid
    return index


def _score_wr_te(
    usage: dict,
    adv: dict,
    recruiting_rank: int | None,
) -> tuple[float, float, float, str]:
    """Return (target_share, ypr, raw_score, rationale) for WR/TE."""
    usage_data = usage.get("usage", {}) or {}
    target_share = float(usage_data.get("passingDowns", 0) or 0)
    # CFBD usage.passingDowns is a share proxy; prefer usage.passingShares if present
    rec_target_share = float(usage_data.get("overall", 0) or 0)
    if rec_target_share:
        target_share = rec_target_share

    receiving = adv.get("receiving", {}) or {}
    ypr = float(receiving.get("yardsPerReception", 0) or 0)

    rank_bonus = 15 if (recruiting_rank is not None and recruiting_rank < 50) else 0
    raw = target_share * 200 + ypr * 3 + rank_bonus

    rationale = f"{target_share:.1%} target share, {ypr:.1f} YPR"
    if rank_bonus:
        rationale += f", top-50 recruit (#{recruiting_rank})"
    return target_share, ypr, raw, rationale


def _score_rb(
    usage: dict,
    adv: dict,
    age: float | None,
    recruiting_rank: int | None,
) -> tuple[float, str]:
    """Return (raw_score, rationale) for RB."""
    rushing = adv.get("rushing", {}) or {}
    total_yards = float(rushing.get("rushingYards", 0) or 0)

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
    adv: dict,
    recruiting_rank: int | None,
) -> tuple[float, str]:
    """Return (raw_score, rationale) for QB."""
    passing = adv.get("passing", {}) or {}
    comp_pct = float(passing.get("completionPercentage", 0) or 0)
    ypa = float(passing.get("yardsPerAttempt", 0) or 0)

    rank_bonus = 10 if (recruiting_rank is not None and recruiting_rank < 100) else 0
    raw = comp_pct * 0.5 + ypa * 5 + rank_bonus

    rationale = f"{comp_pct:.1f}% comp, {ypa:.1f} YPA"
    if rank_bonus:
        rationale += f", top-100 recruit (#{recruiting_rank})"
    return raw, rationale


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
        advanced_map = _fetch_advanced(year, http_client)

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
        norm_name = _normalise_name(name)

        player_id = sleeper_index.get(norm_name)
        recruit = recruiting_map.get(norm_name, {})
        adv = advanced_map.get(norm_name, {})

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

        target_share = 0.0
        ypr = 0.0
        rationale = ""
        raw_score = 0.0

        if pos in ("WR", "TE"):
            target_share, ypr, raw_score, rationale = _score_wr_te(entry, adv, recruiting_rank)
        elif pos == "RB":
            raw_score, rationale = _score_rb(entry, adv, age, recruiting_rank)
        elif pos == "QB":
            raw_score, rationale = _score_qb(adv, recruiting_rank)

        profile = ProspectProfile(
            player_id=player_id,
            name=name,
            position=pos,
            college=college,
            year=year,
            age=age,
            target_share=target_share,
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
