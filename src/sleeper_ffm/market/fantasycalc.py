"""FantasyCalc dynasty player values.

Fetches the current dynasty trade market via the FantasyCalc public API and
caches the result locally for 24 hours. Values are raw FantasyCalc units
(roughly 0-10000 scale, higher = more valuable).

Public API::

    values = fetch()  # {sleeper_id: fc_value, ...}
"""

from __future__ import annotations

import json
import logging
import re as _re
import time
from pathlib import Path
from urllib.request import urlopen

from sleeper_ffm.config import DATA_DIR

log = logging.getLogger(__name__)

_FC_URL = "https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&ppr=1"
_CACHE_DIR = DATA_DIR / "market"
_CACHE_TTL_SECONDS = 86_400  # 24 hours


def _cache_path() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "fantasycalc_latest.json"


def _is_stale(path: Path) -> bool:
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > _CACHE_TTL_SECONDS


def _fetch_fresh() -> list[dict]:
    log.info("fantasycalc: fetching %s", _FC_URL)
    with urlopen(_FC_URL, timeout=15) as resp:
        raw = json.loads(resp.read().decode())
    log.info("fantasycalc: %d entries received", len(raw))
    return raw


def _load_raw() -> list[dict]:
    """Return raw FantasyCalc response, using cache when fresh."""
    path = _cache_path()
    if not _is_stale(path):
        log.debug("fantasycalc: cache hit (%s)", path)
        with open(path) as fh:
            return json.load(fh)
    data = _fetch_fresh()
    with open(path, "w") as fh:
        json.dump(data, fh)
    return data


def fetch() -> dict[str, float]:
    """Return {sleeper_id: fc_value} for all players FantasyCalc knows about.

    FantasyCalc values are on a roughly 0-10000 scale. Players without a
    Sleeper ID mapping are silently skipped.

    Returns:
        Dict mapping Sleeper player ID strings to FantasyCalc dynasty value.
    """
    try:
        raw = _load_raw()
    except Exception as exc:
        log.warning("fantasycalc: fetch failed: %s", exc)
        return {}

    result: dict[str, float] = {}
    for entry in raw:
        player = entry.get("player") or {}
        sleeper_id = player.get("sleeperId") or player.get("sleeperPlayerId")
        value = entry.get("value")
        if sleeper_id and value is not None:
            result[str(sleeper_id)] = float(value)

    log.debug("fantasycalc: %d players with sleeper IDs", len(result))
    return result


def _height_inches(raw: object) -> int | None:
    """Parse a FantasyCalc height (inches as a string, e.g. '72') to an int."""
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def fetch_full() -> dict[str, dict]:
    """Return the full FantasyCalc consensus record for every player, by Sleeper ID.

    Unlike :func:`fetch` (raw value only), this surfaces the whole market
    picture the dynasty community actually trades on: overall/positional rank,
    tier, 30-day value trend, ADP, roster% and trade frequency (liquidity),
    market volatility (moving std dev → how divided the market is), the
    redraft-vs-dynasty split (ascending-youth vs win-now), NFL draft capital,
    and bio. Every field is optional; missing values are ``None``.

    Returns:
        ``{sleeper_id: record}`` where ``record`` carries ``value``,
        ``overall_rank``, ``position_rank``, ``tier``, ``trend_30day``,
        ``adp``, ``roster_pct``, ``trade_frequency``, ``volatility``,
        ``volatility_pct``, ``redraft_value``, ``redraft_dynasty_diff``,
        ``draft_year``, ``draft_round``, ``draft_pick``, ``height``,
        ``weight``, ``college``, ``team``, ``age``, ``years_exp``.
        Empty dict if the fetch fails.
    """
    try:
        raw = _load_raw()
    except Exception as exc:
        log.warning("fantasycalc: fetch_full failed: %s", exc)
        return {}

    result: dict[str, dict] = {}
    for entry in raw:
        player = entry.get("player") or {}
        sleeper_id = player.get("sleeperId") or player.get("sleeperPlayerId")
        if not sleeper_id:
            continue
        draft = player.get("maybeDraftInfo") or {}
        result[str(sleeper_id)] = {
            "value": entry.get("value"),
            "overall_rank": entry.get("overallRank"),
            "position_rank": entry.get("positionRank"),
            "tier": entry.get("maybeTier"),
            "trend_30day": entry.get("trend30Day"),
            "adp": entry.get("maybeAdp"),
            "roster_pct": entry.get("maybeRosterPercent"),
            "trade_frequency": entry.get("maybeTradeFrequency"),
            "volatility": entry.get("maybeMovingStandardDeviation"),
            "volatility_pct": entry.get("maybeMovingStandardDeviationPerc"),
            "redraft_value": entry.get("redraftValue"),
            "redraft_dynasty_diff": entry.get("redraftDynastyValueDifference"),
            "draft_year": draft.get("year"),
            "draft_round": draft.get("round"),
            "draft_pick": draft.get("pick"),
            "height": _height_inches(player.get("maybeHeight")),
            "weight": player.get("maybeWeight"),
            "college": player.get("maybeCollege"),
            "team": player.get("maybeTeam"),
            "age": player.get("maybeAge"),
            "years_exp": player.get("maybeYoe"),
        }

    log.debug("fantasycalc: %d full records with sleeper IDs", len(result))
    return result

_PICK_ROUND_RE = _re.compile(r"\b(\d+)(?:st|nd|rd|th)\b", _re.IGNORECASE)
_PICK_YEAR_RE = _re.compile(r"\b(20\d{2})\b")


def fetch_picks() -> dict[tuple[str, int], float]:
    """Return {(season_str, round_int): fc_value} for picks in the FantasyCalc dataset.

    FC returns picks as player entries with position == "PICK" and names like
    "2026 1st", "2027 2nd Round Pick", "2025 Early 1st", etc. When multiple
    entries exist for the same (season, round) — e.g. early/mid/late variants —
    their values are averaged.

    Returns:
        Dict mapping (season, round) to average FC value for that pick.
        Empty dict if no pick data is available or fetch fails.
    """
    try:
        raw = _load_raw()
    except Exception as exc:
        log.warning("fantasycalc: fetch_picks failed: %s", exc)
        return {}

    buckets: dict[tuple[str, int], list[float]] = {}
    for entry in raw:
        player = entry.get("player") or {}
        pos = (player.get("position") or "").upper()
        name = player.get("name") or ""
        value = entry.get("value")
        if value is None:
            continue
        if (
            pos != "PICK"
            and "pick" not in name.lower()
            and not any(w in name.lower() for w in ("1st", "2nd", "3rd", "4th", "round"))
        ):
            continue

        year_m = _PICK_YEAR_RE.search(name)
        round_m = _PICK_ROUND_RE.search(name)
        if not year_m or not round_m:
            continue
        season = year_m.group(1)
        round_ = int(round_m.group(1))
        if round_ not in (1, 2, 3, 4):
            continue

        key = (season, round_)
        buckets.setdefault(key, []).append(float(value))

    result = {k: sum(vals) / len(vals) for k, vals in buckets.items()}
    log.debug("fantasycalc: %d pick entries parsed", len(result))
    return result
