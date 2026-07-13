"""Lightweight recommendation quality checks for the product surface."""

from __future__ import annotations

from dataclasses import dataclass

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, PREFERRED_VALUE_SEASON, cached_weekly_seasons
from sleeper_ffm.model.owner_history import build_league_history
from sleeper_ffm.model.trade_acceptance import recommend_trade_offers


@dataclass
class EvalFinding:
    """One product-quality finding from the recommendation eval harness."""

    area: str
    status: str
    severity: str
    detail: str
    next_action: str


@dataclass
class RecommendationEvalReport:
    """A compact scorecard for app recommendation trust."""

    overall_status: str
    findings: list[EvalFinding]
    metrics: dict[str, float | int | str]


def build_recommendation_eval(top: int = 8) -> RecommendationEvalReport:
    """Build a non-mutating evaluation report for recommendation trust."""
    findings: list[EvalFinding] = []
    metrics: dict[str, float | int | str] = {}

    cached = cached_weekly_seasons()
    metrics["active_value_season"] = DEFAULT_VALUE_SEASON
    metrics["preferred_value_season"] = PREFERRED_VALUE_SEASON
    metrics["cached_weekly_seasons"] = ",".join(str(season) for season in cached)
    if DEFAULT_VALUE_SEASON != PREFERRED_VALUE_SEASON:
        findings.append(
            EvalFinding(
                area="data_freshness",
                status="degraded",
                severity="high",
                detail=(
                    f"Valuation is using cached {DEFAULT_VALUE_SEASON}; preferred "
                    f"{PREFERRED_VALUE_SEASON} is not cached."
                ),
                next_action=(
                    "Ingest preferred-season nflverse weekly data when upstream publishes it."
                ),
            )
        )

    history = build_league_history()
    trade_counts = [owner.trade_count for owner in history.owners]
    active_owners = sum(1 for count in trade_counts if count > 0)
    metrics["owners_with_trade_history"] = active_owners
    metrics["avg_trades_per_owner"] = round(sum(trade_counts) / max(1, len(trade_counts)), 2)
    if active_owners < max(3, len(history.owners) // 2):
        findings.append(
            EvalFinding(
                area="trade_calibration",
                status="limited",
                severity="medium",
                detail="Fewer than half the league has meaningful trade-history evidence.",
                next_action=(
                    "Treat acceptance scores as fit scores until rejected/accepted "
                    "offers are logged."
                ),
            )
        )

    offers = recommend_trade_offers(top=top)
    evidence_counts = [offer.evidence_count for offer in offers]
    low_evidence = sum(1 for count in evidence_counts if count < 3)
    metrics["trade_offers_evaluated"] = len(offers)
    metrics["low_evidence_trade_offers"] = low_evidence
    metrics["avg_offer_acceptance_score"] = round(
        sum(offer.acceptance_score for offer in offers) / max(1, len(offers)),
        2,
    )
    if low_evidence:
        findings.append(
            EvalFinding(
                area="trade_recommendations",
                status="limited",
                severity="medium",
                detail=(
                    f"{low_evidence}/{len(offers)} trade offer(s) have fewer "
                    "than 3 history samples."
                ),
                next_action=(
                    "Show calibration labels in the UI and prefer higher-evidence partners."
                ),
            )
        )

    overall = "PASS" if not findings else "DEGRADED"
    return RecommendationEvalReport(
        overall_status=overall,
        findings=findings,
        metrics=metrics,
    )
