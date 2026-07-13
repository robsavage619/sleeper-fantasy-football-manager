"""Transaction value added — fantasy points a GM gained via waivers and trades.

Sleeper exposes per-player weekly points (``matchup.players_points``) under the
league's scoring, plus every transaction's type/week/players. Combining them
lets us measure how much real production each manager mined off the waiver wire
and won (or lost) through trades — attributed to the *current* manager.

Surfaced (latest completed season):
  waiver_points / waiver_started_points   points from waiver/FA adds (rostered / started)
  trade_in / out / net points             realized trade win-loss in points
  started_by_source                       lineup production split: draft / waiver / trade
  top_pickups                             the best waiver/FA gems, ranked
  trade_deals                             every trade with players in/out and net points
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field

import httpx

from sleeper_ffm.config import LEAGUE_ID
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

_MAX_WEEK = 18
_WAIVER_METHODS = ("waiver", "free_agent")


@dataclass
class Pickup:
    """A waiver/FA add and the points they scored (total + in the lineup)."""

    player_id: str
    name: str
    points: float
    started_points: float


@dataclass
class TradeDeal:
    """One trade this manager made, with realized post-trade points on each side."""

    week: int
    partner: str
    received: list[dict] = field(default_factory=list)  # [{player_id,name,points}]
    given: list[dict] = field(default_factory=list)
    picks_received: int = 0
    picks_given: int = 0
    received_points: float = 0.0
    given_points: float = 0.0
    net_points: float = 0.0


@dataclass
class TransactionValue:
    """Per-manager fantasy points added via waivers and trades in one season."""

    roster_id: int
    display_name: str
    season: str
    waiver_points: float = 0.0
    waiver_started_points: float = 0.0
    waiver_adds: int = 0
    trade_in_points: float = 0.0
    trade_out_points: float = 0.0
    trade_net_points: float = 0.0
    trade_count: int = 0
    draft_started_points: float = 0.0
    trade_started_points: float = 0.0
    top_pickups: list[dict] = field(default_factory=list)
    trade_deals: list[dict] = field(default_factory=list)


def _player_name(players_dump: dict, pid: str) -> str:
    p = players_dump.get(pid) or {}
    return p.get("full_name") or p.get("search_full_name") or f"Player {pid}"


def _latest_completed_season(client: SleeperClient, league_id: str):
    """Return the newest season league that has real (non-zero) matchup data."""
    for league in client.league_history(league_id=league_id):
        try:
            wk1 = client.matchups(1, league_id=league.league_id)
        except httpx.HTTPError:
            continue
        if any(sum((m.get("players_points") or {}).values()) for m in wk1):
            return league
    return None


def build_transaction_value(league_id: str = LEAGUE_ID) -> list[dict]:
    """Return per-manager transaction value for the latest completed season."""
    with SleeperClient(league_id=league_id) as client:
        seasons = client.league_history(league_id=league_id)
        if not seasons:
            return []
        current_rosters = client.rosters(league_id=seasons[0].league_id)
        user_to_current = {r.owner_id or "": r.roster_id for r in current_rosters}

        season = _latest_completed_season(client, league_id)
        if season is None:
            return []
        lid = season.league_id
        players_dump = client.players()
        users = {u.user_id: (u.display_name or u.user_id) for u in client.users(lid)}
        season_rosters = client.rosters(lid)
        season_to_current = {
            r.roster_id: user_to_current.get(r.owner_id or "", r.roster_id) for r in season_rosters
        }
        name_by_current = {
            user_to_current.get(r.owner_id or "", r.roster_id): users.get(r.owner_id or "", "")
            for r in season_rosters
        }

        adds: dict[tuple[int, str], list[tuple[int, str]]] = defaultdict(list)
        trade_txns: list[dict] = []
        waiver_add_count: dict[int, int] = defaultdict(int)
        trade_count: dict[int, int] = defaultdict(int)
        matchups_by_week: dict[int, dict[int, tuple[dict, set]]] = {}

        for wk in range(1, _MAX_WEEK + 1):
            try:
                txns = client.transactions(wk, league_id=lid)
            except httpx.HTTPError:
                txns = []
            for t in txns:
                if t.get("status") != "complete":
                    continue
                typ = t.get("type") or ""
                leg = t.get("leg", wk)
                add_map = t.get("adds") or {}
                for pid, rid in add_map.items():
                    adds[(rid, pid)].append((leg, typ))
                    if typ in _WAIVER_METHODS:
                        waiver_add_count[rid] += 1
                if typ == "trade":
                    for rid in t.get("roster_ids") or []:
                        trade_count[rid] += 1
                    trade_txns.append(
                        {
                            "leg": leg,
                            "roster_ids": t.get("roster_ids") or [],
                            "adds": add_map,
                            "drops": t.get("drops") or {},
                            "picks": t.get("draft_picks") or [],
                        }
                    )

            try:
                mus = client.matchups(wk, league_id=lid)
            except httpx.HTTPError:
                mus = []
            matchups_by_week[wk] = {
                m["roster_id"]: (m.get("players_points") or {}, set(m.get("starters") or []))
                for m in mus
            }

    def method_for(rid: int, pid: str, week: int) -> str:
        evs = [(leg, typ) for (leg, typ) in adds.get((rid, pid), []) if leg <= week]
        return max(evs)[1] if evs else "draft"

    def post_points(pid: str, rid: int, from_week: int) -> float:
        total = 0.0
        for wk in range(from_week, _MAX_WEEK + 1):
            pp = matchups_by_week.get(wk, {}).get(rid, ({}, set()))[0]
            if pid in pp:
                total += pp[pid]
        return round(total, 1)

    tv: dict[int, TransactionValue] = {}
    for cur in set(season_to_current.values()):
        tv[cur] = TransactionValue(
            roster_id=cur,
            display_name=name_by_current.get(cur, str(cur)),
            season=season.season or "",
        )

    started_by_source: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    waiver_all: dict[int, float] = defaultdict(float)
    pickup_total: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pickup_started: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for wk, by_roster in matchups_by_week.items():
        for rid, (pp, starters) in by_roster.items():
            cur = season_to_current.get(rid, rid)
            if cur not in tv:
                continue
            for pid, pts in pp.items():
                meth = method_for(rid, pid, wk)
                source = "waiver" if meth in _WAIVER_METHODS else meth
                if pid in starters:
                    started_by_source[cur][source] += pts
                if source == "waiver":
                    waiver_all[cur] += pts
                    pickup_total[cur][pid] += pts
                    if pid in starters:
                        pickup_started[cur][pid] += pts

    # Individual trade deals (realized post-trade points on each side).
    deals_by_cur: dict[int, list[TradeDeal]] = defaultdict(list)
    for txn in trade_txns:
        leg = txn["leg"]
        add_map = txn["adds"]
        drop_map = txn["drops"]
        for rid in txn["roster_ids"]:
            cur = season_to_current.get(rid, rid)
            if cur not in tv:
                continue
            partner_rids = [r for r in txn["roster_ids"] if r != rid]
            partner = (
                name_by_current.get(season_to_current.get(partner_rids[0], -1), "?")
                if partner_rids
                else "?"
            )
            received = [
                {
                    "player_id": pid,
                    "name": _player_name(players_dump, pid),
                    "points": post_points(pid, rid, leg),
                }
                for pid, to_rid in add_map.items()
                if to_rid == rid
            ]
            given = [
                {
                    "player_id": pid,
                    "name": _player_name(players_dump, pid),
                    "points": post_points(pid, add_map.get(pid, rid), leg),
                }
                for pid, from_rid in drop_map.items()
                if from_rid == rid
            ]
            picks_recv = sum(1 for p in txn["picks"] if p.get("owner_id") == rid)
            picks_give = sum(1 for p in txn["picks"] if p.get("previous_owner_id") == rid)
            rp = round(sum(x["points"] for x in received), 1)
            gp = round(sum(x["points"] for x in given), 1)
            deals_by_cur[cur].append(
                TradeDeal(
                    week=leg,
                    partner=partner,
                    received=received,
                    given=given,
                    picks_received=picks_recv,
                    picks_given=picks_give,
                    received_points=rp,
                    given_points=gp,
                    net_points=round(rp - gp, 1),
                )
            )

    results: list[dict] = []
    for cur, card in tv.items():
        src = started_by_source[cur]
        card.waiver_points = round(waiver_all[cur], 1)
        card.waiver_started_points = round(src.get("waiver", 0.0), 1)
        card.draft_started_points = round(src.get("draft", 0.0), 1)
        card.trade_started_points = round(src.get("trade", 0.0), 1)
        card.waiver_adds = _count_for_current(waiver_add_count, season_to_current, cur)
        card.trade_count = _count_for_current(trade_count, season_to_current, cur)
        deals = deals_by_cur.get(cur, [])
        card.trade_in_points = round(sum(d.received_points for d in deals), 1)
        card.trade_out_points = round(sum(d.given_points for d in deals), 1)
        card.trade_net_points = round(card.trade_in_points - card.trade_out_points, 1)
        card.trade_deals = [
            asdict(d) for d in sorted(deals, key=lambda d: d.net_points, reverse=True)
        ]

        totals = pickup_total[cur]
        top = sorted(totals, key=lambda k: totals[k], reverse=True)[:5]
        card.top_pickups = [
            asdict(
                Pickup(
                    player_id=pid,
                    name=_player_name(players_dump, pid),
                    points=round(totals[pid], 1),
                    started_points=round(pickup_started[cur].get(pid, 0.0), 1),
                )
            )
            for pid in top
            if totals[pid] > 0
        ]
        results.append(asdict(card))

    results.sort(
        key=lambda c: c["waiver_started_points"] + max(c["trade_net_points"], 0), reverse=True
    )
    return results


def _count_for_current(counts: dict[int, int], season_to_current: dict[int, int], cur: int) -> int:
    """Sum season-roster counts that map to a given current roster."""
    return sum(v for rid, v in counts.items() if season_to_current.get(rid, rid) == cur)
