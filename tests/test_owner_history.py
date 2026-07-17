"""Tests for owner_history.py — the multi-season transaction-history engine.

Pure helper functions (``_gather_raw``, ``_behavioral_type``, ``_behavioral_tags``,
``_approachability``, ``_years_behind``, ``_build_trade_event``, ``_apply_transaction``,
``_finalize``) are exercised directly against hand-built fixtures. ``build_league_history``
is exercised end-to-end against a fake SleeperClient (same DI-seam pattern as
``test_gm_metrics.py``'s ``_FakeClient``), so no network call is made.
"""

from __future__ import annotations

import pytest

from sleeper_ffm.model import owner_history as oh
from sleeper_ffm.sleeper.models import League, Roster, User


@pytest.fixture(autouse=True)
def _clear_history_cache():
    """``build_league_history`` is TTL-cached by league_id; tests reuse the same id."""
    oh.build_league_history.cache_clear()
    yield
    oh.build_league_history.cache_clear()

# ---------------------------------------------------------------------------
# _years_behind
# ---------------------------------------------------------------------------


def test_years_behind_numeric_seasons() -> None:
    assert oh._years_behind("2023", "2025") == 2
    assert oh._years_behind("2025", "2025") == 0


def test_years_behind_non_numeric_returns_zero() -> None:
    assert oh._years_behind("preseason", "2025") == 0


# ---------------------------------------------------------------------------
# _touch
# ---------------------------------------------------------------------------


def test_touch_records_latest_season_and_week() -> None:
    acc = oh._Accumulator(roster_id=1, user_id="u1")
    oh._touch(acc, "2023", 5)
    oh._touch(acc, "2024", 2)
    oh._touch(acc, "2024", 1)  # earlier week in the same later season -> no regression
    assert acc.active_seasons == {"2023", "2024"}
    assert acc.last_season == "2024"
    assert acc.last_week == 2


# ---------------------------------------------------------------------------
# _gather_raw
# ---------------------------------------------------------------------------


def test_gather_raw_computes_rates_and_top_partner() -> None:
    acc = oh._Accumulator(roster_id=1, user_id="u1")
    acc.trades = [
        oh.TradeEvent(season="2024", week=1, partner_roster_id=2, partner_name="Two",
                      received=["A"], sent=["B"]),
        oh.TradeEvent(season="2024", week=3, partner_roster_id=2, partner_name="Two",
                      received=["C"], sent=["D"]),
    ]
    acc.partner_counts.update({2: 2})
    acc.active_seasons = {"2023", "2024"}
    acc.waiver_adds = 3
    acc.free_agent_adds = 1
    acc.faab_spent = 40
    acc.picks_acquired = 2
    acc.picks_sent = 1

    raw = oh._gather_raw(acc, {2: "Two"})

    assert raw.trade_count == 2
    assert raw.seasons_active == 2
    assert raw.trades_per_season == 1.0
    assert raw.net_picks == 1
    assert raw.adds_per_season == 2.0
    assert raw.faab_per_season == 20
    assert raw.top_partner_share == 1.0
    assert raw.top_partner_name == "Two"
    assert raw.distinct_partners == 1


def test_gather_raw_zero_trades_has_no_top_partner() -> None:
    acc = oh._Accumulator(roster_id=1, user_id="u1")
    raw = oh._gather_raw(acc, {})
    assert raw.trade_count == 0
    assert raw.top_partner_share == 0.0
    assert raw.top_partner_name is None


# ---------------------------------------------------------------------------
# _behavioral_type — first-match decision tree
# ---------------------------------------------------------------------------


def _raw(**overrides) -> oh._RawStats:
    base = dict(
        trade_count=1,
        seasons_active=1,
        trades_per_season=1.0,
        net_picks=0,
        adds_per_season=1.0,
        faab_per_season=10.0,
        top_partner_share=0.0,
        top_partner_name=None,
        distinct_partners=1,
    )
    base.update(overrides)
    return oh._RawStats(**base)


def test_behavioral_type_ghost_when_never_active() -> None:
    r = _raw(seasons_active=0, trade_count=0, adds_per_season=0.0)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE GHOST"


def test_behavioral_type_ghost_when_no_trades_and_barely_touches_wire() -> None:
    r = _raw(trade_count=0, adds_per_season=0.2)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE GHOST"


def test_behavioral_type_wheeler_dealer() -> None:
    r = _raw(trades_per_season=3.0)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE WHEELER-DEALER"


def test_behavioral_type_pick_hoarder() -> None:
    r = _raw(net_picks=3, trades_per_season=1.0)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE PICK HOARDER"


def test_behavioral_type_win_now_gambler() -> None:
    r = _raw(net_picks=-3, trades_per_season=1.0)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE WIN-NOW GAMBLER"


