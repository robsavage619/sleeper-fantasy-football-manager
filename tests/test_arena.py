from __future__ import annotations

from sleeper_ffm.evals import arena

# A simple 1QB/1RB/1WR/1FLEX lineup for the pure-logic tests.
_SLOTS = ["QB", "RB", "WR", "FLEX", "BN", "BN"]
_POS = {
    "qb1": "QB",
    "qb2": "QB",
    "rb1": "RB",
    "rb2": "RB",
    "wr1": "WR",
    "wr2": "WR",
    "te1": "TE",
}


def test_select_lineup_fills_dedicated_slots_then_flex() -> None:
    scores = {"qb1": 25, "qb2": 10, "rb1": 20, "rb2": 18, "wr1": 15, "wr2": 5, "te1": 12}
    chosen = arena.select_lineup(scores, _POS, _SLOTS)
    assert set(chosen) == {
        "qb1",
        "rb1",
        "wr1",
        "rb2",
    }  # FLEX takes the best leftover (rb2 18 > te1 12)
    assert len(chosen) == 4


def test_select_lineup_leaves_a_slot_empty_when_no_eligible_player() -> None:
    # No QB on the roster → the QB slot goes unfilled rather than starting an ineligible player.
    chosen = arena.select_lineup({"rb1": 20, "wr1": 15}, _POS, _SLOTS)
    assert "qb" not in " ".join(chosen)
    assert set(chosen) == {"rb1", "wr1"}


def test_the_lineup_that_scores_a_blind_pick_uses_projected_ranks() -> None:
    # The FLEX decision is between te1 and wr2. The projection prefers wr2, but te1 actually
    # erupts — the blind pick eats that miss; the hindsight-optimal lineup does not.
    projected = {"qb1": 25, "rb1": 20, "wr1": 15, "te1": 5, "wr2": 12}
    actual = {"qb1": 25, "rb1": 20, "wr1": 15, "te1": 40, "wr2": 12}
    picked = arena.select_lineup(projected, _POS, _SLOTS)
    engine_pts = sum(actual[p] for p in picked)
    optimal = arena.select_lineup(actual, _POS, _SLOTS)
    optimal_pts = sum(actual[p] for p in optimal)
    assert "te1" not in picked  # projection benched the player who erupted
    assert engine_pts == 72.0 and optimal_pts == 100.0
    assert engine_pts < optimal_pts


def test_point_history_average_and_games() -> None:
    h = arena.PointHistory({"a": [10.0, 20.0], "b": []})
    assert h.average("a") == 15.0
    assert h.average("b") is None
    assert h.average("missing") is None
    assert h.games("a") == 2 and h.games("missing") == 0


def test_season_average_projector_is_leak_free_and_covers_all_positions() -> None:
    hist = arena.PointHistory({"rb1": [10.0, 14.0], "k1": [8.0]})
    proj = arena.season_average_projector(5, ["rb1", "k1", "new"], {"rb1": "RB", "k1": "K"}, hist)
    assert proj["rb1"] == 12.0
    assert proj["k1"] == 8.0
    assert proj["new"] == 0.0  # no prior game — the blind spot a manager also had


def test_recency_projector_weights_recent_games() -> None:
    hist = arena.PointHistory({"wr1": [2.0, 2.0, 2.0, 2.0, 30.0]})  # cold then hot
    season_avg = arena.season_average_projector(6, ["wr1"], {"wr1": "WR"}, hist)
    last4 = arena.recency_projector(6, ["wr1"], {"wr1": "WR"}, hist)
    assert last4["wr1"] > season_avg["wr1"]  # recency catches the breakout


