"""Recommendation scoreboard — does the AI GM's advice actually work?

A tool that can't show its track record is asking for blind trust. This module reads the
findings the war-room has posted over time, flattens them into individual tracked
recommendations, and grades the ones with a deterministic ground truth.

What is auto-gradeable and how:
    * **lineup** — a start-over-sit call is CORRECT when the started player outscored the
      benched one in the week the call was made for (``grade_lineup``). The week is inferred
      from the finding's timestamp against the NFL schedule; player names are matched to
      nflverse weekly box scores scored under this league's rules.
    * **waiver** — a claim "hits" if the added player cleared a startable weekly line in
      the weeks at or after the claim (``grade_waiver``).

What is not auto-gradeable (tracked as PENDING with a reason, never silently scored):
    * **trade** — needs execution + a value-realization window;
    * **draft / prospect** — resolve over seasons.

A rec also stays PENDING when its week can't be inferred or a player name can't be matched
to a box score — surfaced honestly, never guessed. The aggregate is a calibration read:
hit-rate by kind, and how much of the advice is still unproven.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sleeper_ffm.names import normalize_name

log = logging.getLogger(__name__)

# A weekly fantasy line at or above this is a "startable" week for waiver grading.
_STARTABLE_FP: float = 12.0
_GRADEABLE_KINDS: frozenset[str] = frozenset({"lineup", "waiver"})

# A rec posted this many days before a week's first kickoff still counts as "for" that week
# (Thursday games; managers set lineups midweek).
_PRE_SLATE_DAYS = 3
# How far past a week's first kickoff a rec still attributes to that week (its slate window).
_WEEK_WINDOW_DAYS = 7

WeeklyFP = dict[str, dict[tuple[int, int], float]]
WeekResolver = Callable[[float | None], tuple[int, int] | None]


@dataclass
class TrackedRec:
    """One recommendation extracted from a posted finding."""

    finding_id: str
    made_at: str
    kind: str  # trade | waiver | lineup | draft | prospect
    subject: str  # short human label of the rec
    status: str  # CORRECT | INCORRECT | PUSH | HIT | MISS | PENDING
    detail: str = ""
    # Grading inputs (populated for gradeable kinds; None otherwise).
    made_at_epoch: float | None = None
    start: str | None = None
    sit: str | None = None
    player: str | None = None


@dataclass
class ScoreboardKind:
    """Aggregate outcomes for one recommendation kind."""

    kind: str
    total: int
    graded: int
    correct: int
    hit_rate: float | None  # correct / graded, or None if nothing graded


@dataclass
class Scoreboard:
    """The GM's living track record."""

    recs: list[TrackedRec]
    by_kind: list[ScoreboardKind]
    overall_hit_rate: float | None
    graded_count: int
    pending_count: int
    warnings: list[str] = field(default_factory=list)


def grade_lineup(start_fp: float | None, sit_fp: float | None) -> str:
    """Grade a start-over-sit call. CORRECT if the start outscored the sit.

    Returns ``PENDING`` when either actual score is missing.
    """
    if start_fp is None or sit_fp is None:
        return "PENDING"
    if abs(start_fp - sit_fp) < 1e-9:
        return "PUSH"
    return "CORRECT" if start_fp > sit_fp else "INCORRECT"


def grade_waiver(post_claim_weekly_fp: list[float] | None, startable: float = _STARTABLE_FP) -> str:
    """Grade a waiver claim: HIT if the player ever cleared a startable weekly line.

    Returns ``PENDING`` when there is no post-claim performance yet.
    """
    if not post_claim_weekly_fp:
        return "PENDING"
    return "HIT" if max(post_claim_weekly_fp) >= startable else "MISS"


def summarize(recs: list[TrackedRec]) -> tuple[list[ScoreboardKind], float | None, int, int]:
    """Aggregate tracked recs into per-kind and overall hit-rates. Pure.

    Returns:
        ``(by_kind, overall_hit_rate, graded_count, pending_count)``.
    """
    graded_states = {"CORRECT", "INCORRECT", "PUSH", "HIT", "MISS"}
    positive = {"CORRECT", "HIT"}
    neutral = {"PUSH"}

    by_kind: list[ScoreboardKind] = []
    total_graded = 0
    total_correct = 0
    pending = 0
    for kind in sorted({r.kind for r in recs}):
        group = [r for r in recs if r.kind == kind]
        graded = [r for r in group if r.status in graded_states and r.status not in neutral]
        correct = [r for r in graded if r.status in positive]
        total_graded += len(graded)
        total_correct += len(correct)
        pending += sum(1 for r in group if r.status == "PENDING")
        by_kind.append(
            ScoreboardKind(
                kind=kind,
                total=len(group),
                graded=len(graded),
                correct=len(correct),
                hit_rate=round(len(correct) / len(graded), 3) if graded else None,
            )
        )
    overall = round(total_correct / total_graded, 3) if total_graded else None
    return by_kind, overall, total_graded, pending


# ---------------------------------------------------------------------------
# Extraction — fan a findings list into individual tracked recs
# ---------------------------------------------------------------------------

