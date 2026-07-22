from __future__ import annotations

from dataclasses import dataclass

from sleeper_ffm.model import early_claim_watch as ecw


@dataclass
class _FA:
    """Minimal stand-in for model.free_agents.FreeAgent — same fields rank_early_claims reads."""

    player_id: str
    name: str
    position: str
    team: str
    projected_pts: float
    trending_add_count: int = 0


def test_rank_early_claims_excludes_players_the_herd_already_noticed() -> None:
    pool = [
        _FA("1", "Loud Guy", "WR", "ATL", projected_pts=20.0, trending_add_count=500),
        _FA("2", "Quiet Guy", "WR", "SEA", projected_pts=8.0, trending_add_count=0),
    ]
    out = ecw.rank_early_claims(pool, my_roster_ids=set(), sleeper_players={})
    assert [c.player_id for c in out] == ["2"]


def test_rank_early_claims_sorts_the_quiet_pool_by_projection() -> None:
    pool = [
        _FA("1", "A", "WR", "ATL", projected_pts=6.0, trending_add_count=0),
        _FA("2", "B", "RB", "SEA", projected_pts=12.0, trending_add_count=1),
        _FA("3", "C", "TE", "KC", projected_pts=9.0, trending_add_count=2),
    ]
    out = ecw.rank_early_claims(pool, my_roster_ids=set(), sleeper_players={})
    assert [c.player_id for c in out] == ["2", "3", "1"]


def test_rank_early_claims_respects_top_n() -> None:
    pool = [
        _FA(str(i), f"P{i}", "WR", "ATL", projected_pts=float(i), trending_add_count=0)
        for i in range(10)
    ]
    out = ecw.rank_early_claims(pool, my_roster_ids=set(), sleeper_players={}, top_n=3)
    assert len(out) == 3
    assert [c.player_id for c in out] == ["9", "8", "7"]


def test_rank_early_claims_quiet_threshold_is_configurable() -> None:
    pool = [_FA("1", "A", "WR", "ATL", projected_pts=10.0, trending_add_count=5)]
    assert ecw.rank_early_claims(pool, my_roster_ids=set(), sleeper_players={}) == []
    out = ecw.rank_early_claims(pool, my_roster_ids=set(), sleeper_players={}, quiet_trending_max=5)
    assert len(out) == 1


def test_rank_early_claims_omits_bid_when_no_faab_market_given() -> None:
    pool = [_FA("1", "A", "WR", "ATL", projected_pts=10.0, trending_add_count=0)]
    out = ecw.rank_early_claims(pool, my_roster_ids=set(), sleeper_players={})
    assert out[0].suggested_bid is None


def test_rank_early_claims_finds_a_drop_candidate_from_my_roster() -> None:
    pool = [_FA("new", "New Guy", "WR", "ATL", projected_pts=10.0, trending_add_count=0)]
    sleeper_players = {
        "bench1": {"position": "WR", "search_rank": 9000, "age": 29, "full_name": "Bench Guy"},
        "starter1": {"position": "QB", "search_rank": 5, "age": 26, "full_name": "Star QB"},
    }
    out = ecw.rank_early_claims(
        pool, my_roster_ids={"bench1", "starter1"}, sleeper_players=sleeper_players
    )
    assert out[0].drop_candidate == "Bench Guy"


def test_rank_early_claims_never_suggests_dropping_a_protected_starter() -> None:
    # bench1 has a worse (higher) search_rank than starter1, but starter1 is protected —
    # the missing-search-rank default (9999) must not let a starter dominate the pick.
    pool = [_FA("new", "New Guy", "WR", "ATL", projected_pts=10.0, trending_add_count=0)]
    sleeper_players = {
        "bench1": {"position": "WR", "search_rank": 200, "age": 29, "full_name": "Bench Guy"},
        "starter1": {"position": "WR", "age": 26, "full_name": "Star WR"},  # no search_rank
    }
    out = ecw.rank_early_claims(
        pool,
        my_roster_ids={"bench1", "starter1"},
        sleeper_players=sleeper_players,
        protected_ids={"starter1"},
    )
    assert out[0].drop_candidate == "Bench Guy"


def test_rank_early_claims_no_drop_candidate_when_roster_empty() -> None:
    pool = [_FA("1", "A", "WR", "ATL", projected_pts=10.0, trending_add_count=0)]
    out = ecw.rank_early_claims(pool, my_roster_ids=set(), sleeper_players={})
    assert out[0].drop_candidate is None
