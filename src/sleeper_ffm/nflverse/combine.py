"""NFL Combine athletic measurables for draft prospects (via nfl_data_py).

Combine data for a past class never changes, so the normalised per-player dict
is cached to ``data/nflverse/combine_{year}.json`` permanently after the first
pull. Athleticism is one of the few pre-draft signals that is free, objective,
and predictive — especially weight-adjusted speed (``speed_score``) for RB/WR.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from sleeper_ffm.config import NFLVERSE_DIR
from sleeper_ffm.names import normalize_name

log = logging.getLogger(__name__)

# Forty-yard thresholds for a coarse, position-aware athletic grade. These are
# scouting rules of thumb, not a percentile model — the grade is labelled
# "forty-based" everywhere it surfaces so it is not mistaken for a full RAS.
_FORTY_THRESHOLDS: dict[str, tuple[float, float, float]] = {
    # position group: (elite, good, average) — faster is better
    "SKILL": (4.40, 4.50, 4.60),  # WR / RB
    "BIG": (4.60, 4.75, 4.90),  # TE
}


def _height_to_inches(raw: Any) -> int | None:
    """Parse a combine height like ``"6-2"`` into total inches."""
    if raw is None:
        return None
    text = str(raw).strip()
    m = re.match(r"^(\d+)-(\d+)$", text)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2))
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _float_or_none(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(val) else val


def _int_or_none(raw: Any) -> int | None:
    val = _float_or_none(raw)
    return int(val) if val is not None else None


def _speed_score(forty: float | None, weight: float | None) -> float | None:
    """Weight-adjusted 40 time. ~100 is average NFL RB; 110+ is elite."""
    if not forty or not weight or forty <= 0:
        return None
    return round((weight * 200.0) / (forty**4), 1)


def _athletic_grade(position: str, forty: float | None) -> str | None:
    """Coarse forty-based athletic grade, position-aware. Honest about scope."""
    if not forty:
        return None
    group = "BIG" if position == "TE" else "SKILL"
    elite, good, average = _FORTY_THRESHOLDS[group]
    if forty <= elite:
        return "ELITE"
    if forty <= good:
        return "GOOD"
    if forty <= average:
        return "AVERAGE"
    return "BELOW"


def _cache_path(year: int):
    NFLVERSE_DIR.mkdir(parents=True, exist_ok=True)
    return NFLVERSE_DIR / f"combine_{year}.json"


def _build_index(year: int) -> dict[str, dict]:
    """Pull combine data for a class year and index it by normalised name."""
    import nfl_data_py as nfl

    df = nfl.import_combine_data([year])
    records: list[dict] = df.to_dict(orient="records")  # type: ignore[assignment]
    index: dict[str, dict] = {}
    for row in records:
        name = row.get("player_name")
        if not name:
            continue
        index[normalize_name(name)] = {
            "height_in": _height_to_inches(row.get("ht")),
            "weight": _int_or_none(row.get("wt")),
            "forty": _float_or_none(row.get("forty")),
            "vertical": _float_or_none(row.get("vertical")),
            "bench": _int_or_none(row.get("bench")),
            "broad_jump": _int_or_none(row.get("broad_jump")),
            "cone": _float_or_none(row.get("cone")),
            "shuttle": _float_or_none(row.get("shuttle")),
            "draft_round": _int_or_none(row.get("draft_round")),
            "draft_ovr": _int_or_none(row.get("draft_ovr")),
            "draft_team": row.get("draft_team") or None,
            "school": row.get("school") or None,
            "position": (row.get("pos") or "").upper() or None,
        }
    return index


def load_combine_index(year: int) -> dict[str, dict]:
    """Return ``{normalised_name: measurables}`` for a draft class year.

    Cached to disk permanently (combine results for a past year are immutable).
    Returns an empty dict if nfl_data_py is unavailable or the pull fails.
    """
    path = _cache_path(year)
    if path.exists():
        try:
            with open(path) as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("combine: cache read failed for %s: %s", year, exc)

    try:
        index = _build_index(year)
    except Exception as exc:
        log.warning("combine: pull failed for year=%s: %s", year, exc)
        return {}

    try:
        with open(path, "w") as fh:
            json.dump(index, fh)
    except OSError as exc:
        log.warning("combine: cache write failed for %s: %s", year, exc)
    return index


def combine_for(name: str, position: str, year: int) -> dict | None:
    """Return one prospect's combine measurables + derived athleticism, or None.

    Adds ``speed_score`` (weight-adjusted 40) and a coarse forty-based
    ``athletic_grade`` when the underlying numbers are present.
    """
    index = load_combine_index(year)
    record = index.get(normalize_name(name))
    if record is None:
        return None
    enriched = dict(record)
    enriched["speed_score"] = _speed_score(record.get("forty"), record.get("weight"))
    enriched["athletic_grade"] = _athletic_grade(position, record.get("forty"))
    return enriched