# Legacy shape: a single finding whose body still carries the whole document's lists.
_LIST_FIELDS = {
    "trade_recs": "trade",
    "waiver_recs": "waiver",
    "lineup_recs": "lineup",
    "draft_recs": "draft",
    "prospect_notes": "prospect",
}


def _label(kind: str, item: dict) -> str:
    if kind == "trade":
        return f"{item.get('partner', '?')}: {item.get('receive', '?')}"
    if kind == "waiver":
        return f"{item.get('player', '?')} (${item.get('faab_bid', '?')})"
    if kind == "lineup":
        return f"start {item.get('start', '?')} / sit {item.get('sit', '?')}"
    if kind == "draft":
        return str(item.get("pick", "?"))
    if kind == "prospect":
        return str(item.get("name", "?"))
    return item.get("subject", kind)


def _tracked(finding_id: str, made: str, epoch: float | None, kind: str, item: dict) -> TrackedRec:
    rationale = item.get("rationale") or ""
    return TrackedRec(
        finding_id=finding_id,
        made_at=made,
        kind=kind,
        subject=_label(kind, item),
        status="PENDING",
        detail=rationale[:200],
        made_at_epoch=epoch,
        start=item.get("start") if kind == "lineup" else None,
        sit=item.get("sit") if kind == "lineup" else None,
        player=item.get("player") if kind == "waiver" else None,
    )


def _extract_recs(findings: list) -> list[TrackedRec]:
    """Flatten posted findings into individual tracked recommendations (status PENDING).

    ``POST /findings/bulk`` fans a master document out into one finding per rec, keyed by
    ``finding.kind`` with a flat body — the primary shape handled here. A legacy finding
    whose body still holds the whole document's list fields (``trade_recs`` etc.) is also
    unpacked, so no posted rec is silently dropped.
    """
    recs: list[TrackedRec] = []
    for f in findings:
        body = getattr(f, "body", {}) or {}
        fid = getattr(f, "finding_id", "?")
        epoch = getattr(f, "created_at", None)
        made = _iso(epoch) or str(body.get("generated_at") or "")

        nested = {k: body[k] for k in _LIST_FIELDS if isinstance(body.get(k), list)}
        if nested:  # legacy whole-document finding
            for field_name, items in nested.items():
                for item in items:
                    if isinstance(item, dict):
                        recs.append(_tracked(fid, made, epoch, _LIST_FIELDS[field_name], item))
            continue

        kind = getattr(f, "kind", "")
        if kind in {"trade", "waiver", "lineup", "draft", "prospect"}:
            recs.append(_tracked(fid, made, epoch, kind, body))
    return recs


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return dt.datetime.fromtimestamp(epoch, dt.UTC).isoformat()


# ---------------------------------------------------------------------------
# Grading — pure core over an injected FP table + week resolver
# ---------------------------------------------------------------------------


def grade_tracked_recs(
    recs: list[TrackedRec],
    weekly_fp: WeeklyFP,
    resolve_week: WeekResolver,
) -> list[TrackedRec]:
    """Grade lineup/waiver recs in place against a weekly-FP table. Pure and testable.

    Args:
        recs: Tracked recs (mutated: ``status`` is set for the gradeable ones).
        weekly_fp: ``normalize_name(player) -> {(season, week): fantasy_points}``.
        resolve_week: Maps a rec's epoch timestamp to ``(season, week)`` or ``None``
            when the week can't be attributed (rec stays PENDING).

    Returns:
        The same ``recs`` list, for chaining.
    """
    for rec in recs:
        if rec.kind not in _GRADEABLE_KINDS:
            continue
        target = resolve_week(rec.made_at_epoch)
        if target is None:
            continue
        season, week = target
        if rec.kind == "lineup" and rec.start and rec.sit:
            start_fp = weekly_fp.get(normalize_name(rec.start), {}).get((season, week))
            sit_fp = weekly_fp.get(normalize_name(rec.sit), {}).get((season, week))
            rec.status = grade_lineup(start_fp, sit_fp)
        elif rec.kind == "waiver" and rec.player:
            series = weekly_fp.get(normalize_name(rec.player), {})
            post = [fp for (s, w), fp in series.items() if s == season and w >= week]
            rec.status = grade_waiver(post)
    return recs


# ---------------------------------------------------------------------------
# Ground-truth builders — impure, wrapped so a failure degrades to all-PENDING
# ---------------------------------------------------------------------------


