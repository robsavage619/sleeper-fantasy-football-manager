"""In-house GM (owner) sabermetrics: luck, lineup efficiency, FAAB, and a trade ledger.

Slice A (production-grade):
    - Luck index: actual wins minus all-play expected wins, plus a close-game (<5 pt) record.
    - Lineup efficiency: actual starter points / optimal legal lineup (shared, position-aware
      logic in ``owner_skill.optimal_lineup_points`` — the FIXED implementation).
    - FAAB remaining: league waiver budget minus each roster's ``waiver_budget_used``.

Slice B (labelled, carries evidence_count):
    - Trade ledger P&L: retrospective FPAR of assets acquired vs surrendered per trade. Picks are
      valued via ``dynasty.value_pick``; players via current FPAR. Production-based, UNCALIBRATED.

Metric math lives in pure helpers (unit-tested against a frozen fixture); ``build_gm_metrics`` is
a thin live-data orchestrator that never fabricates a value to cover missing data.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from sleeper_ffm.config import DATA_DIR, DEFAULT_VALUE_SEASON, LEAGUE_ID
from sleeper_ffm.model.owner_skill import (
    _find_skill_sample,
    _roster_positions,
    optimal_lineup_points,
)
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

_CLOSE_MARGIN: float = 5.0
_PICK_RE = re.compile(r"R(\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested directly)
# ---------------------------------------------------------------------------


def all_play_wins(week_scores: list[float], my_points: float) -> int:
    """Number of teams a score of ``my_points`` strictly beats in one week's slate."""
    return sum(1 for s in week_scores if s < my_points)


def all_play_record(weeks: list[list[dict]]) -> dict[int, tuple[int, int]]:
    """Accumulate all-play (wins, games) per roster across weeks.

    Args:
        weeks: One entry per scoring week; each is a list of ``{"roster_id", "points"}`` dicts.

    Returns:
        ``{roster_id: (all_play_wins, all_play_games)}``.
    """
    acc: dict[int, list[int]] = {}
    for week in weeks:
        scores = [float(e["points"]) for e in week]
        n = len(scores)
        for entry in week:
            rid = int(entry["roster_id"])
            wins = all_play_wins(scores, float(entry["points"]))
            tally = acc.setdefault(rid, [0, 0])
            tally[0] += wins
            tally[1] += n - 1
    return {rid: (w, g) for rid, (w, g) in acc.items()}


def close_game_record(
    weeks: list[list[dict]], margin: float = _CLOSE_MARGIN
) -> dict[int, dict[str, int]]:
    """Head-to-head record in games decided by less than ``margin`` points.

    Args:
        weeks: Per-week lists of ``{"roster_id", "points", "matchup_id"}`` dicts.
        margin: Point margin under which a game counts as close.

    Returns:
        ``{roster_id: {"close_wins": w, "close_losses": l, "one_score_games": n}}``.
    """
    rec: dict[int, dict[str, int]] = {}

    def _bump(rid: int, key: str) -> None:
        rec.setdefault(rid, {"close_wins": 0, "close_losses": 0, "one_score_games": 0})[key] += 1

    for week in weeks:
        pairs: dict[int, list[dict]] = {}
        for entry in week:
            mid = entry.get("matchup_id")
            if mid is None:
                continue
            pairs.setdefault(int(mid), []).append(entry)
        for members in pairs.values():
            if len(members) != 2:
                continue
            a, b = members
            diff = float(a["points"]) - float(b["points"])
            if abs(diff) >= margin:
                continue
            rid_a, rid_b = int(a["roster_id"]), int(b["roster_id"])
            _bump(rid_a, "one_score_games")
            _bump(rid_b, "one_score_games")
            if diff > 0:
                _bump(rid_a, "close_wins")
                _bump(rid_b, "close_losses")
            elif diff < 0:
                _bump(rid_b, "close_wins")
                _bump(rid_a, "close_losses")
    return rec


def luck_index(actual_wins: float, allplay_pct: float, actual_games: float) -> float:
    """Actual wins minus all-play expected wins; positive = luckier than performance warranted."""
    return round(actual_wins - allplay_pct * actual_games, 3)


def trade_ledger_pnl(trades: list[dict], value_by_asset: dict[str, float]) -> dict[str, float]:
    """Net retrospective value of assets acquired vs surrendered across a set of trades.

    Args:
        trades: List of ``{"received": [asset_key, ...], "sent": [asset_key, ...]}`` dicts.
        value_by_asset: ``{asset_key: value}`` (players in FPAR, picks in pick-value units).

    Returns:
        ``{"value_in", "value_out", "net", "trade_count", "resolved", "unresolved"}``.
    """
    value_in = 0.0
    value_out = 0.0
    resolved = 0
    unresolved = 0
    for trade in trades:
        for asset in trade.get("received", []):
            if asset in value_by_asset:
                value_in += value_by_asset[asset]
                resolved += 1
            else:
                unresolved += 1
        for asset in trade.get("sent", []):
            if asset in value_by_asset:
                value_out += value_by_asset[asset]
                resolved += 1
            else:
                unresolved += 1
    return {
        "value_in": round(value_in, 2),
        "value_out": round(value_out, 2),
        "net": round(value_in - value_out, 2),
        "trade_count": len(trades),
        "resolved": resolved,
        "unresolved": unresolved,
    }


