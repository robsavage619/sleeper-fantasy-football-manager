"""Multi-season transaction-history engine for the dynasty.

Walks every season via ``previous_league_id`` and every scoring week's transactions to
reconstruct per-owner behavioral history: trades, trade partners, and waiver/FAAB tendencies.
Owners are keyed by their CURRENT roster_id; historical rosters join through the stable user_id.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from statistics import median

import httpx

from sleeper_ffm.config import LEAGUE_ID
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

_MAX_WEEK = 18
_MAX_TRADES = 40


@dataclass
class TradeEvent:
    """One trade from a single owner's perspective."""

    season: str
    week: int
    partner_roster_id: int | None
    partner_name: str | None
    received: list[str]
    sent: list[str]
    picks_received: int = 0
    picks_sent: int = 0


@dataclass
class OwnerHistory:
    """Aggregated multi-season transaction history for one current roster."""

    roster_id: int
    user_id: str
    trade_count: int
    trades: list[TradeEvent] = field(default_factory=list)
    trade_partners: list[dict] = field(default_factory=list)
    waiver_adds: int = 0
    free_agent_adds: int = 0
    drops: int = 0
    faab_spent: int = 0
    seasons_covered: list[str] = field(default_factory=list)
    seasons_active: int = 0
    trades_per_season: float = 0.0
    picks_acquired: int = 0
    picks_sent: int = 0
    net_picks: int = 0
    avg_trade_size: float = 0.0
    top_partner_share: float = 0.0
    adds_per_season: float = 0.0
    faab_per_season: float = 0.0
    last_activity: dict | None = None
    trades_by_season: list[dict] = field(default_factory=list)
    behavioral_type: str = "THE GHOST"
    behavioral_summary: str = ""
    behavioral_tags: list[str] = field(default_factory=list)
    pick_lean: str = "NEUTRAL"
    approachability: str = "DORMANT"


@dataclass
class LeagueHistory:
    """Every current owner's transaction history across all dynasty seasons."""

    seasons_covered: list[str]
    owners: list[OwnerHistory]


@dataclass
class _Accumulator:
    """Mutable per-current-roster tally accumulated while walking seasons."""

    roster_id: int
    user_id: str
    trades: list[TradeEvent] = field(default_factory=list)
    partner_counts: Counter[int] = field(default_factory=Counter)
    waiver_adds: int = 0
    free_agent_adds: int = 0
    drops: int = 0
    faab_spent: int = 0
    picks_acquired: int = 0
    picks_sent: int = 0
    active_seasons: set[str] = field(default_factory=set)
    last_season: str | None = None
    last_week: int = -1


def _touch(acc: _Accumulator, season: str, week: int) -> None:
    """Record that ``acc`` transacted in ``season``/``week`` for activity tracking."""
    acc.active_seasons.add(season)
    if (season, week) > (acc.last_season or "", acc.last_week):
        acc.last_season = season
        acc.last_week = week


def _player_name(pid: str, players_dump: dict[str, dict]) -> str:
    """Resolve a Sleeper player_id to a full name, falling back to the id."""
    return players_dump.get(pid, {}).get("full_name") or pid


def _fetch_season_transactions(client: SleeperClient, league_id: str) -> list[dict]:
    """Collect all complete transactions across weeks 1..18 for one season league.

    Wraps each week fetch so an out-of-range week (httpx error) breaks to the caller
    instead of aborting the whole build.
    """
    txns: list[dict] = []
    for week in range(1, _MAX_WEEK + 1):
        try:
            week_txns = client.transactions(week, league_id=league_id)
        except httpx.HTTPError as exc:
            log.warning("history: week %d fetch failed for league %s: %s", week, league_id, exc)
            break
        for txn in week_txns or []:
            if txn.get("status") == "complete":
                txns.append(txn)
    return txns


