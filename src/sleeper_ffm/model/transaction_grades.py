"""Transaction grades — letter-grade every league trade and waiver claim, on the curve.

Composes machinery that already exists for other purposes into a graded ledger:

* ``owner_history._fetch_season_transactions`` — the same full-history season/week walk
  ``faab_market`` and ``owner_history`` already use.
* ``faab_market.build_faab_market`` — this league's real winning-bid distribution by
  position, so a claim's price can be read as "the Nth percentile paid this league has
  ever seen for a WR", not against an invented external tier.
* ``report_card``'s rank-based letter ladder (``_rank_desc`` / ``_grade_for_rank``) — the
  same on-the-curve grading the league report card already uses, so a waiver-claim grade
  and a report-card grade mean the same thing.
* Realized points from ``matchups[*]["players_points"]``, the same ground truth
  ``transaction_value.py`` uses — reimplemented here across *every* season rather than
  just the latest, since grading is a whole-history feature.

Grading rubric
--------------
**Waiver / free-agent claim**: ``surplus = realized_points - bid * league_points_per_dollar``,
where ``league_points_per_dollar`` is computed once per season from that season's own
graded claims (total realized points / total dollars bid) — self-calibrating, no external
assumption about what a FAAB dollar buys in this league. A $0 free-agent claim has no
expected-cost baseline to beat, so its full realized total counts as surplus. Surpluses are
then curve-graded against every other graded claim *in the same season*.

**Trade** (graded per side): ``net_points`` = realized points of players received minus
players sent, since the trade through end of season. Curve-graded against every other
traded side in the same season. Draft picks are counted but not priced into ``net_points``
(the same honest win-now lens ``evals/trade_retro.py`` uses — a rebuild trade for picks can
legitimately grade poorly here without being a bad trade). A ``dynasty_delta`` annotation
(today's dynasty value of received players minus sent players, via
``model.dynasty.value_player`` — picks not priced) is attached for context and is always
labeled as a *current* value, never used in the grade itself.

**Settling**: a current-season move with fewer than ``_SETTLING_WEEKS`` completed weeks
since it happened is flagged ``settling=True`` — the grade is shown but should be read as
provisional, mirroring ``rec_scoreboard``'s PENDING honesty for recent recommendations.

Known biases, stated rather than hidden:

* Realized points favor earlier-season moves (more weeks left to accrue). Curve-ranking
  within the same season limits this to "who moved best given the same remaining season",
  not a cross-season comparison, but does not eliminate it within a season.
* Only *winning* FAAB bids are ever visible from Sleeper's API (see
  ``faab_market`` docstring) — ``bid_percentile`` is a clearing-price floor, not a full
  auction reconstruction.
* A single graded move in a thin season grades A+ by construction (``report_card``'s own
  rank-ladder behavior for n<=1) — a real limitation of on-the-curve grading with a small
  sample, not special-cased away here.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

import httpx

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import LEAGUE_ID
from sleeper_ffm.model.owner_history import _fetch_season_transactions
from sleeper_ffm.model.report_card import _grade_for_rank, _rank_desc
from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

_MAX_WEEK = 18
_WAIVER_METHODS = ("waiver", "free_agent")
_SETTLING_WEEKS = 4
# A started week scoring at/above this line counts as "startable" — same bar
# rec_scoreboard.py uses to grade whether a recommended waiver add panned out.
_STARTABLE_FP = 12.0
# GPA scale matching report_card._LETTERS exactly (A+ down to D, no F — this league's
# ladder never fails a move, it just ranks it at the bottom).
_GPA_SCALE = {
    "A+": 4.3,
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D": 1.0,
}


@dataclass
class WaiverGrade:
    """One graded waiver/free-agent claim."""

    season: str
    week: int
    roster_id: int
    owner_name: str
    player_id: str
    player_name: str
    position: str
    bid: int
    bid_percentile: float | None  # fraction of this position's winning bids <= this bid
    realized_points: float
    startable_weeks: int
    surplus: float
    grade: str
    settling: bool


@dataclass
class TradeSideGrade:
    """One side of a graded trade."""

    season: str
    week: int
    roster_id: int
    owner_name: str
    partner_roster_id: int
    partner_name: str
    received: list[dict] = field(default_factory=list)  # [{player_id, name, points}]
    sent: list[dict] = field(default_factory=list)
    picks_received: int = 0
    picks_sent: int = 0
    net_points: float = 0.0
    dynasty_delta: float | None = None  # today's value, context only — never graded on
    grade: str = ""
    settling: bool = False


@dataclass
class OwnerGpa:
    """One manager's transaction GPA across every graded move."""

    roster_id: int
    owner_name: str
    gpa: float
    n_moves: int
    best_move: str
    worst_move: str