def _build_week_resolver(seasons: list[int]) -> WeekResolver:
    """Build an epoch→(season, week) resolver from the nflverse schedule's game dates."""
    import polars as pl

    from sleeper_ffm.nflverse.loader import load_schedules

    sched = load_schedules(seasons=seasons)
    if sched.is_empty() or not {"season", "week", "gameday"}.issubset(sched.columns):
        return lambda _epoch: None

    starts = (
        sched.filter(pl.col("gameday").is_not_null())
        .group_by(["season", "week"])
        .agg(pl.col("gameday").min().alias("start"))
        .sort("start")
    )
    windows: list[tuple[dt.date, int, int]] = []
    for r in starts.iter_rows(named=True):
        try:
            start = dt.date.fromisoformat(str(r["start"]))
        except (ValueError, TypeError):
            continue
        windows.append((start, int(r["season"]), int(r["week"])))
    if not windows:
        return lambda _epoch: None

    def resolve(epoch: float | None) -> tuple[int, int] | None:
        if epoch is None:
            return None
        d = dt.datetime.fromtimestamp(epoch, dt.UTC).date()
        for i, (start, season, week) in enumerate(windows):
            eff_start = start - dt.timedelta(days=_PRE_SLATE_DAYS)
            if d < eff_start:
                return None  # falls in a dead gap before this (and every later) week
            cap = start + dt.timedelta(days=_WEEK_WINDOW_DAYS)
            nxt = windows[i + 1][0] if i + 1 < len(windows) else None
            # Bound each week to its own ~7-day slate: a season's final week must not
            # swallow the whole off-season up to next season's kickoff.
            eff_end = min(nxt - dt.timedelta(days=_PRE_SLATE_DAYS), cap) if nxt else cap
            if d < eff_end:
                return (season, week)
        return None

    return resolve


def _build_weekly_fp(seasons: list[int]) -> WeeklyFP:
    """Build ``normalize_name -> {(season, week): fp}`` from nflverse weekly box scores."""
    from sleeper_ffm.nflverse.loader import load_weekly
    from sleeper_ffm.scoring.engine import load_scoring, score, stats_from_nflverse

    weekly = load_weekly(seasons=seasons)
    if weekly.is_empty() or "player_display_name" not in weekly.columns:
        return {}
    scoring = load_scoring()
    out: WeeklyFP = {}
    for row in weekly.iter_rows(named=True):
        name = row.get("player_display_name")
        season, week = row.get("season"), row.get("week")
        if not name or season is None or week is None:
            continue
        key = normalize_name(str(name))
        if not key:
            continue
        fp = score(stats_from_nflverse(row), scoring)
        cell = (int(season), int(week))
        series = out.setdefault(key, {})
        # Duplicate display names across players are rare; keep the higher weekly score.
        if fp > series.get(cell, float("-inf")):
            series[cell] = fp
    return out


def build_scoreboard(limit: int = 200) -> Scoreboard:
    """Build the recommendation scoreboard from posted findings, grading where possible.

    Lineup and waiver recs are graded against nflverse weekly box scores (scored under
    this league's rules) once their week can be inferred from the schedule; everything
    else — and anything whose week/player can't be resolved — is surfaced as PENDING.
    """
    from sleeper_ffm.reasoning.findings import list_findings

    warnings: list[str] = []
    try:
        findings = list_findings(limit=limit)
    except Exception as exc:
        log.warning("scoreboard: findings unavailable: %s", exc)
        return Scoreboard([], [], None, 0, 0, ["Findings store unavailable."])

    recs = _extract_recs(findings)
    if not recs:
        warnings.append("No recommendations posted yet; scoreboard is empty.")

    gradeable = [r for r in recs if r.kind in _GRADEABLE_KINDS]
    if gradeable:
        try:
            resolver = _build_week_resolver(_candidate_seasons(gradeable))
            targets = [resolver(r.made_at_epoch) for r in gradeable]
            seasons = sorted({t[0] for t in targets if t is not None})
            if seasons:
                # Build the FP table only for the seasons the recs actually resolved to.
                weekly_fp = _build_weekly_fp(seasons)
                grade_tracked_recs(recs, weekly_fp, resolver)
            else:
                warnings.append(
                    "Lineup/waiver recs present but none could be attributed to an NFL week "
                    "(off-season timestamps or no schedule) — tracked as PENDING."
                )
        except Exception as exc:
            log.warning("scoreboard: outcome grading unavailable: %s", exc)
            warnings.append(f"Outcome grading unavailable ({exc}); gradeable recs left PENDING.")

    if gradeable and not any(r.status != "PENDING" for r in gradeable):
        warnings.append(
            "No lineup/waiver rec has resolved to a played-out result yet — hit-rate will "
            "populate as the graded weeks complete."
        )

    by_kind, overall, graded, pending = summarize(recs)
    return Scoreboard(
        recs=recs[:limit],
        by_kind=by_kind,
        overall_hit_rate=overall,
        graded_count=graded,
        pending_count=pending,
        warnings=warnings,
    )


def _candidate_seasons(recs: list[TrackedRec]) -> list[int]:
    """NFL seasons a batch of recs could belong to, from their timestamps.

    An NFL season spans Sept→Feb, so Jan/Feb timestamps belong to the prior year's season.
    Returns the union plus a one-year cushion on each side so the schedule resolver has the
    weeks it needs at the boundaries.
    """
    years: set[int] = set()
    for r in recs:
        if r.made_at_epoch is None:
            continue
        d = dt.datetime.fromtimestamp(r.made_at_epoch, dt.UTC)
        season = d.year - 1 if d.month <= 2 else d.year
        years.update({season - 1, season, season + 1})
    if not years:
        from sleeper_ffm.config import DEFAULT_VALUE_SEASON

        return [DEFAULT_VALUE_SEASON - 1, DEFAULT_VALUE_SEASON]
    return sorted(years)