def _build_trade_event(
    txn: dict,
    season: str,
    this_roster: int,
    season_roster_to_current: dict[int, int],
    current_name_by_roster: dict[int, str],
    players_dump: dict[str, dict],
) -> TradeEvent:
    """Construct a TradeEvent for ``this_roster`` (a season roster_id) from a raw trade dict."""
    adds = txn.get("adds") or {}
    draft_picks = txn.get("draft_picks") or []
    waiver_budget = txn.get("waiver_budget") or []
    roster_ids = txn.get("roster_ids") or []

    partner_season_roster: int | None = next((r for r in roster_ids if r != this_roster), None)

    received: list[str] = [
        _player_name(pid, players_dump) for pid, rid in adds.items() if rid == this_roster
    ]
    received += [
        f"{p.get('season')} R{p.get('round')}"
        for p in draft_picks
        if p.get("owner_id") == this_roster
    ]
    received += [
        f"${b.get('amount', 0)} FAAB" for b in waiver_budget if b.get("receiver") == this_roster
    ]

    sent: list[str] = [
        _player_name(pid, players_dump)
        for pid, rid in adds.items()
        if partner_season_roster is not None and rid == partner_season_roster
    ]
    sent += [
        f"{p.get('season')} R{p.get('round')}"
        for p in draft_picks
        if p.get("previous_owner_id") == this_roster
    ]
    sent += [f"${b.get('amount', 0)} FAAB" for b in waiver_budget if b.get("sender") == this_roster]

    partner_current: int | None = (
        season_roster_to_current.get(partner_season_roster)
        if partner_season_roster is not None
        else None
    )
    partner_name = (
        current_name_by_roster.get(partner_current) if partner_current is not None else None
    )

    picks_received = sum(1 for p in draft_picks if p.get("owner_id") == this_roster)
    picks_sent = sum(1 for p in draft_picks if p.get("previous_owner_id") == this_roster)

    return TradeEvent(
        season=season,
        week=int(txn.get("leg") or 0),
        partner_roster_id=partner_current,
        partner_name=partner_name,
        received=received,
        sent=sent,
        picks_received=picks_received,
        picks_sent=picks_sent,
    )


def build_league_history(league_id: str = LEAGUE_ID) -> LeagueHistory:
    """Build multi-season transaction history for every current owner.

    Walks the full dynasty chain and every scoring week, attributing transactions to
    the current roster that the historical owner now controls.

    Args:
        league_id: Current-season Sleeper league ID.

    Returns:
        A LeagueHistory with one OwnerHistory per current roster (zeros when no data).
    """
    with SleeperClient(league_id=league_id) as client:
        seasons = client.league_history(league_id=league_id)
        players_dump = client.players()

        if not seasons:
            log.warning("history: no seasons returned for league %s", league_id)
            return LeagueHistory(seasons_covered=[], owners=[])

        current = seasons[0]
        current_rosters = client.rosters(league_id=current.league_id)
        current_users = client.users(league_id=current.league_id)

        # Canonical current-season maps.
        current_name_by_user = {u.user_id: (u.display_name or u.user_id) for u in current_users}
        user_to_current_roster: dict[str, int] = {}
        current_name_by_roster: dict[int, str] = {}
        accumulators: dict[int, _Accumulator] = {}
        for roster in current_rosters:
            uid = roster.owner_id or ""
            user_to_current_roster[uid] = roster.roster_id
            current_name_by_roster[roster.roster_id] = current_name_by_user.get(uid, uid)
            accumulators[roster.roster_id] = _Accumulator(roster_id=roster.roster_id, user_id=uid)

        seasons_covered: list[str] = []
        total_trades = 0

        for league in seasons:
            season_str = league.season or league.league_id
            try:
                season_rosters = client.rosters(league_id=league.league_id)
                # users() fetched for parity with contract; names resolve via current roster.
                client.users(league_id=league.league_id)
            except httpx.HTTPError as exc:
                log.warning("history: roster/user fetch failed for %s: %s", season_str, exc)
                continue

            seasons_covered.append(season_str)

            # This season's roster_id -> user_id, and roster_id -> current roster_id.
            season_roster_to_user = {r.roster_id: (r.owner_id or "") for r in season_rosters}
            season_roster_to_current: dict[int, int] = {}
            for sr_id, uid in season_roster_to_user.items():
                cur = user_to_current_roster.get(uid)
                if cur is not None:
                    season_roster_to_current[sr_id] = cur

            try:
                txns = _fetch_season_transactions(client, league.league_id)
            except httpx.HTTPError as exc:
                log.warning("history: transaction walk failed for %s: %s", season_str, exc)
                continue

            for txn in txns:
                _apply_transaction(
                    txn,
                    season_str,
                    season_roster_to_current,
                    current_name_by_roster,
                    accumulators,
                    players_dump,
                )
                if txn.get("type") == "trade":
                    total_trades += 1

    owners = _finalize(accumulators, current_name_by_roster, seasons_covered)
    log.info(
        "history: %d seasons, %d trades total across league",
        len(seasons_covered),
        total_trades,
    )
    return LeagueHistory(seasons_covered=seasons_covered, owners=owners)


