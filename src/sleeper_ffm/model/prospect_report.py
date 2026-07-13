"""Deep prospect scouting report — assembles every free signal into one view.

Layers, richest-available first:
  1. Market consensus (FantasyCalc) — value, ranks, tier, 30d trend, ADP,
     liquidity, volatility, redraft-vs-dynasty split, NFL draft capital, bio.
  2. Athletic profile (nflverse combine) — measurables + weight-adjusted speed.
  3. College production (CFBD) — per-season trajectory + recruiting (needs key).
  4. Roster fit (owner dossier) — positional depth + contention window.
  5. Derived signals — a ranked, scannable "sharp-manager summary" computed from
     the above (draft capital, timeline fit, momentum, athleticism, conviction).

None of layers 1, 2, 4 need a CFBD key. The report degrades gracefully: any
missing layer is simply absent, never fatal.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def _draft_capital_tier(rnd: int | None) -> str | None:
    if rnd is None:
        return None
    if rnd == 1:
        return "PREMIUM"
    if rnd == 2:
        return "DAY 2"
    return "DAY 3"


def _player_timeline(market: dict | None) -> str | None:
    """Ascending-youth vs win-now, from the redraft/dynasty value split."""
    if not market:
        return None
    value = market.get("value")
    redraft = market.get("redraft_value")
    if not value or redraft is None or value <= 0:
        return None
    premium_pct = (value - redraft) / value * 100
    if premium_pct >= 20:
        return "ASCENDING"
    if premium_pct >= 5:
        return "DEVELOPING"
    if premium_pct >= -5:
        return "READY-NOW"
    return "WIN-NOW"


# How a player's own timeline lines up with the manager's contention window.
_CONTENDING = {"OPEN", "CLOSING", "OPENING"}
_BUILDING = {"ASCENDING", "RETOOLING"}


def _timeline_verdict(player_timeline: str | None, window_label: str | None) -> str | None:
    if not player_timeline or not window_label:
        return None
    future = player_timeline in ("ASCENDING", "DEVELOPING")
    now = player_timeline in ("READY-NOW", "WIN-NOW")
    if window_label in _BUILDING:
        if future:
            return "ALIGNED — youth matches your build window"
        if now:
            return "OFF-TIMELINE — win-now asset while you're building"
    if window_label in _CONTENDING:
        if now:
            return "ALIGNED — ready-now value fits your open window"
        if future:
            return "OFF-TIMELINE — future asset while your window is open"
    return "NEUTRAL"


def _pct(part: float | None, whole: float | None) -> float | None:
    if not part or not whole or whole == 0:
        return None
    return round(part / whole * 100, 1)


def _derive_signals(
    *,
    position: str,
    age: float | None,
    market: dict[str, Any] | None,
    draft_capital: dict[str, Any] | None,
    athleticism: dict[str, Any] | None,
    college: dict[str, Any] | None,
    roster_fit: dict[str, Any] | None,
    player_timeline: str | None,
) -> list[dict]:
    """Ranked, honest one-liner signals — the fast read for a decision."""
    signals: list[dict] = []

    # 1. NFL draft capital — landing spot + pedigree, top predictor for RB/WR.
    rnd = int(draft_capital["round"]) if draft_capital and draft_capital.get("round") else None
    if draft_capital and rnd is not None:
        tier = draft_capital.get("capital_tier")
        pick, team = draft_capital.get("pick"), draft_capital.get("team")
        loc = f"R{rnd}" + (f" P{pick}" if pick else "") + (f" → {team}" if team else "")
        tone = "positive" if rnd <= 2 else "caution" if rnd >= 5 else "neutral"
        signals.append({"label": f"{tier} draft capital", "detail": f"{loc}", "tone": tone})

    # 2. Timeline fit vs the manager's own window.
    if roster_fit and roster_fit.get("timeline_verdict"):
        verdict = roster_fit["timeline_verdict"]
        tone = (
            "positive"
            if verdict.startswith("ALIGNED")
            else "caution"
            if verdict.startswith("OFF")
            else "neutral"
        )
        signals.append({"label": "Timeline fit", "detail": verdict, "tone": tone})

    # 3. Market momentum — is the community buying or selling this player?
    if market and market.get("trend_30day") is not None and market.get("value"):
        trend = market["trend_30day"]
        trend_pct = _pct(abs(trend), market["value"])
        if trend > 0:
            signals.append(
                {
                    "label": "Market rising",
                    "detail": f"+{trend} (30d, ~{trend_pct}% of value) — community is buying",
                    "tone": "positive",
                }
            )
        elif trend < 0:
            signals.append(
                {
                    "label": "Market cooling",
                    "detail": f"{trend} (30d, ~{trend_pct}% of value) — community is selling",
                    "tone": "caution",
                }
            )

    # 4. Athleticism — speed score / forty grade for RB/WR/TE.
    if athleticism and athleticism.get("athletic_grade"):
        grade = athleticism["athletic_grade"]
        forty = athleticism.get("forty")
        ss = athleticism.get("speed_score")
        bits = []
        if forty:
            bits.append(f"{forty} forty")
        if ss:
            bits.append(f"speed score {ss}")
        tone = (
            "positive"
            if grade in ("ELITE", "GOOD")
            else "neutral"
            if grade == "AVERAGE"
            else "caution"
        )
        signals.append(
            {
                "label": f"{grade} athlete",
                "detail": ", ".join(bits) or "combine tested",
                "tone": tone,
            }
        )

    # 5. Market conviction — a divided market is leverage for a manager with a view.
    if market and market.get("volatility_pct") is not None:
        vol = market["volatility_pct"]
        if vol >= 8:
            signals.append(
                {
                    "label": "Divided market",
                    "detail": f"high value volatility ({vol}%) — a conviction play either way",
                    "tone": "neutral",
                }
            )

    # 6. College production — real final-season counting stats when available.
    if college and college.get("has_data") and college.get("seasons"):
        latest = college["seasons"][-1]
        rec, rush, passing = latest.get("receiving"), latest.get("rushing"), latest.get("passing")
        if position in ("WR", "TE") and rec:
            detail = f"{rec['receptions']} rec, {rec['yards']} yds, {rec['touchdowns']} TD (final)"
            signals.append({"label": "College production", "detail": detail, "tone": "neutral"})
        elif position == "RB" and rush:
            extra = f" + {rec['receptions']} rec" if rec and rec.get("receptions") else ""
            detail = f"{rush['carries']} car, {rush['yards']} yds, {rush['touchdowns']} TD{extra}"
            signals.append({"label": "College workload", "detail": detail, "tone": "neutral"})
        elif position == "QB" and passing:
            signals.append(
                {
                    "label": "College production",
                    "detail": (
                        f"{passing['yards']} yds, {passing['touchdowns']} TD, "
                        f"{passing['interceptions']} INT, {passing['comp_pct']}% (final yr)"
                    ),
                    "tone": "neutral",
                }
            )

    # 7. Youth — a young producer is the dynasty premium.
    if age is not None and age <= 21.0:
        signals.append({"label": "Young for class", "detail": f"age {age:.1f}", "tone": "positive"})

    return signals


def _build_roster_fit(position: str, player_timeline: str | None) -> dict | None:
    """Positional depth + contention window for the manager's own roster."""
    try:
        from sleeper_ffm.config import MY_ROSTER_ID
        from sleeper_ffm.model.owner_dossier import build_dossier

        dossier = build_dossier(MY_ROSTER_ID)
    except Exception as exc:
        log.warning("prospect_report: roster fit unavailable: %s", exc)
        return None

    rank = next((r for r in dossier.position_ranks if r.position == position), None)
    window_label = dossier.contention.label
    return {
        "position_rank": rank.rank if rank else None,
        "position_of": rank.of if rank else None,
        "position_tier": rank.tier if rank else None,
        "position_league_avg": round(rank.league_avg, 1) if rank else None,
        "contention_label": window_label,
        "contention_window": dossier.contention.window,
        "contention_rationale": dossier.contention.rationale,
        "timeline_verdict": _timeline_verdict(player_timeline, window_label),
    }


