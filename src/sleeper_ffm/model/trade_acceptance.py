"""Owner-specific trade offer recommendations and acceptance scoring."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import DEFAULT_VALUE_SEASON, MY_ROSTER_ID
from sleeper_ffm.market.blend import pick_market_available
from sleeper_ffm.model.dynasty import PickAsset, value_pick
from sleeper_ffm.model.owner_dossier import OwnerDossier, build_dossier
from sleeper_ffm.model.owner_history import OwnerHistory, build_league_history
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

# Max offers that may feature the same GIVE player, so one asset doesn't get
# shopped to the whole league in the queue.
_MAX_OFFERS_PER_GIVE_PLAYER: int = 2

_NAME_RE = re.compile(r"[^a-z ]")
_PICK_LEG_RE = re.compile(r"^20\d\d R\d")
# Fallback demand shares when this league has no trade history yet.
_DEFAULT_LIQUIDITY: dict[str, float] = {"RB": 0.40, "WR": 0.32, "TE": 0.16, "QB": 0.12}


def _leg_position(leg: str, name_to_pos: dict[str, str]) -> str | None:
    """Classify one trade leg (a stored player name / pick / FAAB string)."""
    if "FAAB" in leg or leg.startswith("$"):
        return None
    if _PICK_LEG_RE.match(leg):
        return "PICK"
    return name_to_pos.get(_NAME_RE.sub("", leg.lower()).strip())


@ttl_cache()
def league_trade_intel() -> dict:
    """Learn how THIS league actually trades from its transaction history.

    Returns demand share by position (how coveted each position is as measured by
    real trade volume), how pick-centric the league is, and the sample size.
    Trade legs are stored as player names, resolved to positions via the dump.
    """
    with SleeperClient() as c:
        players = c.players()
    name_to_pos: dict[str, str] = {}
    for p in players.values():
        full_name = p.get("full_name")
        pos = p.get("position")
        if full_name and pos in _POSITIONS:
            name_to_pos[_NAME_RE.sub("", full_name.lower()).strip()] = pos

    seen: set[tuple] = set()
    pos_legs: dict[str, int] = dict.fromkeys(_POSITIONS, 0)
    pick_trades = 0
    total = 0
    for owner in build_league_history().owners:
        for trade in owner.trades:
            key = (
                trade.season,
                trade.week,
                tuple(sorted(trade.sent)),
                tuple(sorted(trade.received)),
            )
            if key in seen:
                continue
            seen.add(key)
            total += 1
            legs = [_leg_position(x, name_to_pos) for x in trade.sent + trade.received]
            if "PICK" in legs:
                pick_trades += 1
            for leg in legs:
                if leg in pos_legs:
                    pos_legs[leg] += 1

    player_total = sum(pos_legs.values())
    if total < 10 or player_total == 0:
        return {"liquidity": dict(_DEFAULT_LIQUIDITY), "pick_centric": 0.5, "sample": total}
    liquidity = {pos: round(pos_legs[pos] / player_total, 3) for pos in _POSITIONS}
    return {
        "liquidity": liquidity,
        "pick_centric": round(pick_trades / total, 2),
        "sample": total,
    }


def _acquire_premium(position: str, intel: dict) -> float:
    """Value multiple a coveted position commands to pry loose (RB > WR > TE > QB).

    Grounded in this league's real demand: the more a position is traded for, the
    more you must overpay to acquire one.
    """
    liquidity = intel["liquidity"].get(position, 0.25)
    return round(1.0 + 0.45 * liquidity, 3)


@dataclass
class TradeAsset:
    """A single player or pick in a recommended offer."""

    asset_id: str
    kind: str
    label: str
    position: str | None
    value: float


@dataclass
class TradeOfferRecommendation:
    """A concrete outgoing offer with partner-specific acceptance context."""

    partner_roster_id: int
    partner_name: str
    acceptance_score: int
    confidence: str
    priority: int
    give: list[TradeAsset]
    receive: list[TradeAsset]
    give_value: float
    receive_value: float
    value_delta: float
    target_need: str
    partner_need: str
    rationale: str
    command: str
    evidence_count: int
    calibration: str
    calibration_notes: str
    impact_score: float = 0.0
    impact_label: str = "LOW"


def _rank_map(dossier: OwnerDossier) -> dict[str, int]:
    """Return position -> league rank from an owner dossier."""
    return {rank.position: rank.rank for rank in dossier.position_ranks}


def _tier_map(dossier: OwnerDossier) -> dict[str, str]:
    """Return position -> depth tier from an owner dossier."""
    return {rank.position: rank.tier for rank in dossier.position_ranks}


def _need_positions(dossier: OwnerDossier) -> set[str]:
    """Positions where this roster is genuinely weak (worth acquiring at)."""
    return {r.position for r in dossier.position_ranks if r.tier in {"THIN", "AVERAGE"}}


# A received player must clear this blended value to count as a real upgrade
# rather than a depth flier — offers of two fliers are low-impact even if "fair".
_MEANINGFUL_RECEIVE: float = 100.0
_TRIVIAL_ASSET: float = 60.0


def _impact(
    receive_asset: TradeAsset,
    give_value: float,
    receive_value: float,
    my_needs: set[str],
) -> tuple[float, str]:
    """Score how much an offer actually improves the roster (vs merely being fair).

    The point of a trade is landing a real player at a real need; paying a premium
    is the cost of doing so. Impact rewards the caliber acquired at a need and
    penalizes overpay and trivial flier-for-flier swaps.
    """
    fills_need = (receive_asset.position or "") in my_needs
    impact = receive_value if fills_need else receive_value * 0.35
    impact -= 0.7 * max(0.0, give_value - receive_value)  # overpay penalty
    if receive_value < _TRIVIAL_ASSET:
        impact -= 30.0
    impact = round(impact, 1)
    label = "HIGH" if impact >= 90 else "MED" if impact >= 45 else "LOW"
    return impact, label


def _score_position_fit(
    my_dossier: OwnerDossier,
    partner: OwnerDossier,
    give_pos: str,
    receive_pos: str,
) -> int:
    """Score how well the proposed positions solve both rosters' needs."""
    my_ranks = _rank_map(my_dossier)
    partner_ranks = _rank_map(partner)
    league_size = max(partner.league_size, my_dossier.league_size, 1)

    # Higher rank = weaker position = more need. Lower rank = stronger = more surplus.
    # Default: partner unknown rank → assume worst (league_size); my rank → same.
    partner_need = partner_ranks.get(give_pos, league_size)
    my_surplus = max(0, league_size + 1 - my_ranks.get(give_pos, league_size))
    my_need = my_ranks.get(receive_pos, league_size)
    partner_surplus = max(0, league_size + 1 - partner_ranks.get(receive_pos, league_size))

    raw = partner_need + my_surplus + my_need + partner_surplus
    return min(30, round(raw * 1.1))


