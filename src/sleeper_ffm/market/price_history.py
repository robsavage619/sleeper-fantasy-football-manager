"""FantasyCalc price-history store — momentum and mean-reversion signals.

Every Tuesday admin refresh archives a dated FantasyCalc snapshot
(``data/market/fantasycalc_YYYYMMDD.json``, see ``api/routers/admin.py``
``_refresh_fantasycalc``) but nothing reads them back as a series. This assembles
those archives into a per-player time series and derives simple, honest signals:

    * **Momentum** — % change from the earliest to the latest archived snapshot.
    * **Mean-reversion z-score** — how far today's price sits from its own trailing
      average, in standard deviations. A large negative z-score after an injury is
      the "has the price actually bottomed" signal the plan calls for.

With only a handful of weekly snapshots collected so far, signals return ``None``
with a note rather than fabricating a number from thin data — this compounds in
value as more Tuesdays pass and should not be force-computed from noise.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sleeper_ffm.config import DATA_DIR

log = logging.getLogger(__name__)

_MARKET_DIR = DATA_DIR / "market"
_ARCHIVE_RE = re.compile(r"^fantasycalc_(\d{8})\.json$")

# Minimum snapshots before a momentum/z-score signal is trusted, not just noise.
_MIN_SNAPSHOTS_FOR_SIGNAL = 4


@dataclass
class PricePoint:
    """One archived FantasyCalc value for a player."""

    as_of: str  # YYYY-MM-DD
    value: float


@dataclass
class PlayerMeta:
    """Static player identity, pulled from the most recent snapshot that has it."""

    name: str
    position: str
    team: str


@dataclass
class PlayerPriceHistory:
    """Momentum + mean-reversion signal for one player."""

    sleeper_id: str
    meta: PlayerMeta | None
    points: list[PricePoint]
    momentum_pct: float | None
    zscore: float | None
    note: str = ""


@dataclass
class PriceHistoryIndex:
    """The full assembled price-history store."""

    series: dict[str, list[PricePoint]]
    meta: dict[str, PlayerMeta]
    snapshot_dates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _archive_files() -> list[tuple[date, Path]]:
    if not _MARKET_DIR.exists():
        return []
    out: list[tuple[date, Path]] = []
    for p in _MARKET_DIR.glob("fantasycalc_*.json"):
        m = _ARCHIVE_RE.match(p.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        out.append((d, p))
    return sorted(out)


def load_price_history() -> PriceHistoryIndex:
    """Load every archived FantasyCalc snapshot into a per-player time series.

    Returns:
        A :class:`PriceHistoryIndex` with each player's points sorted oldest to
        newest. Snapshot files that fail to parse are skipped with a warning;
        entries without a Sleeper ID are skipped (matches ``fantasycalc.fetch``).
    """
    series: dict[str, list[PricePoint]] = {}
    meta: dict[str, PlayerMeta] = {}
    dates: list[str] = []
    warnings: list[str] = []
    for d, path in _archive_files():
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("price_history: %s unreadable: %s", path.name, exc)
            warnings.append(f"snapshot {path.name} unreadable: {exc}")
            continue
        dates.append(d.isoformat())
        for entry in raw:
            player = entry.get("player") or {}
            sid = player.get("sleeperId") or player.get("sleeperPlayerId")
            value = entry.get("value")
            if not sid or value is None:
                continue
            sid = str(sid)
            series.setdefault(sid, []).append(PricePoint(as_of=d.isoformat(), value=float(value)))
            name = player.get("name")
            if name:
                meta[sid] = PlayerMeta(
                    name=name,
                    position=player.get("position") or "?",
                    team=player.get("maybeTeam") or "FA",
                )
    return PriceHistoryIndex(series=series, meta=meta, snapshot_dates=dates, warnings=warnings)


def player_price_trend(
    sleeper_id: str, index: PriceHistoryIndex | None = None
) -> PlayerPriceHistory:
    """Momentum + mean-reversion signal for one player from the archived series.

    Args:
        sleeper_id: Sleeper player ID.
        index: Pre-loaded index (avoids re-reading disk per player); defaults to a
            fresh :func:`load_price_history` call.

    Returns:
        A :class:`PlayerPriceHistory`. ``momentum_pct``/``zscore`` are ``None`` with
        an explanatory note when there isn't enough history yet.
    """
    index = index if index is not None else load_price_history()
    points = index.series.get(sleeper_id, [])
    meta = index.meta.get(sleeper_id)

    if len(points) < 2:
        note = "No price history yet." if not points else "Only one snapshot so far."
        return PlayerPriceHistory(
            sleeper_id=sleeper_id,
            meta=meta,
            points=points,
            momentum_pct=None,
            zscore=None,
            note=note,
        )

    values = [p.value for p in points]
    momentum = round((values[-1] - values[0]) / values[0] * 100, 2) if values[0] else None

    if len(points) < _MIN_SNAPSHOTS_FOR_SIGNAL:
        return PlayerPriceHistory(
            sleeper_id=sleeper_id,
            meta=meta,
            points=points,
            momentum_pct=momentum,
            zscore=None,
            note=(
                f"Only {len(points)} snapshots so far; z-score needs {_MIN_SNAPSHOTS_FOR_SIGNAL}+."
            ),
        )

    trailing = values[:-1]
    mean = statistics.mean(trailing)
    stdev = statistics.pstdev(trailing)
    z = round((values[-1] - mean) / stdev, 2) if stdev else 0.0
    return PlayerPriceHistory(
        sleeper_id=sleeper_id, meta=meta, points=points, momentum_pct=momentum, zscore=z
    )


def top_movers(
    direction: str = "up",
    limit: int = 25,
    min_snapshots: int = 2,
    index: PriceHistoryIndex | None = None,
) -> list[PlayerPriceHistory]:
    """Biggest momentum movers across every player with enough history.

    Args:
        direction: ``"up"`` for risers, ``"down"`` for fallers.
        limit: Max players to return.
        min_snapshots: Minimum archived snapshots required to qualify (default 2,
            since momentum only needs two points — unlike the z-score's higher bar).
        index: Pre-loaded index; defaults to a fresh :func:`load_price_history` call.

    Returns:
        Players sorted by ``momentum_pct``, largest magnitude in the requested
        direction first. Empty list if fewer than ``min_snapshots`` archives exist.
    """
    index = index if index is not None else load_price_history()
    trends = [
        player_price_trend(sid, index)
        for sid, pts in index.series.items()
        if len(pts) >= min_snapshots
    ]
    movers = [t for t in trends if t.momentum_pct is not None]
    reverse = direction == "up"
    movers.sort(key=lambda t: t.momentum_pct or 0.0, reverse=reverse)
    if direction == "down":
        movers = [t for t in movers if (t.momentum_pct or 0.0) < 0]
    else:
        movers = [t for t in movers if (t.momentum_pct or 0.0) > 0]
    return movers[:limit]