@dataclass
class TransactionGradeBook:
    """The full graded transaction ledger."""

    seasons_covered: list[str]
    waiver_grades: list[WaiverGrade] = field(default_factory=list)
    trade_grades: list[TradeSideGrade] = field(default_factory=list)
    gpa: list[OwnerGpa] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --- pure grading pieces --------------------------------------------------------------


def bid_percentile(position: str, bid: int, market_bids: list) -> float | None:
    """Fraction of this position's historical winning bids at or below ``bid``.

    ``market_bids`` is :attr:`~sleeper_ffm.model.faab_market.FaabMarket.bids` (every
    winning ``WaiverBid`` this league has ever recorded). Returns None when the position
    has too thin a sample to trust — a percentile of 3 data points isn't a real signal.

    Args:
        position: Player position (QB/RB/WR/TE).
        bid: The FAAB dollars paid.
        market_bids: Every historical winning bid, any position.

    Returns:
        A value in ``[0, 1]``, or None if the position has fewer than 5 recorded bids.
    """
    from sleeper_ffm.model.faab_market import _MIN_BIDS_FOR_PERCENTILES

    same_pos = [b.bid for b in market_bids if b.position == position]
    if len(same_pos) < _MIN_BIDS_FOR_PERCENTILES:
        return None
    return round(sum(1 for b in same_pos if b <= bid) / len(same_pos), 3)


def league_points_per_dollar(bids: list[int], realized: list[float]) -> float:
    """This season's own realized-points-per-FAAB-dollar rate, from its own claims.

    Self-calibrating: no external assumption about what a dollar buys here. Zero-bid
    (free-agent) claims contribute points but not to the divisor, so they don't distort
    the rate paid claims are judged against.
    """
    total_bid = sum(bids)
    if total_bid <= 0:
        return 0.0
    return sum(realized) / total_bid


def claim_surplus(realized_points: float, bid: int, league_rate: float) -> float:
    """Points a claim returned above what its FAAB spend would 'expect' to buy.

    A $0 claim has no expected-cost baseline to beat, so its full realized total is
    surplus.
    """
    return round(realized_points - bid * league_rate, 1)


def grade_on_curve(values: dict[int, float]) -> dict[int, str]:
    """Letter-grade each entry against the others in ``values`` (higher = better).

    A thin wrapper over :mod:`~sleeper_ffm.model.report_card`'s rank ladder, so a
    transaction grade and a report-card grade mean exactly the same thing: rank ``k`` of
    ``n`` on this league's curve.
    """
    ranks = _rank_desc(values)
    n = len(values)
    return {key: _grade_for_rank(rank, n) for key, rank in ranks.items()}


def letter_gpa(letters: list[str]) -> float:
    """Mean GPA (4.3 scale) across a set of letter grades. 0.0 for an empty list."""
    if not letters:
        return 0.0
    return round(statistics.mean(_GPA_SCALE.get(g, 2.0) for g in letters), 2)


def is_settling(season: str, week: int, current_season: str, current_week: int) -> bool:
    """Whether a move is still too recent to be graded confidently.

    A move is provisional if it's in the current season and fewer than
    :data:`_SETTLING_WEEKS` completed weeks have passed since it happened.
    """
    if season != current_season:
        return False
    return (current_week - week) < _SETTLING_WEEKS


# --- assembly (pure: takes pre-fetched observations, no I/O) --------------------------


@dataclass
class _WaiverObservation:
    """One waiver/FA claim's raw facts, before grading."""

    season: str
    week: int
    roster_id: int
    owner_name: str
    player_id: str
    player_name: str
    position: str
    bid: int
    realized_points: float
    startable_weeks: int


