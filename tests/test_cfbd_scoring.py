"""CFBD prospect scoring — pure unit tests, no network calls.

These guard the failure modes that only became visible once a CFBD key was
configured: a one-catch receiver topping the board, backs crowding out every
other position, and a college player inheriting an established professional's
market value through a name collision.
"""

from __future__ import annotations

from sleeper_ffm.cfbd.loader import (
    _YPR_PRIOR,
    _build_sleeper_index,
    _shrink_ypr,
    _usage_rate,
)

# ---- yards-per-reception shrinkage ----


def test_one_catch_ypr_collapses_toward_the_prior() -> None:
    # 75 yards on a single reception used to score as elite production.
    shrunk = _shrink_ypr(75.0, receptions=1)
    assert shrunk < 20.0
    assert shrunk > _YPR_PRIOR


def test_full_season_ypr_barely_moves() -> None:
    assert abs(_shrink_ypr(13.0, receptions=60) - 13.0) < 0.5


def test_more_receptions_means_less_shrinkage() -> None:
    inflated = 40.0
    assert _shrink_ypr(inflated, 2) < _shrink_ypr(inflated, 20) < _shrink_ypr(inflated, 200)


def test_no_receptions_scores_zero_not_the_prior() -> None:
    assert _shrink_ypr(0.0, receptions=0) == 0.0


def test_shrunk_ypr_never_exceeds_the_observation() -> None:
    assert _shrink_ypr(30.0, receptions=5) <= 30.0


# ---- usage extraction ----


def test_usage_rate_prefers_overall() -> None:
    assert _usage_rate({"usage": {"overall": 0.292, "passingDowns": 0.1}}) == 0.292


def test_usage_rate_falls_back_to_passing_downs() -> None:
    assert _usage_rate({"usage": {"overall": 0, "passingDowns": 0.18}}) == 0.18


def test_usage_rate_handles_a_missing_block() -> None:
    assert _usage_rate({}) == 0.0


# ---- Sleeper matching ----


def _dump() -> dict[str, dict]:
    return {
        "veteran_qb": {"full_name": "Caleb Williams", "position": "QB", "years_exp": 2},
        "rookie_rb": {"full_name": "Caleb Williams", "position": "RB", "years_exp": 0},
        "rookie_wr": {"full_name": "Carnell Tate", "position": "WR", "years_exp": 0},
        "no_position": {"full_name": "Nameless Guy", "position": None, "years_exp": 0},
    }


def test_established_professional_is_not_a_draft_prospect_match() -> None:
    index = _build_sleeper_index(_dump())
    # The veteran quarterback must not be reachable under any key — inheriting
    # his market value is what floated a college back to third overall.
    assert "veteran_qb" not in index.values()


def test_rookie_of_the_same_name_still_matches_on_position() -> None:
    index = _build_sleeper_index(_dump())
    assert index[("caleb williams", "RB")] == "rookie_rb"
    assert index[("carnell tate", "WR")] == "rookie_wr"


def test_position_mismatch_does_not_resolve() -> None:
    index = _build_sleeper_index(_dump())
    assert index.get(("carnell tate", "RB")) is None


def test_players_without_a_usable_position_are_skipped() -> None:
    assert "no_position" not in _build_sleeper_index(_dump()).values()


# ---- position balance in the returned pool ----


def _usage_entry(name: str, position: str, overall: float, team: str = "Some U") -> dict:
    return {"name": name, "position": position, "team": team, "usage": {"overall": overall}}


def test_backs_do_not_crowd_out_other_positions(monkeypatch) -> None:
    """A trimmed pool must keep the leaders at every position.

    The scoring functions are on incomparable scales — a back's raw score is
    rushing yards over ten, a receiver's tops out far lower — so a single global
    ranking handed the board to running backs and dropped real receivers.
    """
    from sleeper_ffm.cfbd import loader

    monkeypatch.setenv("CFBD_API_KEY", "test-key-not-a-real-credential")

    usage = [_usage_entry(f"Back {i}", "RB", 0.30) for i in range(40)]
    usage += [_usage_entry(f"Receiver {i}", "WR", 0.20) for i in range(40)]
    usage += [_usage_entry(f"End {i}", "TE", 0.10) for i in range(40)]

    # Backs carry huge raw scores; receivers cannot reach them on their own scale.
    stats = {loader.normalize_name(f"Back {i}"): {"rushing": {"YDS": 1500 - i}} for i in range(40)}
    stats.update(
        {
            loader.normalize_name(f"Receiver {i}"): {"receiving": {"YPR": 14.0, "REC": 60}}
            for i in range(40)
        }
    )

    monkeypatch.setattr(loader, "_fetch_usage", lambda *_a, **_k: usage)
    monkeypatch.setattr(loader, "_fetch_recruiting_window", lambda *_a, **_k: {})
    monkeypatch.setattr(loader, "_fetch_player_season_stats", lambda *_a, **_k: stats)

    class _EmptySleeper:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def players(self) -> dict:
            return {}

    monkeypatch.setattr(
        "sleeper_ffm.sleeper.client.SleeperClient", lambda *_a, **_k: _EmptySleeper()
    )

    got = loader.load_prospects(year=2026, top=12)
    positions = {p.position for p in got}
    assert {"RB", "WR", "TE"} <= positions, f"a position was crowded out: {positions}"