# ---------------------------------------------------------------------------
# Response model + orchestrator
# ---------------------------------------------------------------------------


@dataclass
class OwnerGMMetrics:
    """GM sabermetric suite for one owner, matching the owners/sabermetrics endpoint contract."""

    roster_id: int
    user_id: str
    display_name: str | None
    skill_season: str
    luck: dict
    lineup_efficiency: dict
    faab: dict
    trade_ledger: dict  # Slice B — UNCALIBRATED
    data_quality: str
    warnings: list[str] = field(default_factory=list)


def _waiver_budget() -> int:
    try:
        with (DATA_DIR / "league_settings.json").open() as fh:
            return int(json.load(fh).get("settings", {}).get("waiver_budget", 100) or 100)
    except (OSError, ValueError, KeyError) as exc:
        log.warning("could not read waiver_budget (%s); defaulting to 100", exc)
        return 100


def _normalize_weeks(weekly_matchups: list[list[dict]]) -> list[list[dict]]:
    """Flatten Sleeper matchup payloads to ``[{"roster_id","points","matchup_id"}, ...]`` weeks."""
    weeks: list[list[dict]] = []
    for week_data in weekly_matchups:
        entries: list[dict] = []
        for entry in week_data:
            rid = entry.get("roster_id")
            if rid is None:
                continue
            entries.append(
                {
                    "roster_id": int(rid),
                    "points": float(entry.get("points") or 0.0),
                    "matchup_id": entry.get("matchup_id"),
                }
            )
        if entries:
            weeks.append(entries)
    return weeks


def _lineup_efficiency(
    weekly_matchups: list[list[dict]],
    skill_roster_owner: dict[int, int],
    player_positions: dict[str, str],
    roster_positions: list[str],
) -> dict[int, tuple[float, int]]:
    """Return ``{roster_id: (mean_efficiency, weeks)}`` using the position-aware optimal lineup."""
    acc: dict[int, list[float]] = {}
    for week_data in weekly_matchups:
        for entry in week_data:
            rid = entry.get("roster_id")
            if rid is None or int(rid) not in skill_roster_owner:
                continue
            starters = entry.get("starters") or []
            players_points = entry.get("players_points") or {}
            if not starters or not players_points:
                continue
            optimal = optimal_lineup_points(players_points, player_positions, roster_positions)
            if optimal <= 0:
                continue
            actual = sum(players_points.get(pid, 0.0) for pid in starters)
            acc.setdefault(int(rid), []).append(min(actual / optimal, 1.0))
    return {rid: (sum(v) / len(v), len(v)) for rid, v in acc.items() if v}


