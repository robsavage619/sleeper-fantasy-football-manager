"""Recommendation scoreboard — does the AI GM's advice actually work?

A tool that can't show its track record is asking for blind trust. This module reads the
findings the war-room has posted over time, flattens them into individual tracked
recommendations, and grades the ones with a deterministic ground truth.

What is auto-gradeable and how:
    * **lineup** — a start-over-sit call is CORRECT when the started player outscored the
      benched one that week (``grade_lineup``). Pure, exact, no judgment.
    * **waiver** — a claim "hits" if the added player cleared a startable weekly line in
      the weeks after the claim (``grade_waiver``).

What is not yet auto-gradeable (tracked as PENDING with a reason, never silently scored):
    * **trade** — needs execution + a value-realization window;
    * **draft / prospect** — resolve over seasons.

The aggregate is a calibration read: hit-rate by kind, and — the honest part — how much of
the advice is still unproven. Grades only appear where ground truth exists; everything
else is surfaced as pending, not buried.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# A weekly fantasy line at or above this is a "startable" week for waiver grading.
_STARTABLE_FP: float = 12.0
_GRADEABLE_KINDS: frozenset[str] = frozenset({"lineup", "waiver"})


@dataclass
class TrackedRec:
    """One recommendation extracted from a posted finding."""

    finding_id: str
    made_at: str
    kind: str  # trade | waiver | lineup | draft | prospect
    subject: str  # short human label of the rec
    status: str  # CORRECT | INCORRECT | PUSH | HIT | MISS | PENDING
    detail: str = ""


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


def _extract_recs(findings: list) -> list[TrackedRec]:
    """Flatten posted findings into individual tracked recommendations (PENDING)."""
    recs: list[TrackedRec] = []
    kind_fields = {
        "trade_recs": ("trade", lambda r: f"{r.get('partner', '?')}: {r.get('receive', '?')}"),
        "waiver_recs": ("waiver", lambda r: f"{r.get('player', '?')} (${r.get('faab_bid', '?')})"),
        "lineup_recs": (
            "lineup",
            lambda r: f"start {r.get('start', '?')} / sit {r.get('sit', '?')}",
        ),
        "draft_recs": ("draft", lambda r: str(r.get("pick", "?"))),
        "prospect_notes": ("prospect", lambda r: str(r.get("name", "?"))),
    }
    for f in findings:
        body = getattr(f, "body", {}) or {}
        fid = getattr(f, "id", "?")
        made = getattr(f, "created", "") or getattr(f, "created_at", "")
        for field_name, (kind, labeler) in kind_fields.items():
            items = body.get(field_name)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                recs.append(
                    TrackedRec(
                        finding_id=fid,
                        made_at=made,
                        kind=kind,
                        subject=labeler(item),
                        status="PENDING",
                        detail=item.get("rationale", "")[:200] if item.get("rationale") else "",
                    )
                )
    return recs


def build_scoreboard(limit: int = 200) -> Scoreboard:
    """Build the recommendation scoreboard from posted findings.

    Auto-grading of trade/waiver/lineup outcomes requires linking to played-out results;
    until that ground truth exists those recs are tracked as PENDING (surfaced, not
    scored). Returns a structured ledger regardless.
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
    graded_kinds = {r.kind for r in recs} & _GRADEABLE_KINDS
    if recs and not any(r.status != "PENDING" for r in recs):
        warnings.append(
            "All recs currently PENDING — outcome linkage (weekly FP / transactions) not "
            f"yet wired for {sorted(graded_kinds) or 'these kinds'}."
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
