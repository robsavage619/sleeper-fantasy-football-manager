"""Prospect scouting prompt builder.

Packs the full multi-source scouting report (market consensus, NFL draft
capital, athletic testing, college production, roster fit, derived signals)
into a deterministic prompt, then asks Claude Code to layer real analysis on
top: web-searched consensus/scouting, NFL comps grounded in the metrics, a
verdict, and risk factors. Same inputs → same prompt; Claude Code is the
non-deterministic reasoning layer.

Claude posts the finding back via ``sffm finding prospect_scout --body '<json>'``.
The body must echo the prospect's identity (``name`` + ``college``, and
``player_id`` when known) so the frontend can match it to the right row.
"""

from __future__ import annotations

from typing import Any


def build_prospect_scouting_prompt(
    *,
    name: str,
    position: str,
    college: str,
    player_id: str | None,
    report: dict[str, Any],
) -> str:
    """Build a deep-dive scouting prompt from an assembled report dict."""
    market_lines = _format_market(report.get("market"))
    capital_lines = _format_capital(report.get("draft_capital"))
    athletic_lines = _format_athletic(report.get("athleticism"))
    college_lines = _format_college(report.get("college"))
    fit_lines = _format_roster_fit(report.get("roster_fit"), position)
    signal_lines = _format_signals(report.get("signals", []))

    return f"""# Prospect Scouting — {name} ({position}, {college})

## Structured Signals (this app's data)
{signal_lines}

## Market Consensus (FantasyCalc — real dynasty trade market)
{market_lines}

## NFL Draft Capital
{capital_lines}

## Athletic Profile (NFL Combine)
{athletic_lines}

## College Production (ESPN box scores, per season)
{college_lines}

## Fit For My Roster
{fit_lines}

## Your Task
You are a professional dynasty fantasy football analyst competing in one of the
hardest, most competitive leagues in the country. The structured data above is
real but incomplete — it has no scouting tape, no landing-spot depth-chart
context, and only one market source. Fill those gaps, then deliver a verdict.

0. **Search the web first.** Use WebSearch/WebFetch to pull, for {name}:
   - Current consensus dynasty rookie rank from 2+ sources (KeepTradeCut,
     DynastyLeagueFootball, FantasyPros) — cross-check against the FantasyCalc
     rank above; flag disagreement.
   - Recent scouting themes (NFL.com, The Draft Network, PFF public, Reception
     Perception / analytics writers) — summarize, don't quote at length.
   - Landing-spot context: current depth chart, target/touch competition, and
     scheme fit on their NFL team.
   Name the sites you actually found real info on; say so plainly if a search
   is empty rather than inventing a source.
1. **NFL comps** — 2-3 current/recent NFL players whose athletic profile,
   draft capital, and (if available) college production most resemble this
   prospect. Justify each with the SPECIFIC metrics above, not reputation.
2. **Verdict** — dynasty tier (ELITE / STARTER / DEPTH / SPECULATIVE) + a
   one-paragraph bust/hit case that reconciles the market rank, draft capital,
   athleticism, and what you found on the web.
3. **Team fit** — using the roster-fit + timeline context, state plainly
   whether this player fills a real need on my roster or is a luxury/upside
   swing given my contention window.
4. **Risk factors** — the 2-3 things most likely to sink the NFL outlook
   (target/touch competition, scheme, athletic red flags, injury, age).

Post your finding via:
``sffm finding prospect_scout --body '<json>'``
with JSON keys: ``player_id`` (echo {player_id!r}), ``name`` (echo {name!r}),
``college`` (echo {college!r}), ``comps`` (list of
``{{"name": str, "rationale": str}}``), ``verdict`` (tier string), ``case``
(bust/hit paragraph), ``team_fit`` (string), ``risk_notes`` (list of strings),
``consensus_check`` (string: how web ranks compare to FantasyCalc), ``sources``
(list of sites you actually found real info on; may be empty).
"""


def _format_signals(signals: list[dict]) -> str:
    if not signals:
        return "  (no derived signals)"
    return "\n".join(f"  - [{s['tone']}] {s['label']}: {s['detail']}" for s in signals)


