from __future__ import annotations

from sleeper_ffm.season.startsit import PlayerProjection, _compute_changes

_POS = {"qb2": "QB", "rb1": "RB", "wr1": "WR", "qb1": "QB", "wr2": "WR"}


def _proj(pid: str, pos: str, pts: float) -> PlayerProjection:
    return PlayerProjection(pid, pid, pos, "", pts, "MED", "default", "")


def test_qb_never_paired_with_non_qb() -> None:
    optimal = [_proj("qb2", "QB", 25.0), _proj("rb1", "RB", 15.0)]
    current = [_proj("qb1", "QB", 10.0), _proj("wr1", "WR", 8.0)]
    changes = _compute_changes(optimal, current)
    for change in changes:
        start_pos = _POS[change["start"]]
        sit_pos = _POS[change["sit"]]
        if "QB" in (start_pos, sit_pos):
            assert start_pos == "QB" and sit_pos == "QB"


def test_same_position_swap_is_preferred() -> None:
    optimal = [_proj("qb2", "QB", 25.0)]
    current = [_proj("qb1", "QB", 10.0)]
    changes = _compute_changes(optimal, current)
    assert changes == [{"start": "qb2", "sit": "qb1", "gain": 15.0}]


def test_flex_swap_pairs_skill_positions() -> None:
    optimal = [_proj("rb1", "RB", 18.0)]
    current = [_proj("wr2", "WR", 9.0)]
    changes = _compute_changes(optimal, current)
    assert changes == [{"start": "rb1", "sit": "wr2", "gain": 9.0}]