def _build_market(player_id: str | None) -> dict | None:
    """FantasyCalc consensus record for this prospect (None if unmatched)."""
    if not player_id:
        return None
    try:
        from sleeper_ffm.market.fantasycalc import fetch_full

        full = fetch_full()
    except Exception as exc:
        log.warning("prospect_report: market fetch failed: %s", exc)
        return None
    rec = full.get(str(player_id))
    if rec is None:
        return None
    rec = dict(rec)
    rec["player_timeline"] = _player_timeline(rec)
    rec["dynasty_premium_pct"] = _pct(
        (rec["value"] - rec["redraft_value"])
        if rec.get("value") and rec.get("redraft_value") is not None
        else None,
        rec.get("value"),
    )
    return rec


def _build_college(
    *,
    name: str,
    year: int,
    recruiting_rank: int | None,
    stars: int | None,
) -> dict:
    """Real per-season college production from keyless ESPN box scores.

    No API key required — sportsdataverse publishes ESPN box parquet on GitHub.
    """
    try:
        from sleeper_ffm.college.cfb_box import college_history

        seasons = college_history(name, year)
    except Exception as exc:
        log.warning("prospect_report: college history failed: %s", exc)
        seasons = []

    return {
        "source": "ESPN box (sportsdataverse)" if seasons else None,
        "has_data": bool(seasons),
        "seasons": seasons,
        "recruiting_rank": recruiting_rank,
        "stars": stars,
    }


