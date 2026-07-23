"""Valuation blending — deterministic unit tests (no network, no parquet)."""

from __future__ import annotations

from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.model.valuation import _SEASON_WEIGHTS


def test_season_weights_track_the_configured_value_season() -> None:
    # Derived from DEFAULT_VALUE_SEASON so a rollover cannot silently invert the
    # recency weighting: with hardcoded keys the newer season would miss the map
    # and fall to the 1/n default, leaving the OLDER season weighted higher.
    assert _SEASON_WEIGHTS == {
        DEFAULT_VALUE_SEASON - 1: 0.35,
        DEFAULT_VALUE_SEASON: 0.65,
    }


def test_latest_season_outweighs_prior_season() -> None:
    assert _SEASON_WEIGHTS[DEFAULT_VALUE_SEASON] > _SEASON_WEIGHTS[DEFAULT_VALUE_SEASON - 1]