def _apply_transaction(
    txn: dict,
    season_str: str,
    season_roster_to_current: dict[int, int],
    current_name_by_roster: dict[int, str],
    accumulators: dict[int, _Accumulator],
    players_dump: dict[str, dict],
) -> None:
    """Attribute one complete transaction to the relevant current rosters."""
    txn_type = txn.get("type")
    adds = txn.get("adds") or {}
    drops = txn.get("drops") or {}
    settings = txn.get("settings") or {}
    waiver_budget = txn.get("waiver_budget") or []
    week = int(txn.get("leg") or 0)

    if txn_type == "trade":
        roster_ids = txn.get("roster_ids") or []
        for season_roster in roster_ids:
            current_roster = season_roster_to_current.get(season_roster)
            if current_roster is None:
                continue
            acc = accumulators.get(current_roster)
            if acc is None:
                continue
            event = _build_trade_event(
                txn,
                season_str,
                season_roster,
                season_roster_to_current,
                current_name_by_roster,
                players_dump,
            )
            acc.trades.append(event)
            acc.picks_acquired += event.picks_received
            acc.picks_sent += event.picks_sent
            _touch(acc, season_str, week)
            if event.partner_roster_id is not None:
                acc.partner_counts[event.partner_roster_id] += 1
        # FAAB moved between managers in the trade.
        for budget in waiver_budget:
            sender_current = season_roster_to_current.get(budget.get("sender"))
            if sender_current is not None and sender_current in accumulators:
                accumulators[sender_current].faab_spent += int(budget.get("amount", 0) or 0)
        return

    # Waiver / free-agent / commissioner: count adds and drops for the acting roster.
    for _pid, season_roster in adds.items():
        current_roster = season_roster_to_current.get(season_roster)
        if current_roster is None or current_roster not in accumulators:
            continue
        acc = accumulators[current_roster]
        if txn_type == "waiver":
            acc.waiver_adds += 1
            acc.faab_spent += int(settings.get("waiver_bid", 0) or 0)
            _touch(acc, season_str, week)
        elif txn_type == "free_agent":
            acc.free_agent_adds += 1
            _touch(acc, season_str, week)

    for _pid, season_roster in drops.items():
        current_roster = season_roster_to_current.get(season_roster)
        if current_roster is None or current_roster not in accumulators:
            continue
        acc = accumulators[current_roster]
        acc.drops += 1
        _touch(acc, season_str, week)


@dataclass
class _RawStats:
    """Per-owner raw stats gathered in pass one, before relative labels are assigned."""

    trade_count: int
    seasons_active: int
    trades_per_season: float
    net_picks: int
    adds_per_season: float
    faab_per_season: float
    top_partner_share: float
    top_partner_name: str | None
    distinct_partners: int


