"""CFBD college prospect loader — fetches usage/recruiting data and scores dynasty value."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import CURRENT_LEAGUE_YEAR
from sleeper_ffm.names import normalize_name

log = logging.getLogger(__name__)

CFBD_BASE = "https://api.collegefootballdata.com"
_SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

# Sleeper keeps historical/retired players in the dump with years_exp 0, so years_exp
# alone lets stale entries (a coach, a player out of the league since 2020) onto a rookie
# board. The clean discriminator is an NFL team: a genuine incoming rookie is drafted or
# signed (team set), while the stale/misindexed rows carry team=None. This mirrors the
# rookie gate in model.valuation.build_rookie_assets. NB: search_rank is NOT usable here —
# Sleeper stamps real deep rookies (e.g. late UDFAs) with the same 9_999_999 sentinel as
# irrelevant players, so filtering on it would drop legitimate prospects.
_MAX_PROSPECT_AGE = 26.0

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

    # The incoming class still has years_exp 0; an earlier class has already
    # played a season, so allow one more year of experience for those.
    max_years_exp = 0 if year >= CURRENT_LEAGUE_YEAR else 1
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

        # Primary gate: a real incoming rookie is drafted or signed (has a team); the stale
        # and misindexed entries carry team=None. Mirrors build_rookie_assets.
        if not (player.get("team") or (player.get("metadata") or {}).get("team")):
            continue

        # Belt-and-suspenders: drop anything Sleeper flags inactive (retired coaches etc.).
        if player.get("active") is False:
            continue

        search_rank = player.get("search_rank")
        if search_rank is None:
            continue

        raw_age = player.get("age")
        age = float(raw_age) if raw_age else None
        # An incoming rookie is ~20-24; a present age well past that is a stale/misindexed row.
        if age is not None and age > _MAX_PROSPECT_AGE:
            continue
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


# A completed college season never changes, and the prospect board is polled
# repeatedly on draft day, so these three fetches are cached for an hour. Season
# stats alone is an 11-second request — uncached it dominated every page load.
# The cache key ignores the HTTP client, which is per-call and irrelevant to the
# result. Only raw payloads are cached: the profile objects built from them are
# mutated by the market re-rank, so caching those would corrupt a second call.
_CFBD_TTL = 3600.0


@ttl_cache(ttl=_CFBD_TTL, key=lambda year, client: ("usage", year))
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


@ttl_cache(ttl=_CFBD_TTL, key=lambda year, client: ("recruiting", year))
def _fetch_recruiting(year: int, client: httpx.Client) -> dict[str, dict]:
    """Fetch /recruiting/players for one high-school class, name -> record."""
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


# A player drafted in year N signed with a college several years earlier — three
# for a true junior, four or five with a redshirt or a fifth year. Querying the
# draft year (or the college season) returns a class this prospect cannot be in,
# which is why recruiting rank came back empty for every real prospect.
_RECRUIT_CLASS_LOOKBACK = (5, 4, 3)


def _fetch_recruiting_window(draft_year: int, client: httpx.Client) -> dict[str, dict]:
    """Merge the high-school classes a draft prospect could plausibly belong to.

    Args:
        draft_year: The NFL draft class year, e.g. 2026.
        client: Open HTTP client.

    Returns:
        ``{normalised_name: recruit_record}``. When a name appears in more than
        one class the better (numerically lower) ranking wins, so a transfer or
        reclassification does not downgrade a player.
    """
    merged: dict[str, dict] = {}
    for offset in _RECRUIT_CLASS_LOOKBACK:
        for name, record in _fetch_recruiting(draft_year - offset, client).items():
            existing = merged.get(name)
            if existing is None or _recruit_rank(record) < _recruit_rank(existing):
                merged[name] = record
    log.info(
        "CFBD recruiting: %d prospects across classes %s",
        len(merged),
        [draft_year - o for o in _RECRUIT_CLASS_LOOKBACK],
    )
    return merged


def _recruit_rank(record: dict) -> float:
    """Recruiting rank as a sortable number; unranked sorts last."""
    raw = record.get("ranking")
    return float(raw) if raw else float("inf")


@ttl_cache(ttl=_CFBD_TTL, key=lambda year, client: ("season_stats", year))
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


def _build_sleeper_index(players_dump: dict[str, dict]) -> dict[tuple[str, str], str]:
    """Return (normalised name, position) -> player_id for incoming rookies only.

    Matching a college roster against the whole Sleeper dump on name alone
    collides: a Pittsburgh running back named Caleb Williams inherits the Bears
    quarterback's id, and with it his market value, which floats a nobody to the
    top of a market-ranked board. Restricting to players with no NFL experience
    and keying on position removes both halves of that failure — an established
    professional is never the right match for a draft prospect.

    Args:
        players_dump: Sleeper's full player dump.

    Returns:
        Index over rookie-eligible players only.
    """
    index: dict[tuple[str, str], str] = {}
    for pid, p in players_dump.items():
        years_exp = p.get("years_exp")
        if years_exp is not None and years_exp > 0:
            continue
        name = p.get("full_name") or p.get("search_full_name")
        position = _POS_MAP.get((p.get("position") or "").upper())
        if name and position:
            index[(normalize_name(name), position)] = pid
    return index


def _usage_rate(usage: dict) -> float:
    """CFBD's share of team offensive plays the player was involved in.

    Args:
        usage: One ``/player/usage`` entry.

    Returns:
        ``usage.overall``, falling back to the passing-downs share.
    """
    usage_data = usage.get("usage", {}) or {}
    return float(usage_data.get("overall", 0) or usage_data.get("passingDowns", 0) or 0)


# Yards per reception is wildly unstable in small samples — one long catch reads
# as elite. Shrink it toward a typical college YPR by reception count, the same
# empirical-Bayes treatment model.forecast applies to per-game rates. K is the
# reception count at which the observation and the prior carry equal weight.
_YPR_PRIOR = 12.5
_YPR_SHRINK_K = 15.0


def _shrink_ypr(ypr: float, receptions: float) -> float:
    """Shrink a raw yards-per-reception toward the college-average prior.

    Args:
        ypr: Observed yards per reception.
        receptions: Receptions the observation rests on.

    Returns:
        The shrunk rate. A one-catch 75.0 lands near the prior; a full season's
        worth of catches barely moves.
    """
    if receptions <= 0:
        return 0.0
    return (receptions * ypr + _YPR_SHRINK_K * _YPR_PRIOR) / (receptions + _YPR_SHRINK_K)


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
    usage_rate = _usage_rate(usage)

    receiving = season_stats.get("receiving", {}) or {}
    ypr = float(receiving.get("YPR", 0) or 0)
    receptions = float(receiving.get("REC", 0) or 0)
    if not ypr and receiving.get("YDS") and receptions:
        ypr = receiving["YDS"] / receptions
    ypr = _shrink_ypr(ypr, receptions)

    rank_bonus = 15 if (recruiting_rank is not None and recruiting_rank < 50) else 0
    raw = usage_rate * 200 + ypr * 3 + rank_bonus

    rationale = f"{usage_rate:.1%} usage rate, {ypr:.1f} YPR on {int(receptions)} rec"
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

    # A draft class is scouted on the college season it just finished, so the
    # 2026 class means 2025 tape. Querying the draft year itself asks for a
    # season that has not been played, which returns nothing at all.
    college_season = year - 1

    with httpx.Client(timeout=20) as http_client:
        usage_list = _fetch_usage(college_season, http_client)
        recruiting_map = _fetch_recruiting_window(year, http_client)
        season_stats_map = _fetch_player_season_stats(college_season, http_client)

    if not usage_list:
        log.warning(
            "No CFBD usage data returned for college season %s (%s draft class); "
            "using Sleeper prospect fallback",
            college_season,
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

        player_id = sleeper_index.get((norm_name, pos))
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

        # Every position has a usage share; only the receiver branch used to keep
        # it, so backs and quarterbacks reported 0.0 on the board while CFBD had
        # the real figure all along.
        usage_rate = _usage_rate(entry)
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

    # Normalise within position, not across the whole board. The three scoring
    # functions are on incomparable scales — a back's raw score is rushing yards
    # over ten (~140 for a good season) while a receiver's tops out near 70 — so
    # one global maximum let backs crowd everyone else out. That is not a ranking
    # artefact to shrug at: it cut real first-round receivers before the caller
    # ever saw them. The score now reads "how good is this prospect for his
    # position", and cross-position ordering comes from the market re-rank in the
    # prospects router, which is format-correct for this league.
    best_by_position: dict[str, float] = {}
    for raw_score, profile in raw_profiles:
        current = best_by_position.get(profile.position, 0.0)
        best_by_position[profile.position] = max(current, raw_score)

    scored: list[ProspectProfile] = []
    for raw_score, profile in raw_profiles:
        position_best = best_by_position.get(profile.position) or 1.0
        profile.dynasty_prospect_score = round((raw_score / position_best) * 100, 1)
        scored.append(profile)

    # Interleave by within-position rank — the best back, then the best receiver,
    # then the best tight end, and so on — so ``top`` keeps the leaders at every
    # position instead of whichever position happens to cluster near its own
    # ceiling. Sorting on the normalised score alone still crowded the board
    # (128 receivers to 11 backs), which is the same failure in a new costume.
    by_position: dict[str, list[ProspectProfile]] = {}
    for profile in scored:
        by_position.setdefault(profile.position, []).append(profile)

    ranked: list[tuple[int, float, ProspectProfile]] = []
    for group in by_position.values():
        group.sort(key=lambda p: p.dynasty_prospect_score, reverse=True)
        for rank, profile in enumerate(group):
            ranked.append((rank, -profile.dynasty_prospect_score, profile))

    ranked.sort(key=lambda t: (t[0], t[1]))
    return [profile for _, _, profile in ranked[:top]]
