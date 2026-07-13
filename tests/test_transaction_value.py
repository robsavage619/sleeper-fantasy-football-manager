"""Transaction-value attribution — hermetic unit tests for pure helpers."""

from __future__ import annotations

from sleeper_ffm.model import transaction_value as tv


def test_count_for_current_sums_mapped_rosters() -> None:
    # Season rosters 3 and 7 both map to current roster 2.
    counts = {3: 4, 7: 2, 5: 9}
    season_to_current = {3: 2, 7: 2, 5: 5}
    assert tv._count_for_current(counts, season_to_current, 2) == 6
    assert tv._count_for_current(counts, season_to_current, 5) == 9


def test_count_for_current_unmapped_falls_back_to_self() -> None:
    counts = {4: 3}
    assert tv._count_for_current(counts, {}, 4) == 3


def test_player_name_prefers_full_name() -> None:
    dump = {"1": {"full_name": "Sam Darnold"}, "2": {"search_full_name": "zach ertz"}}
    assert tv._player_name(dump, "1") == "Sam Darnold"
    assert tv._player_name(dump, "2") == "zach ertz"
    assert tv._player_name(dump, "999") == "Player 999"


def test_waiver_methods_constant() -> None:
    assert "waiver" in tv._WAIVER_METHODS
    assert "free_agent" in tv._WAIVER_METHODS
