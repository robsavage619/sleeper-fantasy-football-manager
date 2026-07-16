"""Hermetic tests for GM sabermetrics, the fixed optimal-lineup, and symmetric pick counting."""

from __future__ import annotations

import datetime

import polars as pl

from sleeper_ffm.model import gm_metrics as gm
from sleeper_ffm.model import owner_profile as op
from sleeper_ffm.model.owner_skill import optimal_lineup_points
from sleeper_ffm.sleeper.models import Draft, Roster, TradedPick, User

# --- all-play / luck ------------------------------------------------------


def test_all_play_wins_counts_strictly_lower() -> None:
    assert gm.all_play_wins([10.0, 20.0, 30.0], 25.0) == 2
    assert gm.all_play_wins([10.0, 20.0, 30.0], 5.0) == 0


def test_all_play_record_one_week() -> None:
    weeks = [
        [
            {"roster_id": 1, "points": 10.0},
            {"roster_id": 2, "points": 20.0},
            {"roster_id": 3, "points": 30.0},
        ]
    ]
    rec = gm.all_play_record(weeks)
    assert rec[1] == (0, 2)
    assert rec[2] == (1, 2)
    assert rec[3] == (2, 2)


def test_close_game_record_pairs_by_matchup() -> None:
    weeks = [
        [
            {"roster_id": 1, "points": 100.0, "matchup_id": 1},
            {"roster_id": 2, "points": 97.0, "matchup_id": 1},
            {"roster_id": 3, "points": 80.0, "matchup_id": 2},
            {"roster_id": 4, "points": 70.0, "matchup_id": 2},
        ]
    ]
    rec = gm.close_game_record(weeks, margin=5.0)
    assert rec[1] == {"close_wins": 1, "close_losses": 0, "one_score_games": 1}
    assert rec[2] == {"close_wins": 0, "close_losses": 1, "one_score_games": 1}
    # 10-point game is not close -> rosters 3, 4 absent
    assert 3 not in rec and 4 not in rec


def test_luck_index_known_values() -> None:
    # 8 actual wins, 50% all-play over a 14-game slate -> expected 7 -> +1.0 luck
    assert gm.luck_index(8.0, 0.5, 14.0) == 1.0


def test_trade_ledger_pnl_reconciles_to_hand_math() -> None:
    trades = [{"received": ["A", "2026 R1"], "sent": ["B"]}]
    values = {"A": 50.0, "2026 R1": 80.0, "B": 30.0}
    out = gm.trade_ledger_pnl(trades, values)
    assert out["value_in"] == 130.0
    assert out["value_out"] == 30.0
    assert out["net"] == 100.0
    assert out["trade_count"] == 1
    assert out["resolved"] == 3
    assert out["unresolved"] == 0


def test_trade_ledger_pnl_counts_unresolved() -> None:
    trades = [{"received": ["Ghost"], "sent": []}]
    out = gm.trade_ledger_pnl(trades, {})
    assert out["unresolved"] == 1
    assert out["resolved"] == 0
    assert out["net"] == 0.0


# --- realized-production trade ledger (v2) --------------------------------