def test_replay_week_scores_three_ways_without_leakage() -> None:
    roster = {
        "roster_id": 3,
        "players": ["qb1", "rb1", "rb2", "wr1", "bench1"],
        "starters": ["qb1", "rb1", "wr1", "rb2"],  # what the "manager" did
        "players_points": {"qb1": 25, "rb1": 30, "rb2": 5, "wr1": 15, "bench1": 40},
    }

    # A projector that would (wrongly) bench the high-scorer, proving actuals aren't leaking in.
    def blind(_w, avail, _pos, _h):
        return {"qb1": 25, "rb1": 10, "rb2": 20, "wr1": 15, "bench1": 1}

    pos = {**_POS, "bench1": "RB"}
    score = arena._replay_week(5, roster, pos, _SLOTS, arena.PointHistory(), blind)
    assert score is not None
    # optimal uses actuals: qb1(25)+rb1(30)+wr1(15)+bench1-as-flex(40) = 110
    assert score.optimal_pts == 110.0
    # engine picked by projection (bench1 projected 1, so it's benched) → misses the 40.
    assert score.engine_pts < score.optimal_pts
    # actual = the manager's starters scored on actuals: 25+30+15+5 = 75
    assert score.actual_pts == 75.0


def test_replay_week_skips_a_roster_with_no_points() -> None:
    roster = {"roster_id": 1, "players": ["a"], "starters": ["a"], "players_points": {}}
    assert (
        arena._replay_week(5, roster, {"a": "RB"}, _SLOTS, arena.PointHistory(), lambda *a: {})
        is None
    )


def test_extend_history_accumulates_across_weeks() -> None:
    hist = arena.PointHistory()
    arena._extend_history(hist, [{"players_points": {"a": 10.0}}, {"players_points": {"a": 12.0}}])
    arena._extend_history(hist, [{"players_points": {"a": 8.0}}])
    assert hist.by_player["a"] == [10.0, 12.0, 8.0]


def test_engine_beat_actual_flag() -> None:
    assert arena.WeekScore(5, 1, 100.0, 90.0, 120.0).engine_beat_actual
    assert not arena.WeekScore(5, 1, 80.0, 90.0, 120.0).engine_beat_actual


def test_aggregate_computes_capture_and_beat_rate() -> None:
    scores = [
        arena.WeekScore(4, 1, 100.0, 90.0, 120.0),  # engine beats human
        arena.WeekScore(4, 2, 80.0, 110.0, 130.0),  # engine loses
    ]
    result = arena._aggregate(2024, "L", "p", scores, (4,))
    assert result.n_roster_weeks == 2
    assert result.engine_beats_actual_rate == 0.5
    assert result.engine_mean == 90.0 and result.actual_mean == 100.0
    assert result.engine_vs_actual_margin == -10.0
    assert result.engine_capture == round(90.0 / 125.0, 4)


# --- availability levers (A: injury gating, B: DNP discount) -------------------------


def test_availability_out_and_doubtful_are_zeroed() -> None:
    for status in ("Out", "Doubtful"):
        m = arena._availability_multiplier(
            "g1", 5, {"g1": status}, {"BUF": {1, 2, 3, 4}}, {"g1": "BUF"}, {"g1": {1, 2, 3, 4}}
        )
        assert m == 0.0


def test_availability_questionable_is_shaded_not_cut() -> None:
    m = arena._availability_multiplier(
        "g1", 5, {"g1": "Questionable"}, {"BUF": {1, 2, 3, 4}}, {"g1": "BUF"}, {"g1": {1, 2, 3, 4}}
    )
    assert m == arena._QUESTIONABLE_FACTOR


def test_availability_healthy_active_player_is_untouched() -> None:
    m = arena._availability_multiplier(
        "g1", 5, {}, {"BUF": {1, 2, 3, 4}}, {"g1": "BUF"}, {"g1": {1, 2, 3, 4}}
    )
    assert m == 1.0


def test_dnp_discount_when_player_missed_teams_last_game() -> None:
    # Team played weeks 1-4; player has box scores only through week 3 → missed week 4.
    m = arena._availability_multiplier(
        "g1", 5, {}, {"BUF": {1, 2, 3, 4}}, {"g1": "BUF"}, {"g1": {1, 2, 3}}
    )
    assert m == arena._DNP_FACTOR


def test_dnp_and_questionable_compound() -> None:
    m = arena._availability_multiplier(
        "g1", 5, {"g1": "Questionable"}, {"BUF": {1, 2, 3, 4}}, {"g1": "BUF"}, {"g1": {1, 2, 3}}
    )
    assert m == arena._QUESTIONABLE_FACTOR * arena._DNP_FACTOR


def test_no_dnp_penalty_before_a_team_has_played() -> None:
    # Week 1: no prior team games, so absence can't be judged — no penalty.
    m = arena._availability_multiplier("g1", 1, {}, {"BUF": {1}}, {"g1": "BUF"}, {"g1": set()})
    assert m == 1.0


