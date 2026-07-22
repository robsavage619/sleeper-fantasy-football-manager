"""Gap decomposition — WHERE does the engine lose capture, and where do the managers?

The arena says the shipped engine captures ~81-82% of the hindsight-optimal lineup while
the managers capture ~84%, but a single capture number can't say where those points go.
This report decomposes every roster-week's loss (optimal minus started) into named
decision buckets, for the engine lineup and the manager lineup side by side:

* ``dead_starter``   — started a player who scored exactly 0.0 (the availability bucket).
* ``kdef``           — a K/DEF slot call.
* ``benched_flagged``— sat a producer who carried an injury designation or missed his
  team's previous game (the flip side of availability: the discount benched him, he played).
* ``rank_inversion`` — a same-position miss among unflagged players (pure ranking error).
* ``flex_cross``     — a cross-position FLEX call.
* ``unfilled``       — a slot left empty that the optimal lineup filled.

The decomposition is exact: bucket losses sum to ``optimal_pts - started_pts`` for each
side, so bucket shares are directly comparable to (1 - capture). The point is targeting —
a lever aimed at a bucket worth 0.1pp is not worth building, and the engine-vs-manager
*difference* per bucket is the actual gap to close.

Mechanically each started lineup is diffed against the optimal one: players the lineup
started but optimal didn't ("extra") are paired against players optimal started but the
lineup didn't ("missed"), same-position pairs first, the remainder cross-position. Because
the optimal lineup always contains the top scorers at each position, same-position pair
losses are non-negative by construction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sleeper_ffm.evals.arena import (
    _DEFAULT_MAX_WEEK,
    _DEFAULT_MIN_WEEK,
    ArenaUnavailableError,
    PointHistory,
    Projector,
    _extend_history,
    _injury_calendar,
    _player_positions,
    _resolve_league_id,
    _weeks_played_by_team,
    make_engine_projector,
    select_lineup,
)

log = logging.getLogger(__name__)

_KDEF = frozenset({"K", "DEF"})

BUCKETS = (
    "dead_starter",
    "kdef",
    "benched_flagged",
    "rank_inversion",
    "flex_cross",
    "unfilled",
)


def decompose_loss(
    started: list[str],
    optimal: list[str],
    actual_points: dict[str, float],
    positions: dict[str, str],
    flagged: frozenset[str] | set[str],
) -> list[tuple[str, float]]:
    """Split one lineup's loss vs optimal into ``(bucket, points_lost)`` pairs.

    Pure and exact: the returned losses sum to ``sum(optimal pts) - sum(started pts)``.
    ``flagged`` is the set of player ids carrying an availability flag (injury designation
    or missed-last-game) for this week — it decides ``benched_flagged`` vs
    ``rank_inversion``.
    """
    started_set = set(started)
    optimal_set = set(optimal)
    missed = [pid for pid in optimal if pid not in started_set]
    extra = [pid for pid in started if pid not in optimal_set]

    def pts(pid: str) -> float:
        return actual_points.get(pid, 0.0)

    # Same-position pairs first: they are genuine "started X over Y" decisions.
    missed_by_pos: dict[str, list[str]] = {}
    for pid in sorted(missed, key=pts, reverse=True):
        missed_by_pos.setdefault(positions.get(pid, "?"), []).append(pid)
    extra_by_pos: dict[str, list[str]] = {}
    for pid in sorted(extra, key=pts, reverse=True):
        extra_by_pos.setdefault(positions.get(pid, "?"), []).append(pid)

    pairs: list[tuple[str, str]] = []  # (extra_started, missed_optimal)
    for pos, m_list in missed_by_pos.items():
        e_list = extra_by_pos.get(pos, [])
        n = min(len(m_list), len(e_list))
        pairs.extend(zip(e_list[:n], m_list[:n], strict=True))
        missed_by_pos[pos] = m_list[n:]
        extra_by_pos[pos] = e_list[n:]

    # Remainder pairs cross positions — these are FLEX-shaped calls.
    m_rest = sorted((p for lst in missed_by_pos.values() for p in lst), key=pts, reverse=True)
    e_rest = sorted((p for lst in extra_by_pos.values() for p in lst), key=pts, reverse=True)
    n = min(len(m_rest), len(e_rest))
    pairs.extend(zip(e_rest[:n], m_rest[:n], strict=True))

    out: list[tuple[str, float]] = []
    for e_pid, m_pid in pairs:
        loss = pts(m_pid) - pts(e_pid)
        if pts(e_pid) == 0.0:
            bucket = "dead_starter"
        elif positions.get(e_pid) in _KDEF and positions.get(m_pid) in _KDEF:
            bucket = "kdef"
        elif m_pid in flagged:
            bucket = "benched_flagged"
        elif positions.get(e_pid) == positions.get(m_pid):
            bucket = "rank_inversion"
        else:
            bucket = "flex_cross"
        out.append((bucket, loss))

    # Unpaired leftovers: a slot one side filled and the other left empty.
    for pid in m_rest[n:]:
        out.append(("unfilled", pts(pid)))
    for pid in e_rest[n:]:
        out.append(("unfilled", -pts(pid)))
    return out


@dataclass
class GapReport:
    """Bucketed loss-vs-optimal for the engine and the managers over one season."""

    season: int
    league_id: str
    projector: str
    n_roster_weeks: int
    optimal_total: float
    engine_total: float
    actual_total: float
    engine_loss: dict[str, float] = field(default_factory=dict)
    engine_pairs: dict[str, int] = field(default_factory=dict)
    actual_loss: dict[str, float] = field(default_factory=dict)
    actual_pairs: dict[str, int] = field(default_factory=dict)
    # Roster-weeks where the engine's lineup was exactly the manager's.
    identical_lineups: int = 0

    def table(self) -> str:
        """Bucket-by-bucket capture loss, engine vs managers, with the gap per bucket."""
        lines = [
            f"{self.season or 'pooled'} [{self.projector}] gap decomposition "
            f"({self.n_roster_weeks} roster-weeks, "
            f"identical lineups {self.identical_lineups / max(self.n_roster_weeks, 1):.0%})",
            f"  {'bucket':<16} {'engine':>14} {'managers':>14} {'gap':>8}",
        ]
        for bucket in BUCKETS:
            e_pp = 100 * self.engine_loss.get(bucket, 0.0) / self.optimal_total
            a_pp = 100 * self.actual_loss.get(bucket, 0.0) / self.optimal_total
            e_n = self.engine_pairs.get(bucket, 0)
            a_n = self.actual_pairs.get(bucket, 0)
            lines.append(
                f"  {bucket:<16} {e_pp:>6.2f}pp ({e_n:>4}) {a_pp:>6.2f}pp ({a_n:>4}) "
                f"{e_pp - a_pp:>+7.2f}"
            )
        e_cap = 100 * self.engine_total / self.optimal_total
        a_cap = 100 * self.actual_total / self.optimal_total
        lines.append(
            f"  {'capture':<16} {e_cap:>6.2f}% {'':<7} {a_cap:>6.2f}% {'':<7} "
            f"{e_cap - a_cap:>+7.2f}"
        )
        return "\n".join(lines)


def merge_gap_reports(reports: list[GapReport]) -> GapReport:
    """Pool several seasons' reports into one (points summed, labelled season 0)."""
    if not reports:
        raise ValueError("no reports to merge")
    pooled = GapReport(
        season=0,
        league_id="pooled",
        projector=reports[0].projector,
        n_roster_weeks=sum(r.n_roster_weeks for r in reports),
        optimal_total=sum(r.optimal_total for r in reports),
        engine_total=sum(r.engine_total for r in reports),
        actual_total=sum(r.actual_total for r in reports),
        identical_lineups=sum(r.identical_lineups for r in reports),
    )
    for r in reports:
        for bucket in BUCKETS:
            pooled.engine_loss[bucket] = pooled.engine_loss.get(bucket, 0.0) + r.engine_loss.get(
                bucket, 0.0
            )
            pooled.actual_loss[bucket] = pooled.actual_loss.get(bucket, 0.0) + r.actual_loss.get(
                bucket, 0.0
            )
            pooled.engine_pairs[bucket] = pooled.engine_pairs.get(bucket, 0) + r.engine_pairs.get(
                bucket, 0
            )
            pooled.actual_pairs[bucket] = pooled.actual_pairs.get(bucket, 0) + r.actual_pairs.get(
                bucket, 0
            )
    return pooled


