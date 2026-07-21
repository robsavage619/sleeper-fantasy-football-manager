from __future__ import annotations

from sleeper_ffm.model.free_agents import _MIN_PTS, rank_free_agents
from sleeper_ffm.model.projections import PlayerProjection


def _proj(pid: str, pos: str, pts: float, injury: str | None = None) -> PlayerProjection:
    return PlayerProjection(
        player_id=pid,
        name=f"P{pid}",
        position=pos,
        team="BUF",
        opponent="NYJ",
        league_points=pts,
        provider_points=pts,
        injury_status=injury,
    )


def test_ranks_unrostered_skill_players_by_projection() -> None:
    projections = {
        "a": _proj("a", "RB", 18.0),
        "b": _proj("b", "WR", 12.0),
        "c": _proj("c", "RB", 20.0),
    }
    board = rank_free_agents(projections, rostered=set(), trending={}, top_n=5)
    assert [fa.player_id for fa in board.overall] == ["c", "a", "b"]  # sorted desc


def test_rostered_players_are_excluded() -> None:
    projections = {"a": _proj("a", "RB", 18.0), "b": _proj("b", "RB", 20.0)}
    board = rank_free_agents(projections, rostered={"b"}, trending={}, top_n=5)
    assert [fa.player_id for fa in board.overall] == ["a"]  # b is rostered


def test_hard_out_players_are_dropped_but_questionable_kept() -> None:
    projections = {
        "out": _proj("out", "RB", 20.0, injury="Out"),
        "ir": _proj("ir", "WR", 15.0, injury="IR"),
        "q": _proj("q", "WR", 12.0, injury="Questionable"),
    }
    board = rank_free_agents(projections, rostered=set(), trending={}, top_n=5)
    ids = [fa.player_id for fa in board.overall]
    assert "out" not in ids and "ir" not in ids  # hard-outs dropped
    assert "q" in ids  # Questionable kept (provider already priced it)
    q = next(fa for fa in board.overall if fa.player_id == "q")
    assert q.projected_pts == 12.0 and q.injury_status == "Questionable"


def test_roster_filler_below_the_floor_is_dropped() -> None:
    projections = {"scrub": _proj("scrub", "WR", _MIN_PTS - 0.1), "ok": _proj("ok", "WR", 10.0)}
    board = rank_free_agents(projections, rostered=set(), trending={}, top_n=5)
    assert [fa.player_id for fa in board.overall] == ["ok"]


def test_trending_add_count_is_attached() -> None:
    projections = {"hot": _proj("hot", "RB", 14.0)}
    board = rank_free_agents(projections, rostered=set(), trending={"hot": 1098}, top_n=5)
    assert board.overall[0].trending_add_count == 1098


def test_by_position_buckets_and_respects_top_n() -> None:
    projections = {str(i): _proj(str(i), "RB", float(20 - i)) for i in range(5)}
    board = rank_free_agents(projections, rostered=set(), trending={}, top_n=3)
    assert len(board.by_position["RB"]) == 3  # capped at top_n
    assert board.by_position["QB"] == []  # none available
    assert [fa.player_id for fa in board.by_position["RB"]] == ["0", "1", "2"]