def test_behavioral_type_faab_bully() -> None:
    r = _raw(faab_per_season=40.0, trades_per_season=1.0)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE FAAB BULLY"


def test_behavioral_type_streamer() -> None:
    r = _raw(adds_per_season=6.0, trades_per_season=1.0, faab_per_season=10.0)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE STREAMER"


def test_behavioral_type_statue() -> None:
    r = _raw(trades_per_season=0.2, adds_per_season=1.0, faab_per_season=10.0)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE STATUE"


def test_behavioral_type_operator_is_the_fallback() -> None:
    r = _raw(trades_per_season=1.0, adds_per_season=1.0, faab_per_season=10.0, net_picks=0)
    assert oh._behavioral_type(r, 1.0, 20.0, 3.0) == "THE OPERATOR"


# ---------------------------------------------------------------------------
# _behavioral_tags / _approachability
# ---------------------------------------------------------------------------


def test_behavioral_tags_pick_hoarder_and_active_trader() -> None:
    r = _raw(net_picks=2, trades_per_season=5.0, faab_per_season=10.0, adds_per_season=1.0)
    tags = oh._behavioral_tags(r, 1.0, 20.0, 3.0)
    assert "PICK-HOARDER" in tags
    assert "ACTIVE-TRADER" in tags


def test_behavioral_tags_capped_at_four() -> None:
    r = _raw(
        net_picks=2,
        trades_per_season=5.0,
        faab_per_season=40.0,
        adds_per_season=6.0,
        top_partner_share=0.8,
        trade_count=5,
    )
    tags = oh._behavioral_tags(r, 1.0, 20.0, 3.0)
    assert len(tags) <= 4


def test_approachability_dormant_when_no_trades() -> None:
    r = _raw(trade_count=0)
    assert oh._approachability(r, None, "2025") == "DORMANT"


def test_approachability_dormant_when_stale() -> None:
    r = _raw(trade_count=2)
    assert oh._approachability(r, "2020", "2025") == "DORMANT"


def test_approachability_insular_with_one_dominant_partner() -> None:
    r = _raw(trade_count=3, top_partner_share=0.8)
    assert oh._approachability(r, "2025", "2025") == "INSULAR"


def test_approachability_open_with_many_partners() -> None:
    r = _raw(trade_count=5, top_partner_share=0.2, distinct_partners=5)
    assert oh._approachability(r, "2025", "2025") == "OPEN"


def test_approachability_selective_otherwise() -> None:
    r = _raw(trade_count=1, top_partner_share=0.3, distinct_partners=1)
    assert oh._approachability(r, "2025", "2025") == "SELECTIVE"


# ---------------------------------------------------------------------------
# _build_trade_event
# ---------------------------------------------------------------------------


def test_build_trade_event_splits_received_and_sent() -> None:
    txn = {
        "leg": 4,
        "roster_ids": [10, 20],
        "adds": {"pA": 10, "pB": 20},
        "draft_picks": [
            {"season": "2026", "round": 1, "owner_id": 10, "previous_owner_id": 20},
        ],
        "waiver_budget": [{"sender": 20, "receiver": 10, "amount": 15}],
    }
    players_dump = {"pA": {"full_name": "Player A"}, "pB": {"full_name": "Player B"}}
    event = oh._build_trade_event(
        txn,
        season="2024",
        this_roster=10,
        season_roster_to_current={10: 1, 20: 2},
        current_name_by_roster={1: "Owner One", 2: "Owner Two"},
        players_dump=players_dump,
    )
    assert event.season == "2024"
    assert event.week == 4
    assert event.partner_roster_id == 2
    assert event.partner_name == "Owner Two"
    assert "Player A" in event.received
    assert "2026 R1" in event.received
    assert "$15 FAAB" in event.received
    assert event.sent == ["Player B"]
    assert event.picks_received == 1
    assert event.picks_sent == 0


# ---------------------------------------------------------------------------
# _apply_transaction
# ---------------------------------------------------------------------------


def _accumulators(*roster_ids: int) -> dict[int, oh._Accumulator]:
    return {rid: oh._Accumulator(roster_id=rid, user_id=f"u{rid}") for rid in roster_ids}


def test_apply_transaction_trade_updates_both_sides() -> None:
    accs = _accumulators(1, 2)
    txn = {
        "type": "trade",
        "leg": 2,
        "roster_ids": [10, 20],
        "adds": {"pA": 10},
        "drops": {},
        "draft_picks": [],
        "waiver_budget": [],
    }
    oh._apply_transaction(
        txn,
        season_str="2024",
        season_roster_to_current={10: 1, 20: 2},
        current_name_by_roster={1: "One", 2: "Two"},
        accumulators=accs,
        players_dump={"pA": {"full_name": "Player A"}},
    )
    assert len(accs[1].trades) == 1
    assert len(accs[2].trades) == 1
    assert accs[1].partner_counts[2] == 1
    assert accs[1].active_seasons == {"2024"}