def _build_flag_calendar(season: int, max_week: int) -> dict[int, frozenset[str]]:
    """``{week: {sleeper ids carrying an availability flag}}`` — injury designation or DNP.

    Mirrors the two availability levers the engine projector applies, mapped back to
    sleeper ids so lineup diffs can be tagged. Best-effort: missing nflverse data degrades
    to empty sets (every miss then reads as a ranking error), and that degradation is
    logged rather than silent.
    """
    import polars as pl

    from sleeper_ffm.nflverse.loader import load_id_map, load_schedules, load_weekly

    gsis_to_sleeper: dict[str, str] = {}
    id_map = load_id_map()
    if {"sleeper_id", "gsis_id"} <= set(id_map.columns):
        for r in id_map.select(["sleeper_id", "gsis_id"]).iter_rows(named=True):
            if r.get("sleeper_id") and r.get("gsis_id"):
                gsis_to_sleeper[str(r["gsis_id"])] = str(r["sleeper_id"]).split(".")[0]

    injuries = _injury_calendar(season)
    if not injuries:
        log.warning("gap_report: no injury calendar for %s; flags are DNP-only", season)

    weekly = load_weekly([season])
    box_weeks: dict[str, set[int]] = {}
    team_by_gsis: dict[str, str] = {}
    if weekly.is_empty():
        log.warning("gap_report: no nflverse weekly for %s; DNP flags unavailable", season)
    else:
        for row in weekly.filter(pl.col("season_type") == "REG").iter_rows(named=True):
            gsis = str(row["player_id"])
            box_weeks.setdefault(gsis, set()).add(int(row["week"]))
            team_by_gsis[gsis] = row.get("recent_team") or ""
    weeks_played = _weeks_played_by_team(load_schedules, season)

    out: dict[int, frozenset[str]] = {}
    for wk in range(1, max_week + 1):
        flagged: set[str] = set()
        for gsis in injuries.get(wk, {}):
            sid = gsis_to_sleeper.get(gsis)
            if sid:
                flagged.add(sid)
        for gsis, weeks in box_weeks.items():
            prior = [w for w in weeks_played.get(team_by_gsis.get(gsis, ""), ()) if w < wk]
            if prior and max(prior) not in weeks:
                sid = gsis_to_sleeper.get(gsis)
                if sid:
                    flagged.add(sid)
        out[wk] = frozenset(flagged)
    return out


