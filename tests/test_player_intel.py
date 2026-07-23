"""Player intel composition tests (pure — no network, no cached parquet)."""

from __future__ import annotations

import polars as pl
import pytest

from sleeper_ffm.model import player_intel as pi


def _row(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "player_id": "p1",
        "name": "Test Player",
        "position": "RB",
        "team": "AAA",
        "season_age": 26.0,
        "team_changed": False,
        "coach_changed": False,
        "qb_changed": False,
        "draft_round": 3.0,
        "draft_year": 2019.0,
    }
    base.update(over)
    return base


def test_moved_back_gets_an_alert() -> None:
    flags = pi.situation_flags(_row(position="RB", team_changed=True))
    kinds = {f.kind: f for f in flags}
    assert kinds["usage_history_void"].severity == "ALERT"
    assert "-0.279" in kinds["usage_history_void"].evidence


def test_moved_receiver_is_told_not_to_discount() -> None:
    """S2 found no replicable WR penalty; the flag must say so rather than warn."""
    flags = pi.situation_flags(_row(position="WR", team_changed=True))
    kinds = {f.kind: f for f in flags}
    assert kinds["role_travels"].severity == "INFO"
    assert "do not discount" in kinds["role_travels"].headline


def test_team_change_supersedes_coach_change_for_backs() -> None:
    """A back who moved also has a new coach; flagging both would double-count one event."""
    flags = pi.situation_flags(_row(position="RB", team_changed=True, coach_changed=True))
    kinds = {f.kind for f in flags}
    assert "usage_history_void" in kinds
    assert "play_caller_change" not in kinds


def test_qb_change_flag_points_at_efficiency_not_volume() -> None:
    flags = pi.situation_flags(_row(position="WR", qb_changed=True))
    flag = next(f for f in flags if f.kind == "qb_change_efficiency")
    assert "efficiency, not volume" in flag.headline
    assert "0.93" in flag.evidence


def test_qb_change_does_not_flag_running_backs() -> None:
    flags = pi.situation_flags(_row(position="RB", qb_changed=True))
    assert not any(f.kind == "qb_change_efficiency" for f in flags)


def test_attrition_severity_tracks_the_measured_rate() -> None:
    high = pi.attrition_flag("RB", "receiving_back", 30.0)
    low = pi.attrition_flag("RB", "grinder", 23.0)
    assert high is not None and high.severity == "ALERT"
    assert "56%" in high.headline
    assert low is not None and low.severity == "INFO"


def test_attrition_absent_without_an_archetype() -> None:
    assert pi.attrition_flag("RB", None, 30.0) is None
    assert pi.attrition_flag("RB", "grinder", None) is None


def test_draft_tier_collapses_rounds() -> None:
    assert pi.draft_tier(1.0) == "A"
    assert pi.draft_tier(2.0) == "A"
    assert pi.draft_tier(5.0) == "B"
    assert pi.draft_tier(7.0) == "C"
    assert pi.draft_tier(None) == "C"


def test_rookie_flag_only_fires_for_rookies() -> None:
    assert pi.rookie_flag("RB", 1.0, is_rookie=False) is None
    flag = pi.rookie_flag("RB", 1.0, is_rookie=True)
    assert flag is not None
    assert "safest rookie asset" in flag.headline


def test_rookie_quarterback_flagged_as_least_reliable() -> None:
    flag = pi.rookie_flag("QB", 1.0, is_rookie=True)
    assert flag is not None
    assert "least reliable" in flag.headline


def test_flags_are_ordered_most_severe_first() -> None:
    intel = pi.build_player_intel(
        _row(position="RB", team_changed=True, season_age=23.0),
        archetype="grinder",
    )
    severities = [f.severity for f in intel.flags]
    assert severities == sorted(severities, key=lambda s: {"ALERT": 0, "WATCH": 1, "INFO": 2}[s])
    assert intel.alert_count >= 1


def test_roster_scoping_filters_to_held_players() -> None:
    context = pl.DataFrame(
        [
            {
                **_row(player_id="mine", name="Mine", team_changed=True),
                "season": 2025,
                "sleeper_id": 111.0,
            },
            {
                **_row(player_id="theirs", name="Theirs", team_changed=True),
                "season": 2025,
                "sleeper_id": 222.0,
            },
        ]
    )
    scoped = pi.build_roster_intel(context, sleeper_ids={"111"})
    assert [i.name for i in scoped] == ["Mine"]


