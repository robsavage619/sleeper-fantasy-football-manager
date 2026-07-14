"""Contention-window classifier — who's a buyer and who's a seller, right now.

A trade is only good if the *other* side wants what you're selling. This module labels
every roster's competitive window by combining two signals it already has cheaply:

    * **Now** — playoff/title odds from the Monte-Carlo season simulator
      (:mod:`sleeper_ffm.model.season_sim`): how good the team is this season.
    * **Trajectory** — the age profile of its core (weighted core age and the share of
      value tied up in under-25 players): whether that strength is rising or aging out.

The cross of those two gives the classic four windows plus a neutral middle, and — the
actionable part — what each team *should* be buying or selling. Sell your aging RB to a
WIN-NOW team; pry a productive vet from a REBUILD team for picks; don't bother offering
win-now help to a RETOOL team hoarding youth.

Pick capital is a deliberate omission for now (it lives behind the per-league
``traded_picks`` walk); odds + age capture window direction well on their own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, MY_ROSTER_ID

log = logging.getLogger(__name__)

# Core = the top-value players that actually define a roster's window.
_CORE_SIZE: int = 10
# A player at or under this age counts toward the "young core" value share.
_YOUNG_AGE: float = 25.0
# Odds thresholds separating contenders / muddled middle / also-rans.
_CONTENDER_ODDS: float = 0.55
_PRETENDER_ODDS: float = 0.30
# A roster is "young" if its youth value share clears this or its core is this young.
_YOUNG_SHARE: float = 0.50
_YOUNG_CORE_AGE: float = 25.5


@dataclass
class ContentionWindow:
    """One roster's competitive window and what it should trade for."""

    roster_id: int
    label: str  # WIN-NOW | SUSTAIN | RETOOL | REBUILD | HOLD
    playoff_odds: float
    title_odds: float
    core_age: float  # value-weighted average age of the core
    young_share: float  # fraction of core value in under-25 players
    strength: float
    seeking: str  # what this team wants in trades
    shedding: str  # what this team should move
    rationale: str
    is_me: bool = False


@dataclass
class ContentionBoard:
    """League-wide contention windows, contenders first."""

    season: int
    windows: list[ContentionWindow]
    warnings: list[str] = field(default_factory=list)


def classify_window(
    title_odds: float,
    playoff_odds: float,
    core_age: float,
    young_share: float,
) -> tuple[str, str, str, str]:
    """Classify a window from odds + age. Pure.

    Returns:
        ``(label, seeking, shedding, rationale)``.
    """
    young = young_share >= _YOUNG_SHARE or core_age <= _YOUNG_CORE_AGE
    contender = playoff_odds >= _CONTENDER_ODDS
    pretender = playoff_odds <= _PRETENDER_ODDS

    if contender and not young:
        return (
            "WIN-NOW",
            "immediate-impact starters, proven vets",
            "future picks, developmental youth",
            f"{playoff_odds:.0%} playoff odds with an aging core (avg {core_age:.1f}) — "
            "the window is open now and closing; push chips in.",
        )
    if contender and young:
        return (
            "SUSTAIN",
            "selective upgrades, depth",
            "little — mostly holds",
            f"{playoff_odds:.0%} playoff odds with a young core (avg {core_age:.1f}) — "
            "the best seat in the league; contend now and keep the window open.",
        )
    if pretender and young:
        return (
            "RETOOL",
            "picks, more young talent, buy-low upside",
            "any aging vets for future value",
            f"only {playoff_odds:.0%} playoff odds but a young core (avg {core_age:.1f}) — "
            "ascending; accumulate and let it mature.",
        )
    if pretender and not young:
        return (
            "REBUILD",
            "picks and youth for anything",
            "every productive veteran on the roster",
            f"{playoff_odds:.0%} playoff odds and an aging core (avg {core_age:.1f}) — "
            "tear it down; sell vets before they depreciate.",
        )
    return (
        "HOLD",
        "value that clearly improves the team",
        "redundant depth only",
        f"middling odds ({playoff_odds:.0%}) — no decisive lean; stay flexible.",
    )


def _core_profile(values_ages: list[tuple[float, float]]) -> tuple[float, float]:
    """Return ``(value_weighted_core_age, young_value_share)`` for a roster's core.

    Args:
        values_ages: ``[(value, age), ...]`` for all rostered players.

    Returns:
        Value-weighted average age of the top-``_CORE_SIZE`` by value, and the fraction
        of that core's value held by under-25 players. ``(0.0, 0.0)`` if empty.
    """
    core = sorted(values_ages, key=lambda va: va[0], reverse=True)[:_CORE_SIZE]
    total_val = sum(v for v, _ in core)
    if total_val <= 0:
        return 0.0, 0.0
    weighted_age = sum(v * a for v, a in core) / total_val
    young_val = sum(v for v, a in core if a <= _YOUNG_AGE)
    return round(weighted_age, 1), round(young_val / total_val, 3)


def build_contention(n_sims: int = 2000) -> ContentionBoard:
    """Classify every roster's contention window.

    Returns:
        A :class:`ContentionBoard` sorted contenders-first. Degrades gracefully.
    """
    from sleeper_ffm.model.dynasty import value_player
    from sleeper_ffm.model.season_sim import build_season_sim
    from sleeper_ffm.model.valuation import build_player_assets
    from sleeper_ffm.sleeper.client import SleeperClient

    warnings: list[str] = []
    with SleeperClient() as c:
        rosters = c.rosters()
        players = c.players()

    try:
        assets = build_player_assets(seasons=[DEFAULT_VALUE_SEASON], sleeper_players=players)
        val_age = {a.player_id: (value_player(a), a.age) for a in assets}
    except Exception as exc:
        log.warning("contention: player assets unavailable: %s", exc)
        warnings.append("Player assets unavailable; core-age profile degraded.")
        val_age = {}

    try:
        sim = build_season_sim(n_sims=n_sims)
        odds = {t.roster_id: t for t in sim.teams}
    except Exception as exc:
        log.warning("contention: season sim unavailable: %s", exc)
        warnings.append("Season simulation unavailable; odds default to neutral.")
        odds = {}

    windows: list[ContentionWindow] = []
    for r in rosters:
        roster_val_ages = [val_age[pid] for pid in (r.players or []) if pid in val_age]
        core_age, young_share = _core_profile(roster_val_ages)
        team_odds = odds.get(r.roster_id)
        playoff = team_odds.playoff_odds if team_odds else 0.5
        title = team_odds.title_odds if team_odds else 0.0
        strength = team_odds.strength if team_odds else 0.0
        label, seeking, shedding, rationale = classify_window(
            title, playoff, core_age or 27.0, young_share
        )
        windows.append(
            ContentionWindow(
                roster_id=r.roster_id,
                label=label,
                playoff_odds=round(playoff, 4),
                title_odds=round(title, 4),
                core_age=core_age,
                young_share=young_share,
                strength=strength,
                seeking=seeking,
                shedding=shedding,
                rationale=rationale,
                is_me=(r.roster_id == MY_ROSTER_ID),
            )
        )

    windows.sort(key=lambda w: w.playoff_odds, reverse=True)
    return ContentionBoard(season=DEFAULT_VALUE_SEASON, windows=windows, warnings=warnings)
