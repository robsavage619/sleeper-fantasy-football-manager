"""Tests for the canonical player-name normalizer (single shared implementation).

Consolidates what used to be six divergent ``_normalize_name``/``_normalise_name``
implementations across valuation.py, rec_scoreboard.py, trade_acceptance.py,
nflverse/combine.py, cfbd/loader.py, and college/cfb_box.py.
"""

from __future__ import annotations

from sleeper_ffm.names import normalize_name


def test_lowercases_and_collapses_whitespace() -> None:
    assert normalize_name("  Justin   Jefferson  ") == "justin jefferson"


def test_strips_trailing_generational_suffixes() -> None:
    assert normalize_name("Marvin Harrison Jr.") == "marvin harrison"
    assert normalize_name("Marvin Harrison Jr") == "marvin harrison"
    assert normalize_name("Odell Beckham Sr.") == "odell beckham"
    assert normalize_name("Michael Pittman II") == "michael pittman"
    assert normalize_name("Michael Pittman III") == "michael pittman"
    assert normalize_name("Robert Griffin IV") == "robert griffin"
    assert normalize_name("Some Player V") == "some player"


def test_does_not_strip_suffix_mid_string() -> None:
    # "V" only strips as a trailing generational suffix, not as a mid-name token.
    assert normalize_name("Devonta Smith") == "devonta smith"


def test_strips_trailing_position_team_annotation() -> None:
    assert normalize_name("Bijan Robinson (RB ATL)") == "bijan robinson"


def test_ascii_folds_accented_characters() -> None:
    assert normalize_name("Amón-Ra St. Brown") == normalize_name("Amon-Ra St Brown")
    assert normalize_name("Amón-Ra St. Brown") == "amonra st brown"


def test_strips_punctuation_but_keeps_digits() -> None:
    assert normalize_name("D'Andre Swift") == "dandre swift"
    assert normalize_name("Player 3rd") == "player 3rd"


def test_none_and_empty_return_empty_string() -> None:
    assert normalize_name(None) == ""
    assert normalize_name("") == ""


def test_idempotent() -> None:
    once = normalize_name("Marvin Harrison Jr. (WR ARI)")
    twice = normalize_name(once)
    assert once == twice == "marvin harrison"
