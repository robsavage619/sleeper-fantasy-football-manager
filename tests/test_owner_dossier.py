"""Hermetic tests for owner_dossier.build_dossier — the backbone of every trade offer.

Follows the house DI-seam pattern (see test_gm_metrics.py's ``_FakeClient``): a fake
SleeperClient supplies frozen league data, and the network-touching valuation/market
seams (``build_player_assets_cached``, ``build_player_blend``, ``value_pick``) are
monkeypatched to deterministic fakes so no nflverse/FantasyCalc fetch is required.
"""

from __future__ import annotations

from sleeper_ffm.market.blend import MarketBlend
from sleeper_ffm.model import owner_dossier as od
from sleeper_ffm.model.dynasty import PlayerAsset
from sleeper_ffm.sleeper.models import Draft, Roster, TradedPick, User


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

    def rosters(self, league_id=None):
        return self._rosters

    def users(self, league_id=None):
        return self._users

    def players(self, force=False):
        return self._players

    def traded_picks(self, league_id=None):
        return self._picks

    def draft(self, draft_id):
        return self._draft


_EMPTY_BLEND = MarketBlend(
    market={}, fc_scale=1.0, values={}, market_valued=frozenset(), model_valued_only=True
)


def _install_fakes(
    monkeypatch,
    users: list[User],
    rosters: list[Roster],
    picks: list[TradedPick],
    players: dict[str, dict],
    draft: Draft,
    vet_assets: list[PlayerAsset] | None = None,
) -> None:
    """Wire the fake SleeperClient and stub the network-touching valuation seams."""
    monkeypatch.setattr(
        od, "SleeperClient", lambda *a, **k: _FakeClient(users, rosters, picks, players, draft)
    )
    monkeypatch.setattr(
        od, "build_player_assets_cached", lambda seasons, sleeper_players: vet_assets or []
    )
    monkeypatch.setattr(od, "build_player_blend", lambda assets: _EMPTY_BLEND)
    # Deterministic pick pricing, independent of the live FantasyCalc pick market.
    pick_values = {1: 100.0, 2: 50.0, 3: 20.0}
    monkeypatch.setattr(od, "value_pick", lambda pick: pick_values.get(pick.round, 5.0))


def _two_roster_league() -> tuple[list[User], list[Roster], dict[str, dict], Draft]:
    users = [
        User(user_id="u1", display_name="Owner One"),
        User(user_id="u2", display_name="Owner Two"),
    ]
    rosters = [
        Roster(
            roster_id=1,
            owner_id="u1",
            players=["p1", "p2"],
            starters=["p1"],
            taxi=[],
            reserve=[],
        ),
        Roster(
            roster_id=2,
            owner_id="u2",
            players=["p3"],
            starters=["p3"],
            taxi=[],
            reserve=[],
        ),
    ]
    players = {
        "p1": {"position": "WR", "full_name": "Young Riser", "age": 23, "team": "KC"},
        "p2": {"position": "RB", "full_name": "Old Veteran", "age": 32, "team": "SF"},
        "p3": {"position": "QB", "full_name": "Steady Owner Two", "age": 27, "team": "BUF"},
    }
    draft = Draft(draft_id="d1", settings={"rounds": 4})
    return users, rosters, players, draft


def _vet_assets() -> list[PlayerAsset]:
    return [
        PlayerAsset(player_id="p1", name="Young Riser", position="WR", age=23, current_fpar=60.0),
        PlayerAsset(player_id="p2", name="Old Veteran", position="RB", age=32, current_fpar=10.0),
        PlayerAsset(
            player_id="p3", name="Steady Owner Two", position="QB", age=27, current_fpar=40.0
        ),
    ]


def test_build_dossier_roster_not_found_raises(monkeypatch) -> None:
    users, rosters, players, draft = _two_roster_league()
    _install_fakes(monkeypatch, users, rosters, [], players, draft, _vet_assets())
    try:
        od.build_dossier(99, season=2025)
    except ValueError as exc:
        assert "99" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown roster_id")