def build_scouting_report(
    *,
    name: str,
    position: str,
    college: str,
    year: int,
    age: float | None,
    player_id: str | None = None,
    recruiting_rank: int | None = None,
    stars: int | None = None,
    dynasty_prospect_score: float = 0.0,
) -> dict[str, Any]:
    """Assemble the full multi-source scouting report for one prospect."""
    market = _build_market(player_id)
    athleticism = None
    try:
        from sleeper_ffm.nflverse.combine import combine_for

        athleticism = combine_for(name, position, year)
    except Exception as exc:
        log.warning("prospect_report: combine lookup failed: %s", exc)

    college_block = _build_college(
        name=name,
        year=year,
        recruiting_rank=recruiting_rank,
        stars=stars,
    )

    player_timeline = market.get("player_timeline") if market else None
    roster_fit = _build_roster_fit(position, player_timeline)

    # NFL draft capital: prefer FantasyCalc, fall back to combine's draft fields.
    draft_capital: dict | None = None
    if market and market.get("draft_round"):
        draft_capital = {
            "year": market.get("draft_year"),
            "round": market.get("draft_round"),
            "pick": market.get("draft_pick"),
            "team": market.get("team"),
        }
    elif athleticism and athleticism.get("draft_round"):
        draft_capital = {
            "year": year,
            "round": athleticism.get("draft_round"),
            "pick": athleticism.get("draft_ovr"),
            "team": athleticism.get("draft_team"),
        }
    if draft_capital:
        draft_capital["capital_tier"] = _draft_capital_tier(draft_capital.get("round"))

    signals = _derive_signals(
        position=position,
        age=age,
        market=market,
        draft_capital=draft_capital,
        athleticism=athleticism,
        college=college_block,
        roster_fit=roster_fit,
        player_timeline=player_timeline,
    )

    sources = []
    if market:
        sources.append("FantasyCalc")
    if athleticism:
        sources.append("NFL Combine (nflverse)")
    if college_block["has_data"]:
        sources.append("ESPN box (sportsdataverse)")
    if roster_fit:
        sources.append("League dossier")

    warnings: list[str] = []
    if market is None:
        warnings.append(
            "No FantasyCalc market match — consensus rank, trend, and draft "
            "capital unavailable for this player."
        )

    has_rich = bool(market) or bool(athleticism) or college_block["has_data"]
    data_quality = (
        "FULL"
        if market and (athleticism or college_block["has_data"])
        else "PARTIAL"
        if has_rich
        else "DEGRADED"
    )

    return {
        "identity": {
            "name": name,
            "position": position,
            "college": college,
            "class_year": year,
            "age": age,
            "nfl_team": (market or {}).get("team"),
            "height_in": (market or {}).get("height") or (athleticism or {}).get("height_in"),
            "weight": (market or {}).get("weight") or (athleticism or {}).get("weight"),
        },
        "dynasty_prospect_score": dynasty_prospect_score,
        "market": market,
        "draft_capital": draft_capital,
        "athleticism": athleticism,
        "college": college_block,
        "roster_fit": roster_fit,
        "signals": signals,
        "data_quality": data_quality,
        "warnings": warnings,
        "sources_used": sources,
    }


def build_scouting_prompt(
    *,
    name: str,
    position: str,
    college: str,
    year: int,
    age: float | None,
    player_id: str | None = None,
    recruiting_rank: int | None = None,
    stars: int | None = None,
    dynasty_prospect_score: float = 0.0,
) -> str:
    """Assemble the report, then format it into a Claude Code scouting prompt."""
    from sleeper_ffm.prompts.prospect_scouting import build_prospect_scouting_prompt

    report = build_scouting_report(
        name=name,
        position=position,
        college=college,
        year=year,
        age=age,
        player_id=player_id,
        recruiting_rank=recruiting_rank,
        stars=stars,
        dynasty_prospect_score=dynasty_prospect_score,
    )
    return build_prospect_scouting_prompt(
        name=name,
        position=position,
        college=college,
        player_id=player_id,
        report=report,
    )