def _choose_position_pair(
    my_dossier: OwnerDossier,
    partner: OwnerDossier,
) -> tuple[str, str]:
    """Choose give/receive positions from surplus-vs-need ranks."""
    my_ranks = _rank_map(my_dossier)
    partner_ranks = _rank_map(partner)
    my_tiers = _tier_map(my_dossier)
    partner_tiers = _tier_map(partner)
    league_size = max(my_dossier.league_size, partner.league_size, 1)

    give_pos = max(
        _POSITIONS,
        key=lambda pos: (
            partner_ranks.get(pos, league_size) - my_ranks.get(pos, league_size),
            my_tiers.get(pos) in {"DEEP", "SOLID"},
            partner_tiers.get(pos) in {"THIN", "AVERAGE"},
        ),
    )
    # Only acquire where I am genuinely weak — don't chase a position I'm already
    # deep at just because the partner is deeper (e.g. buying a 2nd QB in 1QB).
    receive_candidates = [p for p in _POSITIONS if p in _need_positions(my_dossier)] or list(
        _POSITIONS
    )
    receive_pos = max(
        receive_candidates,
        key=lambda pos: (
            my_ranks.get(pos, league_size) - partner_ranks.get(pos, league_size),
            partner_tiers.get(pos) in {"DEEP", "SOLID"},
            my_tiers.get(pos) in {"THIN", "AVERAGE"},
        ),
    )
    return give_pos, receive_pos


