"""Owner-specific trade offer recommendations and acceptance scoring."""

from __future__ import annotations

from dataclasses import dataclass

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, MY_ROSTER_ID
from sleeper_ffm.model.dynasty import PickAsset, value_pick
from sleeper_ffm.model.owner_dossier import OwnerDossier, build_dossier
from sleeper_ffm.model.owner_history import OwnerHistory, build_league_history
from sleeper_ffm.sleeper.client import SleeperClient

_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")


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


def _rank_map(dossier: OwnerDossier) -> dict[str, int]:
    """Return position -> league rank from an owner dossier."""
    return {rank.position: rank.rank for rank in dossier.position_ranks}


def _tier_map(dossier: OwnerDossier) -> dict[str, str]:
    """Return position -> depth tier from an owner dossier."""
    return {rank.position: rank.tier for rank in dossier.position_ranks}


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

    partner_need = max(0, league_size + 1 - partner_ranks.get(give_pos, league_size))
    my_surplus = max(0, league_size + 1 - my_ranks.get(give_pos, league_size))
    my_need = max(0, league_size + 1 - my_ranks.get(receive_pos, league_size))
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
    receive_pos = max(
        _POSITIONS,
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
    give_candidates = _player_candidates(my_dossier, give_pos)
    receive_candidates = _player_candidates(partner, receive_pos)
    if not give_candidates or not receive_candidates:
        return None

    best: TradeOfferRecommendation | None = None
    for give_player in give_candidates[:5]:
        give_asset = _trade_asset(give_player)
        for target in receive_candidates[:6]:
            receive_asset = _trade_asset(target)
            target_age = float(target["age"])
            if target_age > _target_age_ceiling(receive_asset.position or ""):
                continue
            if give_asset.value > receive_asset.value * 1.25:
                continue

            sweetener = _pick_sweetener(receive_asset.value - give_asset.value, my_dossier)
            if sweetener is not None and sweetener.asset_id.endswith("_R1") and target_age >= 27:
                continue
            give_assets = [give_asset] + ([sweetener] if sweetener else [])
            give_value = round(sum(asset.value for asset in give_assets), 1)
            receive_value = receive_asset.value
            value_delta = round(receive_value - give_value, 1)
            if value_delta < 0 or value_delta > 65:
                continue

            acceptance, confidence, rationale = _acceptance_score(
                my_dossier,
                partner,
                history,
                give_asset,
                receive_asset,
                sweetener,
            )
            priority = acceptance + round(max(-8, min(18, value_delta * 0.35)))
            calibration, evidence_count, calibration_notes = _calibration_context(history)
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
            )
            if best is None or offer.priority > best.priority:
                best = offer

    return best


def recommend_trade_offers(
    top: int = 8,
    season: int = DEFAULT_VALUE_SEASON,
    my_roster_id: int = MY_ROSTER_ID,
) -> list[TradeOfferRecommendation]:
    """Return partner-specific outgoing trade offers sorted by priority.

    Args:
        top: Maximum number of offers to return.
        season: NFL season to use for player valuation.
        my_roster_id: Current roster id to build offers from.

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

    offers.sort(key=lambda offer: (-offer.priority, -offer.acceptance_score, offer.partner_name))
    return offers[:top]
