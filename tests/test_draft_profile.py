"""Draft-profile helpers — hermetic unit tests."""

from __future__ import annotations

from sleeper_ffm.model import draft_profile as dp


def test_lean_heavy() -> None:
    assert dp._lean({"RB": 6, "WR": 3, "TE": 1, "QB": 1}) == "RB-HEAVY"


def test_lean_lean() -> None:
    # 4/10 = 0.4 → LEAN (>= 0.35, < 0.45)
    assert dp._lean({"WR": 4, "RB": 3, "TE": 2, "QB": 1}) == "WR-LEAN"


def test_lean_balanced() -> None:
    assert dp._lean({"RB": 3, "WR": 3, "TE": 2, "QB": 2}) == "BALANCED"


def test_lean_empty() -> None:
    assert dp._lean({}) == "—"


def test_hit_value_is_positive() -> None:
    assert dp._HIT_VALUE > 0