def _weekly(rows: list[tuple[str, int, int, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_display_name": pl.Utf8,
            "season": pl.Int64,
            "week": pl.Int64,
            "fp_sffm": pl.Float64,
        },
        orient="row",
    )


def test_is_pick_key() -> None:
    assert gm.is_pick_key("2026 R1")
    assert not gm.is_pick_key("Derrick Henry")


def test_realized_player_production_sums_only_after_trade_date() -> None:
    weekly = _weekly(
        [
            ("A", 2024, 5, 10.0),  # before the trade -> excluded
            ("A", 2024, 6, 12.0),  # trade week itself -> excluded
            ("A", 2024, 7, 15.0),  # after -> counted
            ("A", 2025, 1, 20.0),  # following season -> counted
        ]
    )
    fp = gm.realized_player_production("A", since_season=2024, since_week=6, weekly_scored=weekly)
    assert fp == 35.0


def test_realized_player_production_unresolved_name_is_none() -> None:
    weekly = _weekly([("A", 2024, 5, 10.0)])
    assert gm.realized_player_production("Ghost", 2024, 5, weekly) is None


def test_realized_player_production_real_zero_after_trade() -> None:
    # Player is known but never played again after the trade — a real 0, not unresolved.
    weekly = _weekly([("A", 2024, 5, 10.0)])
    assert gm.realized_player_production("A", 2024, 5, weekly) == 0.0


def test_realized_trade_ledger_pnl_values_players_by_post_trade_production() -> None:
    weekly = _weekly(
        [
            ("A", 2024, 6, 12.0),
            ("A", 2024, 7, 15.0),  # A produces 15 after the trade
            ("B", 2024, 7, 5.0),  # B produces 5 after the trade
        ]
    )
    trades = [{"season": "2024", "week": 6, "received": ["A"], "sent": ["B", "2026 R1"]}]
    out = gm.realized_trade_ledger_pnl(trades, weekly, pick_values={"2026 R1": 80.0})
    assert out["value_in"] == 15.0
    assert out["value_out"] == 5.0 + 80.0
    assert out["net"] == 15.0 - 85.0
    assert out["resolved"] == 3
    assert out["unresolved"] == 0


def test_realized_trade_ledger_pnl_unresolved_pick_and_unknown_player() -> None:
    weekly = _weekly([("A", 2024, 6, 12.0)])
    trades = [{"season": "2024", "week": 6, "received": ["Ghost", "2099 R9"], "sent": []}]
    out = gm.realized_trade_ledger_pnl(trades, weekly, pick_values={})
    assert out["unresolved"] == 2
    assert out["resolved"] == 0


# --- fixed optimal lineup respects position eligibility -------------------


def test_optimal_lineup_respects_positions() -> None:
    # A roster stacked with WRs: naive top-8-of-all would field an illegal lineup.
    players_points = {
        "qb1": 25.0,
        "wr1": 24.0,
        "wr2": 23.0,
        "wr3": 22.0,
        "wr4": 21.0,
        "wr5": 20.0,
        "rb1": 5.0,
        "te1": 4.0,
    }
    positions = {
        "qb1": "QB",
        "wr1": "WR",
        "wr2": "WR",
        "wr3": "WR",
        "wr4": "WR",
        "wr5": "WR",
        "rb1": "RB",
        "te1": "TE",
    }
    slots = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "BN", "BN"]
    # Legal optimal: QB25 + RB5 + (empty RB 0) + WR24 + WR23 + TE4 + FLEX(WR22 + WR21) = 124
    assert optimal_lineup_points(players_points, positions, slots) == 124.0
    # The illegal naive sum would be 25+24+23+22+21+20+5+4 = 144 (must NOT be returned)
    assert optimal_lineup_points(players_points, positions, slots) != 144.0


def test_optimal_lineup_empty_roster() -> None:
    assert optimal_lineup_points({}, {}, ["QB", "RB", "FLEX"]) == 0.0


# --- owner_profile symmetric pick counting --------------------------------


class _FakeClient:
    """Minimal SleeperClient stand-in returning frozen league data."""

    def __init__(self, users, rosters, picks, players, draft) -> None:
        self._users = users
        self._rosters = rosters
        self._picks = picks
        self._players = players
        self._draft = draft

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def users(self, league_id=None):
        return self._users

    def rosters(self, league_id=None):
        return self._rosters

    def traded_picks(self, league_id=None):
        return self._picks

    def players(self, force=False):
        return self._players

    def draft(self, draft_id):
        return self._draft


def test_owner_profile_pick_count_is_symmetric(monkeypatch) -> None:
    cy = datetime.date.today().year
    users = [
        User(user_id="u1", display_name="One"),
        User(user_id="u2", display_name="Two"),
    ]
    rosters = [
        Roster(roster_id=1, owner_id="u1", players=["p1"], starters=["p1"], taxi=[], reserve=[]),
        Roster(roster_id=2, owner_id="u2", players=["p2"], starters=["p2"], taxi=[], reserve=[]),
    ]
    # Roster 1 traded away only its (cy, R3) pick to roster 2. No other round is ever traded.
    picks = [TradedPick(season=str(cy), round=3, roster_id=1, owner_id=2, previous_owner_id=1)]
    players = {"p1": {"position": "QB"}, "p2": {"position": "RB"}}
    draft = Draft(draft_id="d1", settings={"rounds": 4})

    def _fake(*args, **kwargs):
        return _FakeClient(users, rosters, picks, players, draft)

    monkeypatch.setattr(op, "SleeperClient", _fake)

    profiles = {p.roster_id: p for p in op.build_owner_profiles()}
    # Live space = 2 seasons (cy, cy+1) x 4 configured rounds = 8 own slots.
    # Roster 1 traded away 1 -> holds 7 own + 0 foreign = 7 (NOT understated to ~1).
    assert profiles[1].picks_owned == 7
    assert profiles[1].picks_given == 1
    # Roster 2 kept all 8 own + received 1 foreign = 9 (symmetric with roster 1's outflow).
    assert profiles[2].picks_owned == 9
    assert profiles[2].picks_given == 0