def test_build_dossier_basic_fields(monkeypatch) -> None:
    users, rosters, players, draft = _two_roster_league()
    _install_fakes(monkeypatch, users, rosters, [], players, draft, _vet_assets())

    dossier = od.build_dossier(1, season=2025)

    assert dossier.roster_id == 1
    assert dossier.user_id == "u1"
    assert dossier.display_name == "Owner One"
    assert dossier.player_count == 2
    assert {p["player_id"] for p in dossier.players} == {"p1", "p2"}
    # dynasty_value is derived from the model (no market blend), so it must be positive
    # for both rostered skill players.
    assert all(p["dynasty_value"] > 0 for p in dossier.players)
    assert dossier.total_dynasty_value == round(sum(p["dynasty_value"] for p in dossier.players), 1)


def test_build_dossier_age_buckets_partition_players(monkeypatch) -> None:
    users, rosters, players, draft = _two_roster_league()
    _install_fakes(monkeypatch, users, rosters, [], players, draft, _vet_assets())

    dossier = od.build_dossier(1, season=2025)

    # p1 is 23 (<=23 band), p2 is 32 (30-32 band) -> exactly one player in each of those
    # buckets and zero in every other band.
    by_label = {b.label: b for b in dossier.age_buckets}
    assert by_label["≤23"].count == 1
    assert by_label["30–32"].count == 1  # noqa: RUF001
    assert sum(b.count for b in dossier.age_buckets) == 2


def test_build_dossier_value_by_position_only_covers_roster_positions(monkeypatch) -> None:
    users, rosters, players, draft = _two_roster_league()
    _install_fakes(monkeypatch, users, rosters, [], players, draft, _vet_assets())

    dossier = od.build_dossier(1, season=2025)

    by_pos = {v.position: v for v in dossier.value_by_position}
    assert by_pos["WR"].count == 1
    assert by_pos["RB"].count == 1
    assert by_pos["QB"].count == 0
    assert by_pos["TE"].count == 0
    total_pct = round(sum(v.pct for v in dossier.value_by_position))
    assert total_pct == 100


def test_build_dossier_contention_window_favors_youth(monkeypatch) -> None:
    users, rosters, players, draft = _two_roster_league()
    # Roster 1 skews young (23 + 32); make it lopsided young to pin a clear label.
    vet_assets = [
        PlayerAsset(player_id="p1", name="Young Riser", position="WR", age=22, current_fpar=80.0),
        PlayerAsset(player_id="p2", name="Old Veteran", position="RB", age=24, current_fpar=70.0),
        PlayerAsset(
            player_id="p3", name="Steady Owner Two", position="QB", age=27, current_fpar=40.0
        ),
    ]
    players["p2"]["age"] = 24
    _install_fakes(monkeypatch, users, rosters, [], players, draft, vet_assets)

    dossier = od.build_dossier(1, season=2025)

    # Both roster-1 players are <=25 -> 100% youth share, 0% vet share -> top label.
    assert dossier.contention.label == "ASCENDING"
    assert dossier.contention.score == 100.0


def test_build_dossier_value_rank_and_position_ranks(monkeypatch) -> None:
    users, rosters, players, draft = _two_roster_league()
    _install_fakes(monkeypatch, users, rosters, [], players, draft, _vet_assets())

    dossier = od.build_dossier(1, season=2025)

    assert dossier.league_size == 2
    assert dossier.value_rank in (1, 2)
    positions_seen = {r.position for r in dossier.position_ranks}
    assert positions_seen == {"QB", "RB", "WR", "TE"}
    for r in dossier.position_ranks:
        assert r.of == 2
        assert r.rank in (1, 2)


def test_build_dossier_picks_owned_and_traded_away(monkeypatch) -> None:
    import datetime

    cy = datetime.date.today().year
    users, rosters, players, draft = _two_roster_league()
    # Roster 1 traded away its (cy, R3) pick to roster 2; roster 2 sends it a foreign pick back.
    picks = [
        TradedPick(season=str(cy), round=3, roster_id=1, owner_id=2, previous_owner_id=1),
        TradedPick(season=str(cy), round=1, roster_id=2, owner_id=1, previous_owner_id=2),
    ]
    _install_fakes(monkeypatch, users, rosters, picks, players, draft, _vet_assets())

    dossier = od.build_dossier(1, season=2025)

    assert {"season": str(cy), "round": 3} in dossier.picks_traded_away
    acquired = [p for p in dossier.picks_owned if p["source"] == "acquired"]
    assert any(p["season"] == str(cy) and p["round"] == 1 for p in acquired)
    own = [p for p in dossier.picks_owned if p["source"] == "own"]
    assert all(not (p["season"] == str(cy) and p["round"] == 3) for p in own)