def test_empty_context_returns_nothing() -> None:
    assert pi.build_roster_intel(pl.DataFrame()) == []


def test_rookie_hit_rates_maps_capital_to_tiers(monkeypatch) -> None:
    """Every drafted rookie gets a base rate; missing capital falls to tier C."""
    id_map = pl.DataFrame(
        [
            {
                "sleeper_id": 1.0,
                "position": "RB",
                "draft_year": 2026.0,
                "draft_round": 1.0,
            },
            {
                "sleeper_id": 2.0,
                "position": "QB",
                "draft_year": 2026.0,
                "draft_round": 1.0,
            },
            {
                "sleeper_id": 3.0,
                "position": "WR",
                "draft_year": 2026.0,
                "draft_round": 4.0,
            },
            {
                "sleeper_id": 4.0,
                "position": "TE",
                "draft_year": 2026.0,
                "draft_round": None,
            },
            {
                "sleeper_id": 9.0,
                "position": "WR",
                "draft_year": 2025.0,
                "draft_round": 1.0,
            },
        ]
    )
    monkeypatch.setattr("sleeper_ffm.nflverse.loader.load_id_map", lambda: id_map, raising=True)

    rates = pi.rookie_hit_rates(2026)

    # The 2025 entrant must not appear in a 2026 class.
    assert set(rates) == {"1", "2", "3", "4"}
    assert rates["1"]["tier"] == "A"
    # Same tier, different lineup value: backs are far safer than quarterbacks here.
    assert rates["1"]["position_rate"] == pytest.approx(0.882)
    assert rates["2"]["position_rate"] == pytest.approx(0.389)
    assert rates["3"]["tier"] == "B"
    # Undrafted collapses to tier C, and position_rate only applies inside tier A.
    assert rates["4"]["tier"] == "C"
    assert rates["4"]["position_rate"] is None


# ---- frozen study effect sizes -------------------------------------------
#
# These tables are snapshots of studies S2-S6. They are literals by design, but
# nothing recomputes them, so the guard here is that they stay internally
# coherent and stay wired to the study module that owns them.


def test_qb_quality_effect_is_shared_with_the_study_that_produced_it() -> None:
    from sleeper_ffm.model.research import qb_quality

    assert pi.QB_QUALITY_PTS_PER_SD is qb_quality.QB_QUALITY_PTS_PER_SD_BY_POSITION
    # The study's WR headline and the per-position table cannot disagree.
    assert pi.QB_QUALITY_PTS_PER_SD["WR"] == qb_quality.QB_QUALITY_PTS_PER_SD


def test_rookie_tiers_are_ordered_and_bracketed_by_their_intervals() -> None:
    rates = [pi.ROOKIE_TIERS[t][0] for t in ("A", "B", "C")]
    assert rates == sorted(rates, reverse=True), "draft capital must not invert"
    for tier, (rate, lo, hi) in pi.ROOKIE_TIERS.items():
        assert lo <= rate <= hi, f"tier {tier} rate outside its Wilson interval"
        assert 0.0 <= lo <= hi <= 1.0


def test_tier_a_position_rates_are_probabilities() -> None:
    assert set(pi.TIER_A_BY_POSITION) == {"RB", "WR", "TE", "QB"}
    assert all(0.0 <= v <= 1.0 for v in pi.TIER_A_BY_POSITION.values())


def test_attrition_table_is_complete_and_probabilistic() -> None:
    expected_bands = {"22-24", "25-27", "28+"}
    seen_bands: dict[tuple[str, str], set[str]] = {}
    for (position, archetype, band), rate in pi.ATTRITION.items():
        assert 0.0 <= rate <= 1.0, f"{position}/{archetype}/{band} is not a probability"
        seen_bands.setdefault((position, archetype), set()).add(band)
    for key, bands in seen_bands.items():
        assert bands == expected_bands, f"{key} is missing an age band"


def test_rb_situation_change_gaps_are_penalties() -> None:
    # S2 found a carryover penalty for backs who move; a positive value here
    # would silently invert the situation-change flag.
    assert pi.RB_TEAM_CHANGE_GAP < 0
    assert pi.RB_COACH_CHANGE_GAP < 0