def test_injury_calendar_only_reads_the_projected_week(monkeypatch) -> None:
    """Leakage guard: the multiplier is keyed by week, so a future Out can't leak back."""
    injuries = {5: {"g1": "Out"}, 6: {"g1": "Questionable"}}  # g1 is Out in wk5, Q in wk6
    # Projecting week 6 must see the wk6 status, never wk5's.
    week6 = injuries.get(6, {})
    m = arena._availability_multiplier(
        "g1", 6, week6, {"BUF": {1, 2, 3, 4, 5}}, {"g1": "BUF"}, {"g1": {1, 2, 3, 4, 5}}
    )
    assert m == arena._QUESTIONABLE_FACTOR  # wk6 designation, not wk5's Out


def test_weeks_played_by_team_inverts_the_schedule() -> None:
    import polars as pl

    def fake_load(_seasons):
        return pl.DataFrame(
            {
                "season": [2024, 2024, 2024],
                "game_type": ["REG", "REG", "REG"],
                "week": [1, 1, 2],
                "home_team": ["BUF", "KC", "BUF"],
                "away_team": ["NYJ", "LAC", "MIA"],
            }
        )

    out = arena._weeks_played_by_team(fake_load, 2024)
    assert out["BUF"] == {1, 2}
    assert out["NYJ"] == {1}
    assert out["MIA"] == {2}


# --- head-to-head counterfactual ----------------------------------------------------


def test_score_h2h_week_pairs_opponent_by_matchup_id() -> None:
    matchups = [
        {
            "roster_id": 2,
            "matchup_id": 1,
            "points": 100.0,
            "players": ["qb1", "rb1", "wr1", "rb2"],
            "starters": ["qb1", "rb1", "wr1", "rb2"],
            "players_points": {"qb1": 25, "rb1": 30, "wr1": 15, "rb2": 20},
        },
        {"roster_id": 5, "matchup_id": 1, "points": 88.0, "players": [], "players_points": {}},
        {"roster_id": 7, "matchup_id": 2, "points": 120.0, "players": [], "players_points": {}},
    ]
    out = arena._score_h2h_week(
        6,
        matchups,
        2,
        _POS,
        _SLOTS,
        arena.PointHistory(),
        lambda *a: {"qb1": 25, "rb1": 30, "wr1": 15, "rb2": 20},
    )
    assert out is not None
    _engine_pts, _actual_pts, opp_pts, others = out
    assert opp_pts == 88.0  # roster 5 shares matchup_id 1
    assert sorted(others) == [88.0, 120.0]  # every other roster's actual points


def test_score_h2h_week_returns_none_when_roster_absent() -> None:
    matchups = [
        {"roster_id": 9, "matchup_id": 1, "points": 50.0, "players": [], "players_points": {}}
    ]
    assert (
        arena._score_h2h_week(6, matchups, 2, _POS, _SLOTS, arena.PointHistory(), lambda *a: {})
        is None
    )


def _h2h(roster_id: int, margin: float, e_ap: int, a_ap: int) -> arena.H2HResult:
    return arena.H2HResult(
        season=2024,
        league_id="L",
        roster_id=roster_id,
        projector="engine",
        n_weeks=11,
        engine_wins=0,
        engine_losses=0,
        actual_wins=0,
        actual_losses=0,
        engine_points_for=0.0,
        actual_points_for=0.0,
        engine_allplay_wins=e_ap,
        actual_allplay_wins=a_ap,
        allplay_games=99,
        points_margin=margin,
        points_margin_ci=(0.0, 0.0),
        outscore_pvalue=1.0,
    )


def test_league_h2h_counts_rosters_the_engine_beats() -> None:
    result = arena.LeagueH2HResult(
        season=2024,
        league_id="L",
        projector="engine",
        per_roster=[_h2h(1, 5.0, 60, 50), _h2h(2, -3.0, 40, 55), _h2h(3, 1.0, 50, 50)],
    )
    assert result.rosters_outscored == 2  # rosters 1 and 3 have positive margin
    assert result.rosters_out_allplayed == 1  # only roster 1 has more all-play wins