def test_apply_transaction_waiver_counts_add_and_faab() -> None:
    accs = _accumulators(1)
    txn = {
        "type": "waiver",
        "leg": 3,
        "adds": {"pA": 10},
        "drops": {},
        "settings": {"waiver_bid": 12},
    }
    oh._apply_transaction(
        txn,
        season_str="2024",
        season_roster_to_current={10: 1},
        current_name_by_roster={1: "One"},
        accumulators=accs,
        players_dump={},
    )
    assert accs[1].waiver_adds == 1
    assert accs[1].faab_spent == 12


def test_apply_transaction_free_agent_and_drop() -> None:
    accs = _accumulators(1)
    txn = {"type": "free_agent", "leg": 1, "adds": {"pA": 10}, "drops": {"pB": 10}}
    oh._apply_transaction(
        txn,
        season_str="2024",
        season_roster_to_current={10: 1},
        current_name_by_roster={1: "One"},
        accumulators=accs,
        players_dump={},
    )
    assert accs[1].free_agent_adds == 1
    assert accs[1].drops == 1


# ---------------------------------------------------------------------------
# _finalize — end-to-end aggregation from accumulators
# ---------------------------------------------------------------------------


def test_finalize_produces_owner_history_with_expected_shape() -> None:
    accs = _accumulators(1, 2)
    accs[1].trades = [
        oh.TradeEvent(
            season="2024", week=2, partner_roster_id=2, partner_name="Two",
            received=["A"], sent=["B"],
        )
    ]
    accs[1].partner_counts.update({2: 1})
    accs[1].active_seasons = {"2024"}
    accs[1].last_season = "2024"
    accs[1].last_week = 2

    owners = oh._finalize(accs, {1: "One", 2: "Two"}, seasons_covered=["2024"])
    by_roster = {o.roster_id: o for o in owners}

    assert by_roster[1].trade_count == 1
    assert by_roster[1].trades_by_season == [{"season": "2024", "count": 1}]
    assert by_roster[2].trade_count == 0
    assert by_roster[2].behavioral_type == "THE GHOST"


# ---------------------------------------------------------------------------
# build_league_history — end-to-end against a fake SleeperClient
# ---------------------------------------------------------------------------


class _FakeHistoryClient:
    """Fake SleeperClient supplying one season with one trade and one waiver add."""

    def __init__(self) -> None:
        self._league = League(league_id="L2024", season="2024", previous_league_id=None)
        self._rosters = [
            Roster(roster_id=1, owner_id="u1", players=["p1"], starters=["p1"]),
            Roster(roster_id=2, owner_id="u2", players=["p2"], starters=["p2"]),
        ]
        self._users = [
            User(user_id="u1", display_name="Owner One"),
            User(user_id="u2", display_name="Owner Two"),
        ]
        self._players = {"pA": {"full_name": "Player A"}, "pB": {"full_name": "Player B"}}

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def league_history(self, league_id=None):
        return [self._league]

    def rosters(self, league_id=None):
        return self._rosters

    def users(self, league_id=None):
        return self._users

    def players(self, force=False):
        return self._players

    def transactions(self, week: int, league_id=None):
        if week == 1:
            return [
                {
                    "status": "complete",
                    "type": "trade",
                    "leg": 1,
                    "roster_ids": [1, 2],
                    "adds": {"pA": 1},
                    "drops": {},
                    "draft_picks": [],
                    "waiver_budget": [],
                },
                {
                    "status": "complete",
                    "type": "waiver",
                    "leg": 1,
                    "adds": {"pB": 1},
                    "drops": {},
                    "settings": {"waiver_bid": 8},
                },
            ]
        return []


def test_build_league_history_end_to_end(monkeypatch) -> None:
    monkeypatch.setattr(oh, "SleeperClient", lambda *a, **k: _FakeHistoryClient())

    history = oh.build_league_history(league_id="L2024")

    assert history.seasons_covered == ["2024"]
    by_roster = {o.roster_id: o for o in history.owners}
    assert by_roster[1].trade_count == 1
    assert by_roster[1].waiver_adds == 1
    assert by_roster[1].faab_spent == 8
    assert by_roster[2].trade_count == 1


def test_build_league_history_no_seasons_returns_empty(monkeypatch) -> None:
    class _NoSeasonsClient(_FakeHistoryClient):
        def league_history(self, league_id=None):
            return []

    monkeypatch.setattr(oh, "SleeperClient", lambda *a, **k: _NoSeasonsClient())

    history = oh.build_league_history(league_id="L2024")

    assert history.seasons_covered == []
    assert history.owners == []
