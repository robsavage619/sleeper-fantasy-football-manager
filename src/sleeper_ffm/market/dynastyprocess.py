"""DynastyProcess fallback dynasty rankings.

Fetches the community-curated DynastyProcess values CSV from GitHub when
FantasyCalc is unavailable. Values are mapped from search-rank to a 0-10000
scale so the blend layer sees a consistent unit regardless of source.

Public API::

    values = fetch()  # {sleeper_id: dp_value, ...}
"""

from __future__ import annotations

import csv
import io
import logging
import time
from pathlib import Path
from urllib.request import urlopen

from sleeper_ffm.config import DATA_DIR

log = logging.getLogger(__name__)

# DynastyProcess values CSV — weekly update cadence.
_DP_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
)
_CACHE_DIR = DATA_DIR / "market"
_CACHE_TTL_SECONDS = 7 * 86_400  # 1 week (DP updates ~weekly)

# DP provides a raw 0-10000 "value" column; we don't need to rescale.
_MAX_DP_VALUE = 10_000.0


def _cache_path() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "dynastyprocess_latest.csv"


def _is_stale(path: Path) -> bool:
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > _CACHE_TTL_SECONDS


def _fetch_fresh() -> str:
    log.info("dynastyprocess: fetching %s", _DP_URL)
    with urlopen(_DP_URL, timeout=15) as resp:
        text = resp.read().decode("utf-8")
    log.info("dynastyprocess: %d bytes received", len(text))
    return text


def _load_csv_text() -> str:
    path = _cache_path()
    if not _is_stale(path):
        log.debug("dynastyprocess: cache hit (%s)", path)
        return path.read_text(encoding="utf-8")
    text = _fetch_fresh()
    path.write_text(text, encoding="utf-8")
    return text


def fetch() -> dict[str, float]:
    """Return {sleeper_id: dp_value} for players in the DynastyProcess dataset.

    DynastyProcess uses a 0-10000 value scale (same order of magnitude as
    FantasyCalc). Players without a ``sleeper_id`` column are skipped.

    Returns:
        Dict mapping Sleeper player ID strings to DynastyProcess dynasty value.
    """
    try:
        text = _load_csv_text()
    except Exception as exc:
        log.warning("dynastyprocess: fetch failed: %s", exc)
        return {}

    result: dict[str, float] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        sleeper_id = (row.get("sleeper_id") or "").strip()
        raw_value = (row.get("value") or "").strip()
        if not sleeper_id or not raw_value:
            continue
        try:
            result[sleeper_id] = float(raw_value)
        except ValueError:
            pass

    log.debug("dynastyprocess: %d players with sleeper IDs", len(result))
    return result