@dataclass
class _TradeObservation:
    """One side of one trade's raw facts, before grading."""

    season: str
    week: int
    roster_id: int
    owner_name: str
    partner_roster_id: int
    partner_name: str
    received: list[dict]
    sent: list[dict]
    picks_received: int
    picks_sent: int
    net_points: float
    dynasty_delta: float | None


def assemble_waiver_grades(
    obs: list[_WaiverObservation],
    market_bids: list,
    current_season: str,
    current_week: int,
) -> list[WaiverGrade]:
    """Grade a batch of waiver observations against each other — one season's curve.

    Pure: no network, no clock (``current_season``/``current_week`` are passed in).
    """
    if not obs:
        return []
    rate = league_points_per_dollar([o.bid for o in obs], [o.realized_points for o in obs])
    surpluses = {i: claim_surplus(o.realized_points, o.bid, rate) for i, o in enumerate(obs)}
    letters = grade_on_curve(surpluses)
    return [
        WaiverGrade(
            season=o.season,
            week=o.week,
            roster_id=o.roster_id,
            owner_name=o.owner_name,
            player_id=o.player_id,
            player_name=o.player_name,
            position=o.position,
            bid=o.bid,
            bid_percentile=bid_percentile(o.position, o.bid, market_bids),
            realized_points=o.realized_points,
            startable_weeks=o.startable_weeks,
            surplus=surpluses[i],
            grade=letters[i],
            settling=is_settling(o.season, o.week, current_season, current_week),
        )
        for i, o in enumerate(obs)
    ]


def assemble_trade_grades(
    obs: list[_TradeObservation],
    current_season: str,
    current_week: int,
) -> list[TradeSideGrade]:
    """Grade a batch of trade-side observations against each other — one season's curve.

    Pure: no network, no clock.
    """
    if not obs:
        return []
    nets = {i: o.net_points for i, o in enumerate(obs)}
    letters = grade_on_curve(nets)
    return [
        TradeSideGrade(
            season=o.season,
            week=o.week,
            roster_id=o.roster_id,
            owner_name=o.owner_name,
            partner_roster_id=o.partner_roster_id,
            partner_name=o.partner_name,
            received=o.received,
            sent=o.sent,
            picks_received=o.picks_received,
            picks_sent=o.picks_sent,
            net_points=o.net_points,
            dynasty_delta=o.dynasty_delta,
            grade=letters[i],
            settling=is_settling(o.season, o.week, current_season, current_week),
        )
        for i, o in enumerate(obs)
    ]


def build_gpa_table(
    waiver_grades: list[WaiverGrade], trade_grades: list[TradeSideGrade]
) -> list[OwnerGpa]:
    """Roll every graded move up into a per-manager GPA, ranked best to worst. Pure."""
    by_owner: dict[int, list[tuple[str, str]]] = {}
    names: dict[int, str] = {}
    for w in waiver_grades:
        names[w.roster_id] = w.owner_name
        one_liner = f"{w.player_name} waiver ({w.season} wk{w.week}, {w.grade})"
        by_owner.setdefault(w.roster_id, []).append((w.grade, one_liner))
    for t in trade_grades:
        names[t.roster_id] = t.owner_name
        one_liner = f"trade w/ {t.partner_name} ({t.season} wk{t.week}, {t.grade})"
        by_owner.setdefault(t.roster_id, []).append((t.grade, one_liner))

    out: list[OwnerGpa] = []
    for rid, moves in by_owner.items():
        letters = [g for g, _ in moves]
        ranked = sorted(moves, key=lambda m: _GPA_SCALE.get(m[0], 2.0), reverse=True)
        out.append(
            OwnerGpa(
                roster_id=rid,
                owner_name=names.get(rid, str(rid)),
                gpa=letter_gpa(letters),
                n_moves=len(moves),
                best_move=ranked[0][1],
                worst_move=ranked[-1][1],
            )
        )
    out.sort(key=lambda o: -o.gpa)
    return out


# --- live builder (I/O) ----------------------------------------------------------------


def _player_name(players_dump: dict, pid: str) -> str:
    p = players_dump.get(pid) or {}
    return p.get("full_name") or p.get("search_full_name") or f"Player {pid}"