def _gather_raw(acc: _Accumulator, current_name_by_roster: dict[int, str]) -> _RawStats:
    """Compute one owner's raw per-season rates and pick balance (pass one)."""
    trade_count = len(acc.trades)
    seasons_active = len(acc.active_seasons)
    denom = max(seasons_active, 1)
    trades_per_season = round(trade_count / denom, 2)
    adds_per_season = round((acc.waiver_adds + acc.free_agent_adds) / denom, 1)
    faab_per_season = round(acc.faab_spent / denom)
    net_picks = acc.picks_acquired - acc.picks_sent

    top = acc.partner_counts.most_common(1)
    if top and trade_count:
        top_partner_share = round(top[0][1] / trade_count, 2)
        top_partner_name = current_name_by_roster.get(top[0][0], str(top[0][0]))
    else:
        top_partner_share = 0.0
        top_partner_name = None

    return _RawStats(
        trade_count=trade_count,
        seasons_active=seasons_active,
        trades_per_season=trades_per_season,
        net_picks=net_picks,
        adds_per_season=adds_per_season,
        faab_per_season=faab_per_season,
        top_partner_share=top_partner_share,
        top_partner_name=top_partner_name,
        distinct_partners=len(acc.partner_counts),
    )


def _behavioral_type(r: _RawStats, m_tps: float, m_fps: float, m_adds: float) -> str:
    """Assign the headline nickname from the objective, first-match decision tree."""
    if r.seasons_active == 0 or (r.trade_count == 0 and r.adds_per_season < 0.5):
        return "THE GHOST"
    if r.trades_per_season >= 1.5 * m_tps and r.trades_per_season >= 2:
        return "THE WHEELER-DEALER"
    if r.net_picks >= 3:
        return "THE PICK HOARDER"
    if r.net_picks <= -3:
        return "THE WIN-NOW GAMBLER"
    if r.faab_per_season >= 1.5 * m_fps and r.faab_per_season > 0:
        return "THE FAAB BULLY"
    if r.adds_per_season >= 1.5 * m_adds:
        return "THE STREAMER"
    if r.trades_per_season <= 0.5 * m_tps:
        return "THE STATUE"
    return "THE OPERATOR"


def _behavioral_tags(r: _RawStats, m_tps: float, m_fps: float, m_adds: float) -> list[str]:
    """Collect up to four trait tags, ordered by importance."""
    tags: list[str] = []
    if r.net_picks >= 2:
        tags.append("PICK-HOARDER")
    elif r.net_picks <= -2:
        tags.append("PICK-SPENDER")
    if r.trades_per_season >= max(2, m_tps):
        tags.append("ACTIVE-TRADER")
    elif r.trades_per_season <= 0.5 * m_tps:
        tags.append("PASSIVE")
    if r.faab_per_season >= 1.5 * m_fps and r.faab_per_season > 0:
        tags.append("FAAB-AGGRESSIVE")
    elif r.faab_per_season <= 0.5 * m_fps:
        tags.append("FAAB-THRIFTY")
    if r.top_partner_share >= 0.5 and r.trade_count >= 3:
        tags.append("ONE-PARTNER")
    if r.adds_per_season >= 1.5 * m_adds:
        tags.append("WAIVER-CHURN")
    return tags[:4]


def _approachability(r: _RawStats, last_season: str | None, newest: str | None) -> str:
    """Classify how open the owner is to dealing, from recency and partner spread."""
    stale = (
        last_season is not None and newest is not None and _years_behind(last_season, newest) > 1
    )
    if last_season is None or r.trade_count == 0 or stale:
        return "DORMANT"
    if r.trade_count >= 3 and r.top_partner_share >= 0.6:
        return "INSULAR"
    if r.distinct_partners >= 4:
        return "OPEN"
    return "SELECTIVE"


def _years_behind(season: str, newest: str) -> int:
    """Return how many seasons ``season`` trails ``newest`` (0 if not both numeric)."""
    try:
        return int(newest) - int(season)
    except ValueError:
        return 0