def _player_candidates(dossier: OwnerDossier, position: str) -> list[dict]:
    """Return roster players at ``position`` sorted as tradeable candidates."""
    rows = [
        p
        for p in dossier.players
        if p["position"] == position and p["dynasty_value"] >= 15 and not p["is_taxi"]
    ]
    return sorted(
        rows,
        key=lambda p: (
            p["is_starter"],
            abs(float(p["dynasty_value"]) - 85),
            -float(p["dynasty_value"]),
        ),
    )


def _pick_sweetener(delta: float, my_dossier: OwnerDossier) -> TradeAsset | None:
    """Choose the smallest owned future pick that can close a value gap."""
    if delta <= 12:
        return None

    pick_rows: list[tuple[float, dict]] = []
    for pick in my_dossier.picks_owned:
        season = str(pick["season"])
        round_ = int(pick["round"])
        value = value_pick(
            PickAsset(
                season=season,
                round=round_,
                original_owner_id=MY_ROSTER_ID,
                current_owner_id=MY_ROSTER_ID,
            )
        )
        pick_rows.append((value, pick))

    if not pick_rows:
        return None

    pick_value, pick = min(
        pick_rows,
        key=lambda item: (abs(item[0] - min(delta, 55)), item[1]["round"]),
    )
    label = f"{pick['season']} R{pick['round']}"
    return TradeAsset(
        asset_id=f"{pick['season']}_R{pick['round']}",
        kind="pick",
        label=label,
        position=None,
        value=round(pick_value, 1),
    )


def _target_age_ceiling(position: str) -> float:
    """Return the oldest age worth chasing without a steep discount."""
    ceilings = {"QB": 34.0, "RB": 27.5, "WR": 29.5, "TE": 30.5}
    return ceilings.get(position, 29.5)


def _trade_asset(player: dict) -> TradeAsset:
    """Convert a dossier player row into a TradeAsset."""
    return TradeAsset(
        asset_id=player["player_id"],
        kind="player",
        label=f"{player['name']} ({player['position']} {player['team']})",
        position=player["position"],
        value=round(float(player["dynasty_value"]), 1),
    )


def _approachability_bonus(history: OwnerHistory | None) -> int:
    """Convert behavior history into an acceptance score adjustment."""
    if history is None:
        return 0
    bonus_by_label = {"OPEN": 15, "SELECTIVE": 8, "INSULAR": -4, "DORMANT": -12}
    bonus = bonus_by_label.get(history.approachability, 0)
    if "ACTIVE-TRADER" in history.behavioral_tags:
        bonus += 5
    if "PASSIVE" in history.behavioral_tags:
        bonus -= 5
    return bonus


def _calibration_context(history: OwnerHistory | None) -> tuple[str, int, str]:
    """Return evidence quality for interpreting an acceptance score."""
    if history is None:
        return "UNCALIBRATED", 0, "No owner transaction history available."
    evidence_count = history.trade_count
    if evidence_count >= 8:
        label = "OWNER-HISTORY"
    elif evidence_count >= 3:
        label = "LIMITED-HISTORY"
    else:
        label = "LOW-SAMPLE"
    notes = (
        f"{evidence_count} historical trade(s), {history.trades_per_season:.1f}/season, "
        f"{history.approachability.lower()} approachability"
    )
    return label, evidence_count, notes


def _window_bonus(
    partner: OwnerDossier,
    give_asset: TradeAsset,
    sweetener: TradeAsset | None,
) -> int:
    """Score whether the offer matches the partner's contention window."""
    label = partner.contention.label
    if label in {"CLOSING", "OPEN"} and give_asset.kind == "player":
        return 8
    if label in {"ASCENDING", "OPENING", "RETOOLING"} and sweetener is not None:
        return 8
    return 0