@ttl_cache()
def build_transaction_grades(league_id: str = LEAGUE_ID) -> TransactionGradeBook:
    """Walk every season's transactions and grade every waiver claim and trade side.

    The most expensive builder in the model layer — a full-history transaction *and*
    matchups walk, one season at a time — so it is TTL-cached like its siblings
    (``build_faab_market``, ``build_league_history``).

    Args:
        league_id: Current-season Sleeper league ID.

    Returns:
        A :class:`TransactionGradeBook`. Degrades per-season on fetch failure (a visible
        warning, not a silent drop) rather than failing the whole ledger.
    """
    from sleeper_ffm.model.faab_market import build_faab_market

    warnings: list[str] = []
    market = build_faab_market(league_id=league_id)

    with SleeperClient(league_id=league_id) as client:
        seasons = client.league_history(league_id=league_id)
        if not seasons:
            return TransactionGradeBook(seasons_covered=[], warnings=["No league history."])

        current_league = seasons[0]
        current_season = current_league.season or current_league.league_id
        current_rosters = client.rosters(league_id=current_league.league_id)
        user_to_current = {r.owner_id or "": r.roster_id for r in current_rosters}
        current_users = {
            u.user_id: (u.display_name or u.user_id) for u in client.users(current_league.league_id)
        }
        name_by_current = {
            user_to_current.get(r.owner_id or "", r.roster_id): current_users.get(
                r.owner_id or "", str(r.roster_id)
            )
            for r in current_rosters
        }
        players_dump = client.players()
        try:
            current_week = int(client.state_nfl().week or 0)
        except Exception:  # off-season / state hiccup
            current_week = 0

        vet_values: dict[str, float] = {}
        try:
            from sleeper_ffm.config import DEFAULT_VALUE_SEASON
            from sleeper_ffm.model.dynasty import value_player
            from sleeper_ffm.model.valuation import build_player_assets_cached

            assets = build_player_assets_cached(
                seasons=[DEFAULT_VALUE_SEASON], sleeper_players=players_dump
            )
            vet_values = {a.player_id: value_player(a) for a in assets}
        except Exception as exc:
            log.warning("transaction_grades: dynasty values unavailable (%s)", exc)
            warnings.append("Dynasty-value annotations unavailable this run.")

        seasons_covered: list[str] = []
        all_waiver_grades: list[WaiverGrade] = []
        all_trade_grades: list[TradeSideGrade] = []

        for league in seasons:
            season_str = league.season or league.league_id
            try:
                season_rosters = client.rosters(league_id=league.league_id)
            except httpx.HTTPError as exc:
                log.warning("transaction_grades: roster fetch failed for %s: %s", season_str, exc)
                warnings.append(f"{season_str}: roster fetch failed, skipped.")
                continue

            season_to_current: dict[int, int] = {}
            for r in season_rosters:
                cur = user_to_current.get(r.owner_id or "")
                if cur is not None:
                    season_to_current[r.roster_id] = cur

            try:
                txns = _fetch_season_transactions(client, league.league_id)
            except httpx.HTTPError as exc:
                log.warning(
                    "transaction_grades: transaction walk failed for %s: %s", season_str, exc
                )
                warnings.append(f"{season_str}: transaction walk failed, skipped.")
                continue

            matchups_by_week: dict[int, dict[int, dict]] = {}
            for wk in range(1, _MAX_WEEK + 1):
                try:
                    mus = client.matchups(wk, league_id=league.league_id)
                except httpx.HTTPError:
                    mus = []
                matchups_by_week[wk] = {
                    m["roster_id"]: (m.get("players_points") or {}) for m in mus
                }
            if not any(matchups_by_week.values()):
                continue  # nothing played yet this season — nothing to grade

            seasons_covered.append(season_str)

            def points_and_startable(
                pid: str, roster_id: int, from_week: int, _mbw=matchups_by_week
            ) -> tuple[float, int]:
                total = 0.0
                startable = 0
                for wk in range(from_week, _MAX_WEEK + 1):
                    v = _mbw.get(wk, {}).get(roster_id, {}).get(pid)
                    if v is not None:
                        total += v
                        if v >= _STARTABLE_FP:
                            startable += 1
                return round(total, 1), startable

            waiver_obs: list[_WaiverObservation] = []
            trade_obs: list[_TradeObservation] = []

            for txn in txns:
                typ = txn.get("type") or ""
                week = int(txn.get("leg") or 0)
                if typ in _WAIVER_METHODS:
                    bid = int((txn.get("settings") or {}).get("waiver_bid", 0) or 0)
                    for pid, season_roster in (txn.get("adds") or {}).items():
                        cur = season_to_current.get(season_roster)
                        if cur is None:
                            continue
                        position = players_dump.get(pid, {}).get("position")
                        if position not in SKILL_POSITIONS:
                            continue
                        realized, startable = points_and_startable(pid, season_roster, week)
                        waiver_obs.append(
                            _WaiverObservation(
                                season=season_str,
                                week=week,
                                roster_id=cur,
                                owner_name=name_by_current.get(cur, str(cur)),
                                player_id=pid,
                                player_name=_player_name(players_dump, pid),
                                position=position,
                                bid=bid,
                                realized_points=realized,
                                startable_weeks=startable,
                            )
                        )
                elif typ == "trade":
                    roster_ids = txn.get("roster_ids") or []
                    add_map = txn.get("adds") or {}
                    drop_map = txn.get("drops") or {}
                    picks = txn.get("draft_picks") or []
                    for rid in roster_ids:
                        cur = season_to_current.get(rid)
                        if cur is None:
                            continue
                        partner_rids = [r for r in roster_ids if r != rid]
                        partner_cur = (
                            season_to_current.get(partner_rids[0]) if partner_rids else None
                        )
                        received = [
                            {
                                "player_id": pid,
                                "name": _player_name(players_dump, pid),
                                "points": points_and_startable(pid, rid, week)[0],
                            }
                            for pid, to_rid in add_map.items()
                            if to_rid == rid
                        ]
                        sent = [
                            {
                                "player_id": pid,
                                "name": _player_name(players_dump, pid),
                                "points": points_and_startable(pid, add_map.get(pid, rid), week)[0],
                            }
                            for pid, from_rid in drop_map.items()
                            if from_rid == rid
                        ]
                        rp = sum(x["points"] for x in received)
                        gp = sum(x["points"] for x in sent)
                        dd = None
                        if vet_values:
                            recv_val = sum(vet_values.get(x["player_id"], 0.0) for x in received)
                            sent_val = sum(vet_values.get(x["player_id"], 0.0) for x in sent)
                            dd = round(recv_val - sent_val, 0)
                        trade_obs.append(
                            _TradeObservation(
                                season=season_str,
                                week=week,
                                roster_id=cur,
                                owner_name=name_by_current.get(cur, str(cur)),
                                partner_roster_id=partner_cur if partner_cur is not None else -1,
                                partner_name=(
                                    name_by_current.get(partner_cur, "?")
                                    if partner_cur is not None
                                    else "?"
                                ),
                                received=received,
                                sent=sent,
                                picks_received=sum(1 for p in picks if p.get("owner_id") == rid),
                                picks_sent=sum(
                                    1 for p in picks if p.get("previous_owner_id") == rid
                                ),
                                net_points=round(rp - gp, 1),
                                dynasty_delta=dd,
                            )
                        )

            all_waiver_grades.extend(
                assemble_waiver_grades(waiver_obs, market.bids, current_season, current_week)
            )
            all_trade_grades.extend(assemble_trade_grades(trade_obs, current_season, current_week))

    if not all_waiver_grades and not all_trade_grades:
        warnings.append("No gradeable waiver claims or trades found in league history.")

    return TransactionGradeBook(
        seasons_covered=seasons_covered,
        waiver_grades=all_waiver_grades,
        trade_grades=all_trade_grades,
        gpa=build_gpa_table(all_waiver_grades, all_trade_grades),
        warnings=warnings,
    )


__all__ = [
    "OwnerGpa",
    "TradeSideGrade",
    "TransactionGradeBook",
    "WaiverGrade",
    "assemble_trade_grades",
    "assemble_waiver_grades",
    "bid_percentile",
    "build_gpa_table",
    "build_transaction_grades",
    "claim_surplus",
    "grade_on_curve",
    "is_settling",
    "league_points_per_dollar",
    "letter_gpa",
]