def run_gap_report(
    season: int,
    projector: Projector | None = None,
    projector_name: str = "engine",
    min_week: int = _DEFAULT_MIN_WEEK,
    max_week: int = _DEFAULT_MAX_WEEK,
    league_id: str | None = None,
) -> GapReport:
    """Replay a season exactly like the arena, but bucket every point of capture loss.

    Same blind-replay discipline as :func:`sleeper_ffm.evals.arena.run_arena`: the
    projector sees only prior weeks' history, and realized points enter only after the
    lineup is chosen.

    Raises:
        ArenaUnavailableError: League history or matchups unavailable.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        lid = league_id or _resolve_league_id(client, season)
        if lid is None:
            raise ArenaUnavailableError(f"no league in this dynasty's history for season {season}")
        league = client.league(lid)
        roster_positions = list(league.roster_positions or [])
        if not roster_positions:
            raise ArenaUnavailableError(f"league {lid} has no roster_positions")
        positions = _player_positions(client)
        proj = projector or make_engine_projector(season)
        flags = _build_flag_calendar(season, max_week)

        report = GapReport(
            season=season,
            league_id=lid,
            projector=projector_name,
            n_roster_weeks=0,
            optimal_total=0.0,
            engine_total=0.0,
            actual_total=0.0,
        )
        history = PointHistory()
        for week in range(1, max_week + 1):
            try:
                matchups = client.matchups(week, league_id=lid)
            except Exception as exc:
                log.warning("gap_report: %s week %s unavailable: %s", season, week, exc)
                matchups = []
            if not matchups:
                continue
            if week >= min_week:
                week_flags = flags.get(week, frozenset())
                for roster in matchups:
                    _tally_roster_week(
                        report, week, roster, positions, roster_positions, history, proj, week_flags
                    )
            _extend_history(history, matchups)

    if not report.n_roster_weeks:
        raise ArenaUnavailableError(f"no scorable roster-weeks for season {season}")
    return report


def _tally_roster_week(
    report: GapReport,
    week: int,
    roster: dict,
    positions: dict[str, str],
    roster_positions: list[str],
    history: PointHistory,
    projector: Projector,
    flagged: frozenset[str],
) -> None:
    """Diff one roster-week's engine and manager lineups against optimal into the report."""
    actual_points_raw = roster.get("players_points") or {}
    available = [pid for pid in (roster.get("players") or []) if pid]
    if not available or not actual_points_raw:
        return

    # Blind pick first — realized points are consulted only after, as in the arena.
    projected = projector(week, available, positions, history)
    engine_ids = select_lineup(projected, positions, roster_positions)

    actual_points = {pid: float(pts) for pid, pts in actual_points_raw.items()}
    optimal_ids = select_lineup(actual_points, positions, roster_positions)
    manager_ids = [pid for pid in (roster.get("starters") or []) if pid]

    report.n_roster_weeks += 1
    report.optimal_total += sum(actual_points.get(pid, 0.0) for pid in optimal_ids)
    report.engine_total += sum(actual_points.get(pid, 0.0) for pid in engine_ids)
    report.actual_total += sum(actual_points.get(pid, 0.0) for pid in manager_ids)
    if set(engine_ids) == set(manager_ids):
        report.identical_lineups += 1

    for bucket, loss in decompose_loss(engine_ids, optimal_ids, actual_points, positions, flagged):
        report.engine_loss[bucket] = report.engine_loss.get(bucket, 0.0) + loss
        report.engine_pairs[bucket] = report.engine_pairs.get(bucket, 0) + 1
    for bucket, loss in decompose_loss(manager_ids, optimal_ids, actual_points, positions, flagged):
        report.actual_loss[bucket] = report.actual_loss.get(bucket, 0.0) + loss
        report.actual_pairs[bucket] = report.actual_pairs.get(bucket, 0) + 1


def mean_capture(report: GapReport) -> tuple[float, float]:
    """(engine, managers) capture as point-total shares — cross-check vs the arena."""
    if not report.optimal_total:
        return 0.0, 0.0
    return (
        report.engine_total / report.optimal_total,
        report.actual_total / report.optimal_total,
    )


__all__ = [
    "BUCKETS",
    "GapReport",
    "decompose_loss",
    "mean_capture",
    "merge_gap_reports",
    "run_gap_report",
]