def _acceptance_score(
    my_dossier: OwnerDossier,
    partner: OwnerDossier,
    history: OwnerHistory | None,
    give_asset: TradeAsset,
    receive_asset: TradeAsset,
    sweetener: TradeAsset | None,
) -> tuple[int, str, str]:
    """Return acceptance score plus a compact rationale."""
    give_value = give_asset.value + (sweetener.value if sweetener else 0.0)
    margin_for_partner = give_value - receive_asset.value
    position_fit = _score_position_fit(
        my_dossier,
        partner,
        give_asset.position or "",
        receive_asset.position or "",
    )
    margin_score = round(max(-22, min(24, margin_for_partner * 0.35)))
    history_score = _approachability_bonus(history)
    window_score = _window_bonus(partner, give_asset, sweetener)
    sample_penalty = 0 if history and history.trade_count >= 3 else -4

    raw = 42 + position_fit + margin_score + history_score + window_score + sample_penalty
    score = max(5, min(98, round(raw)))
    confidence = "HIGH" if score >= 74 else "MED" if score >= 54 else "LOW"
    rationale = (
        f"{position_fit}/30 roster-fit, {margin_for_partner:+.1f} value margin, "
        f"{history.approachability if history else 'UNKNOWN'} approachability, "
        f"{partner.contention.label.lower()} window"
    )
    return score, confidence, rationale


def _command(give: list[TradeAsset], receive: TradeAsset, partner: OwnerDossier) -> str:
    """Format a concise command for the War Room queue."""
    give_text = " + ".join(asset.label for asset in give)
    return f"Offer {give_text} to {partner.display_name} for {receive.label}"


def _offer_for_partner(
    my_dossier: OwnerDossier,
    partner: OwnerDossier,
    history: OwnerHistory | None,
) -> TradeOfferRecommendation | None:
    """Build the best single offer for one partner, if a plausible fit exists."""
    give_pos, receive_pos = _choose_position_pair(my_dossier, partner)
    my_needs = _need_positions(my_dossier)

    # Realism: in a 1QB league QBs are a small slice of trade volume and only move
    # to a QB-needy partner — never as a throw-in to pry a starter loose.
    if give_pos == "QB" and "QB" not in _need_positions(partner):
        return None

    give_candidates = _player_candidates(my_dossier, give_pos)
    # Trade from surplus depth, never your cornerstone: keep the best asset at the
    # position you're "deep" at — you don't deal your franchise QB or elite TE to
    # fill another hole.
    cornerstone = max(
        (p["dynasty_value"] for p in my_dossier.players if p["position"] == give_pos),
        default=0.0,
    )
    give_candidates = [p for p in give_candidates if p["dynasty_value"] < cornerstone]
    receive_candidates = _player_candidates(partner, receive_pos)
    if not give_candidates or not receive_candidates:
        return None

    intel = league_trade_intel()
    premium = _acquire_premium(receive_pos, intel)

    best: TradeOfferRecommendation | None = None
    for give_player in give_candidates[:5]:
        give_asset = _trade_asset(give_player)
        for target in receive_candidates[:6]:
            receive_asset = _trade_asset(target)
            target_age = float(target["age"])
            if target_age > _target_age_ceiling(receive_asset.position or ""):
                continue
            receive_value = receive_asset.value

            # Realistic clears are fair-to-premium for the acquirer: pay up to pry a
            # coveted asset loose (picks are this league's currency), and the partner
            # must come out at least even or they won't move it.
            gap = round(receive_value * premium - give_asset.value, 1)
            sweetener = _pick_sweetener(gap, my_dossier) if gap > 12 else None
            if sweetener is not None and sweetener.asset_id.endswith("_R1") and target_age >= 27:
                continue
            give_assets = [give_asset] + ([sweetener] if sweetener else [])
            give_value = round(sum(asset.value for asset in give_assets), 1)
            if give_value < receive_value or give_value > receive_value * (premium + 0.35):
                continue
            value_delta = round(receive_value - give_value, 1)  # negative = I pay the premium

            acceptance, confidence, rationale = _acceptance_score(
                my_dossier,
                partner,
                history,
                give_asset,
                receive_asset,
                sweetener,
            )
            overpay = max(0.0, give_value - receive_value)
            demand_pct = round(intel["liquidity"].get(receive_pos, 0) * 100)
            rationale = (
                f"{rationale}; land {receive_asset.position} need at "
                f"{'a premium' if overpay > 5 else 'fair value'} "
                f"({receive_asset.position} is {demand_pct}% of this league's trades)"
            )
            priority = acceptance + round(max(-8, min(18, value_delta * 0.35)))
            impact_score, impact_label = _impact(
                receive_asset, give_value, receive_value, my_needs
            )
            calibration, evidence_count, calibration_notes = _calibration_context(history)
            if sweetener is not None and not pick_market_available():
                calibration_notes += (
                    " FantasyCalc pick market unavailable — the pick sweetener's "
                    "value uses the static fallback table, not live pricing."
                )
            offer = TradeOfferRecommendation(
                partner_roster_id=partner.roster_id,
                partner_name=partner.display_name,
                acceptance_score=acceptance,
                confidence=confidence,
                priority=priority,
                give=give_assets,
                receive=[receive_asset],
                give_value=give_value,
                receive_value=receive_value,
                value_delta=value_delta,
                target_need=receive_pos,
                partner_need=give_pos,
                rationale=rationale,
                command=_command(give_assets, receive_asset, partner),
                evidence_count=evidence_count,
                calibration=calibration,
                calibration_notes=calibration_notes,
                impact_score=impact_score,
                impact_label=impact_label,
            )
            if best is None or offer.impact_score > best.impact_score:
                best = offer

    return best