def _summary(r: _RawStats, btype: str) -> str:
    """Compose a plain, objective one-line scouting note from real numbers."""
    if r.trade_count == 0:
        base = f"No trades in {max(r.seasons_active, 0)} active season(s)"
    else:
        base = f"{r.trades_per_season} trades/season"
        if r.top_partner_share >= 0.5 and r.top_partner_name:
            base += f", mostly with {r.top_partner_name}"

    if r.net_picks > 0:
        picks = f"; hoards picks (+{r.net_picks})"
    elif r.net_picks < 0:
        picks = f"; spends picks ({r.net_picks})"
    else:
        picks = ""

    if r.adds_per_season >= 2:
        wire = f"; {r.adds_per_season} wire adds/yr"
    elif r.trade_count == 0 and r.adds_per_season < 0.5:
        wire = "; barely touches the wire"
    else:
        wire = ""

    nickname = btype.replace("THE ", "").lower()
    return f"{base}{picks}{wire} — {nickname}."[:140]


def _finalize(
    accumulators: dict[int, _Accumulator],
    current_name_by_roster: dict[int, str],
    seasons_covered: list[str],
) -> list[OwnerHistory]:
    """Convert accumulators into OwnerHistory records with a relative behavioral layer.

    Two-pass: gather raw per-owner stats, derive league-relative medians, then assign
    nicknames, tags, and labels against those medians.
    """
    ordered_ids = sorted(accumulators)
    raw = {rid: _gather_raw(accumulators[rid], current_name_by_roster) for rid in ordered_ids}

    active = [r for r in raw.values() if r.seasons_active > 0]
    if len(active) >= 2:
        m_tps = median(r.trades_per_season for r in active)
        m_fps = median(r.faab_per_season for r in active)
        m_adds = median(r.adds_per_season for r in active)
    else:
        m_tps, m_fps, m_adds = 1.0, 20.0, 3.0
    m_tps = m_tps or 0.01
    m_fps = m_fps or 0.01
    m_adds = m_adds or 0.01

    newest = max(seasons_covered) if seasons_covered else None
    seasons_asc = sorted(seasons_covered)

    owners: list[OwnerHistory] = []
    for roster_id in ordered_ids:
        acc = accumulators[roster_id]
        r = raw[roster_id]
        trades = sorted(acc.trades, key=lambda t: (t.season, t.week), reverse=True)[:_MAX_TRADES]
        partners = [
            {
                "roster_id": pr_id,
                "name": current_name_by_roster.get(pr_id, str(pr_id)),
                "count": count,
            }
            for pr_id, count in acc.partner_counts.most_common()
        ]

        trades_per = Counter(t.season for t in acc.trades)
        trades_by_season = [{"season": s, "count": trades_per.get(s, 0)} for s in seasons_asc]

        sizes = [len([a for a in (t.received + t.sent) if "FAAB" not in a]) for t in acc.trades]
        avg_trade_size = round(sum(sizes) / len(sizes), 1) if sizes else 0.0

        last_activity = (
            {"season": acc.last_season, "week": acc.last_week}
            if acc.last_season is not None
            else None
        )

        btype = _behavioral_type(r, m_tps, m_fps, m_adds)
        net_picks = r.net_picks
        pick_lean = "HOARDS" if net_picks >= 2 else "SPENDS" if net_picks <= -2 else "NEUTRAL"

        owners.append(
            OwnerHistory(
                roster_id=acc.roster_id,
                user_id=acc.user_id,
                trade_count=r.trade_count,
                trades=trades,
                trade_partners=partners,
                waiver_adds=acc.waiver_adds,
                free_agent_adds=acc.free_agent_adds,
                drops=acc.drops,
                faab_spent=acc.faab_spent,
                seasons_covered=seasons_covered,
                seasons_active=r.seasons_active,
                trades_per_season=r.trades_per_season,
                picks_acquired=acc.picks_acquired,
                picks_sent=acc.picks_sent,
                net_picks=net_picks,
                avg_trade_size=avg_trade_size,
                top_partner_share=r.top_partner_share,
                adds_per_season=r.adds_per_season,
                faab_per_season=r.faab_per_season,
                last_activity=last_activity,
                trades_by_season=trades_by_season,
                behavioral_type=btype,
                behavioral_summary=_summary(r, btype),
                behavioral_tags=_behavioral_tags(r, m_tps, m_fps, m_adds),
                pick_lean=pick_lean,
                approachability=_approachability(r, acc.last_season, newest),
            )
        )
    return owners