def _format_market(market: dict | None) -> str:
    if not market:
        return "  (no FantasyCalc market match for this player)"
    lines = [
        f"  Dynasty value: {market.get('value')} (overall #{market.get('overall_rank')}, "
        f"positional #{market.get('position_rank')}, tier {market.get('tier')})"
    ]
    if market.get("trend_30day") is not None:
        lines.append(f"  30-day trend: {market['trend_30day']:+d}")
    if market.get("player_timeline"):
        lines.append(
            f"  Timeline: {market['player_timeline']} "
            f"(dynasty premium {market.get('dynasty_premium_pct')}% over redraft)"
        )
    if market.get("roster_pct") is not None:
        lines.append(
            f"  Rostered {market['roster_pct'] * 100:.0f}% of leagues; "
            f"trade frequency {market.get('trade_frequency')}"
        )
    if market.get("volatility_pct"):
        lines.append(f"  Market volatility: {market['volatility_pct']}% (disagreement)")
    return "\n".join(lines)


def _format_capital(cap: dict | None) -> str:
    if not cap or not cap.get("round"):
        return "  (undrafted / no draft capital on record)"
    pick = f" (pick {cap['pick']})" if cap.get("pick") else ""
    team = f" to {cap['team']}" if cap.get("team") else ""
    tier = cap.get("capital_tier")
    return f"  {tier}: Round {cap['round']}{pick}{team}, {cap.get('year')} NFL Draft"


def _format_athletic(ath: dict | None) -> str:
    if not ath:
        return "  (no combine data — did not test or not in dataset)"
    parts = []
    if ath.get("height_in"):
        parts.append(f"{ath['height_in'] // 12}'{ath['height_in'] % 12}\"")
    if ath.get("weight"):
        parts.append(f"{ath['weight']} lbs")
    if ath.get("forty"):
        parts.append(f"{ath['forty']} forty")
    if ath.get("vertical"):
        parts.append(f'{ath["vertical"]}" vert')
    if ath.get("bench"):
        parts.append(f"{ath['bench']} bench")
    if ath.get("broad_jump"):
        parts.append(f'{ath["broad_jump"]}" broad')
    line = "  " + ", ".join(parts) if parts else "  (measurables incomplete)"
    if ath.get("speed_score") or ath.get("athletic_grade"):
        line += (
            f"\n  Speed score {ath.get('speed_score')} · "
            f"forty-based grade {ath.get('athletic_grade')}"
        )
    return line


def _format_college(college: dict | None) -> str:
    if not college or not college.get("has_data"):
        return "  (no college production data found)"
    lines = []
    for row in college["seasons"]:
        parts = []
        rec = row.get("receiving")
        if rec:
            parts.append(
                f"{rec['receptions']} rec / {rec['yards']} yds / "
                f"{rec['touchdowns']} TD ({rec['ypr']} YPR)"
            )
        rush = row.get("rushing")
        if rush:
            parts.append(
                f"{rush['carries']} car / {rush['yards']} yds / "
                f"{rush['touchdowns']} TD ({rush['ypc']} YPC)"
            )
        passing = row.get("passing")
        if passing:
            parts.append(
                f"{passing['yards']} pass yds / {passing['touchdowns']} TD / "
                f"{passing['interceptions']} INT / {passing['comp_pct']}% ({passing['ypa']} YPA)"
            )
        lines.append(f"  {row['season']}: {'; '.join(parts)}")
    if college.get("recruiting_rank"):
        lines.append(
            f"  Recruiting: #{college['recruiting_rank']} national, {college.get('stars')}-star"
        )
    return "\n".join(lines)


def _format_roster_fit(fit: dict | None, position: str) -> str:
    if not fit:
        return "  (roster fit unavailable)"
    lines = []
    if fit.get("position_rank") is not None:
        lines.append(
            f"  My {position} depth ranks #{fit['position_rank']} of {fit['position_of']} "
            f"(tier {fit['position_tier']}, league avg {fit['position_league_avg']})"
        )
    lines.append(
        f"  Contention window: {fit.get('contention_label')} "
        f"({fit.get('contention_window')}) — {fit.get('contention_rationale')}"
    )
    if fit.get("timeline_verdict"):
        lines.append(f"  Timeline fit: {fit['timeline_verdict']}")
    return "\n".join(lines)