def recommend_trade_offers(
    top: int = 8,
    season: int = DEFAULT_VALUE_SEASON,
    my_roster_id: int = MY_ROSTER_ID,
    log_offers: bool = False,
) -> list[TradeOfferRecommendation]:
    """Return partner-specific outgoing trade offers sorted by priority.

    Read-only by default: this does NOT write to the offer log. Logging is an
    explicit action (``log_offers=True``, used only when the user acts on an
    offer) so that dashboard polling and eval runs never pollute the calibration
    log.

    Args:
        top: Maximum number of offers to return.
        season: NFL season to use for player valuation.
        my_roster_id: Current roster id to build offers from.
        log_offers: When True, append the returned offers to ``data/offers.jsonl``.

    Returns:
        Recommended offers sorted by acceptance-adjusted priority.
    """
    with SleeperClient() as client:
        roster_ids = [r.roster_id for r in client.rosters()]

    history_by_roster = {history.roster_id: history for history in build_league_history().owners}
    my_dossier = build_dossier(my_roster_id, season=season)

    offers: list[TradeOfferRecommendation] = []
    for roster_id in roster_ids:
        if roster_id == my_roster_id:
            continue
        partner = build_dossier(roster_id, season=season)
        offer = _offer_for_partner(
            my_dossier,
            partner,
            history_by_roster.get(roster_id),
        )
        if offer is not None:
            offers.append(offer)

    # Rank by roster impact first, then acceptance — a needle-moving trade a
    # partner might take beats a trivially "fair" swap they'd rubber-stamp.
    offers.sort(
        key=lambda offer: (-offer.impact_score, -offer.acceptance_score, offer.partner_name)
    )

    # Cap how many offers may feature the same GIVE player.
    capped: list[TradeOfferRecommendation] = []
    give_counts: dict[str, int] = {}
    for offer in offers:
        give_pid = offer.give[0].asset_id if offer.give else ""
        if give_counts.get(give_pid, 0) >= _MAX_OFFERS_PER_GIVE_PLAYER:
            continue
        give_counts[give_pid] = give_counts.get(give_pid, 0) + 1
        capped.append(offer)

    top_offers = capped[:top]

    if log_offers:
        _persist_offers(top_offers)

    return top_offers


def _persist_offers(offers: list[TradeOfferRecommendation]) -> None:
    """Append offers to the calibration log; never fatal to the caller."""
    try:
        import dataclasses
        from datetime import datetime

        from sleeper_ffm.model.offer_log import append_offers

        now = datetime.now(UTC).isoformat()
        append_offers([dataclasses.asdict(o) for o in offers], logged_at=now)
    except Exception as exc:
        log.warning("recommend_trade_offers: offer log write failed: %s", exc)