def build_gm_metrics() -> list[OwnerGMMetrics]:
    """Compute the GM sabermetric suite for every current roster in the league.

    Returns:
        One :class:`OwnerGMMetrics` per roster, sorted by luck index descending. Metrics that
        cannot be computed are reported as None with a warning, never fabricated.
    """
    with SleeperClient() as client:
        rosters = client.rosters(LEAGUE_ID)
        users = client.users(LEAGUE_ID)
        sleeper_players = client.players()
        skill_season, skill_rosters, weekly_matchups = _find_skill_sample(client)

    user_by_id = {u.user_id: u for u in users}
    roster_owner = {r.roster_id: (r.owner_id or "") for r in rosters}
    player_positions = {pid: str(p.get("position") or "") for pid, p in sleeper_players.items()}
    roster_positions = _roster_positions()
    budget = _waiver_budget()

    skill_roster_owner: dict[int, int] = {r.roster_id: r.roster_id for r in skill_rosters}
    owner_standings: dict[int, tuple[float, float]] = {}
    for r in skill_rosters:
        wins = float(r.settings.get("wins", 0) or 0)
        losses = int(r.settings.get("losses", 0) or 0)
        ties = int(r.settings.get("ties", 0) or 0)
        owner_standings[r.roster_id] = (wins + ties * 0.5, wins + losses + ties * 0.5)

    weeks = _normalize_weeks(weekly_matchups)
    ap = all_play_record(weeks)
    close = close_game_record(weeks)
    eff = _lineup_efficiency(
        weekly_matchups, skill_roster_owner, player_positions, roster_positions
    )

    value_by_asset, ledger_warn = _asset_values(sleeper_players)
    trades_by_roster = _trades_by_current_roster()

    results: list[OwnerGMMetrics] = []
    for r in rosters:
        rid = r.roster_id
        uid = roster_owner.get(rid, "")
        user = user_by_id.get(uid)
        display_name = getattr(user, "display_name", None) if user else None
        warnings: list[str] = []

        ap_wins, ap_games = ap.get(rid, (0, 0))
        ap_pct = ap_wins / ap_games if ap_games > 0 else 0.0
        actual_wins, actual_games = owner_standings.get(rid, (0.0, 0.0))
        luck = {
            "skill_season": skill_season,
            "actual_wins": round(actual_wins, 1),
            "allplay_pct": round(ap_pct, 4),
            "expected_wins": round(ap_pct * actual_games, 2),
            "luck_index": luck_index(actual_wins, ap_pct, actual_games),
            **close.get(rid, {"close_wins": 0, "close_losses": 0, "one_score_games": 0}),
        }
        if not weeks:
            warnings.append("No matchup data; luck metrics are zeroed.")

        eff_val = eff.get(rid)
        lineup = {
            "efficiency": round(eff_val[0], 4) if eff_val else None,
            "weeks": eff_val[1] if eff_val else 0,
            "missing": eff_val is None,
        }
        if eff_val is None:
            warnings.append("Lineup data missing for this owner; efficiency not computed.")

        used = r.settings.get("waiver_budget_used")
        faab = {
            "budget": budget,
            "used": int(used) if used is not None else None,
            "remaining": budget - int(used) if used is not None else None,
        }
        if used is None:
            warnings.append("waiver_budget_used missing from roster settings.")

        roster_trades = trades_by_roster.get(rid, [])
        ledger: dict = dict(trade_ledger_pnl(roster_trades, value_by_asset))
        ledger["label"] = (
            "UNCALIBRATED — production-based retrospective; players valued at current FPAR, "
            "picks at model pick value; historical trade partners resolved by name."
        )
        ledger["evidence_count"] = ledger["trade_count"]
        if ledger_warn:
            warnings.append(ledger_warn)

        results.append(
            OwnerGMMetrics(
                roster_id=rid,
                user_id=uid,
                display_name=display_name,
                skill_season=skill_season,
                luck=luck,
                lineup_efficiency=lineup,
                faab=faab,
                trade_ledger=ledger,
                data_quality="ok" if weeks else "no_matchups",
                warnings=warnings,
            )
        )

    results.sort(key=lambda x: x.luck["luck_index"], reverse=True)
    return results


def _asset_values(sleeper_players: dict[str, dict]) -> tuple[dict[str, float], str | None]:
    """Build a ``{asset_key: value}`` map keyed by player name and "<season> R<round>" pick label.

    Player keys are full names (history stores names, not ids). Pick keys match the history
    format ``"2026 R1"``. Returns the map plus an optional warning string.
    """
    from sleeper_ffm.model.dynasty import PickAsset, value_pick
    from sleeper_ffm.model.valuation import build_player_assets

    values: dict[str, float] = {}
    warn: str | None = None
    try:
        for asset in build_player_assets(
            seasons=[DEFAULT_VALUE_SEASON], sleeper_players=sleeper_players
        ):
            values[asset.name] = asset.current_fpar
    except Exception as exc:
        log.warning("trade ledger: player valuation failed (%s)", exc)
        warn = "Player FPAR unavailable; trade ledger resolves picks only."

    # Pre-value any pick label appearing in trades is done lazily at lookup; here we seed common
    # season/round combinations so exact-string keys resolve.
    for season in range(DEFAULT_VALUE_SEASON, DEFAULT_VALUE_SEASON + 4):
        for rnd in (1, 2, 3, 4):
            key = f"{season} R{rnd}"
            values[key] = value_pick(
                PickAsset(season=str(season), round=rnd, original_owner_id=0, current_owner_id=0)
            )
    return values, warn


def _trades_by_current_roster() -> dict[int, list[dict]]:
    """Collect each current roster's trades as ``{"received", "sent"}`` asset-key lists.

    Uses ``build_league_history`` (which already attributes historical trades to the current
    roster and stores assets as display names / "<season> R<round>" pick labels).
    """
    from sleeper_ffm.model.owner_history import build_league_history

    trades_by_roster: dict[int, list[dict]] = {}
    try:
        history = build_league_history()
    except Exception as exc:
        log.warning("trade ledger: history build failed (%s)", exc)
        return trades_by_roster

    for owner in history.owners:
        trades_by_roster[owner.roster_id] = [
            {
                "received": [_pick_key(a) for a in trade.received if "FAAB" not in a],
                "sent": [_pick_key(a) for a in trade.sent if "FAAB" not in a],
            }
            for trade in owner.trades
        ]
    return trades_by_roster


def _pick_key(asset: str) -> str:
    """Normalize a history asset label so pick strings match the seeded ``"<season> R<round>"``."""
    match = _PICK_RE.search(asset)
    year = re.search(r"20\d{2}", asset)
    if match and year:
        return f"{year.group(0)} R{int(match.group(1))}"
    return asset
