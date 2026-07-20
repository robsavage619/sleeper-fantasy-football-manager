from __future__ import annotations

import pytest

from sleeper_ffm.model import projections as pr
from sleeper_ffm.sleeper.graphql import SleeperGraphQLClient, SleeperGraphQLError

_SCORING = {"rush_yd": 0.1, "rush_td": 6.0, "rec": 1.0, "rec_yd": 0.1, "bonus_rush_yd_100": 3.0}


def _row(player_id: str, position: str = "RB", **stats: float) -> dict:
    return {
        "player_id": player_id,
        "team": "BAL",
        "opponent": "BUF",
        "player": {"first_name": "Test", "last_name": "Back", "position": position},
        "stats": stats,
    }


def test_scores_under_league_settings_not_provider_points() -> None:
    row = _row("1", rush_yd=80.0, rush_td=1.0, rec=4.0, rec_yd=30.0, pts_ppr=99.0)
    out = pr._to_projection(row, _SCORING)
    assert out is not None
    # 80*0.1 + 6 + 4 + 30*0.1 = 21.0, not the provider's 99.
    assert out.league_points == 21.0
    assert out.provider_points == 99.0
    assert out.points_delta == -78.0


def test_non_skill_and_empty_rows_are_skipped() -> None:
    assert pr._to_projection(_row("1", position="K", rush_yd=10.0), _SCORING) is None
    assert pr._to_projection(_row("2"), _SCORING) is None  # no stats
    assert pr._to_projection({"player_id": "3", "stats": {"rec": 1.0}}, _SCORING) is None


def test_opportunity_counts_carries_plus_targets() -> None:
    out = pr._to_projection(_row("1", rush_att=12.0, rec_tgt=5.0, rec=4.0), _SCORING)
    assert out is not None
    assert out.opportunity == 17.0


def test_threshold_bonus_underfires_on_expected_value() -> None:
    """A projected 95.4 rush yards scores no 100-yd bonus — documented, not a bug."""
    under = pr._to_projection(_row("1", rush_yd=95.4), _SCORING)
    over = pr._to_projection(_row("2", rush_yd=101.0), _SCORING)
    assert under is not None and over is not None
    assert under.league_points == 9.54
    assert over.league_points == 13.1  # 10.1 + the 3.0 bonus


def test_opportunity_shares_sum_to_one_per_team() -> None:
    projections = {
        "1": pr.PlayerProjection("1", "A", "RB", "BAL", "BUF", 0.0, 0.0, {"rush_att": 15.0}),
        "2": pr.PlayerProjection("2", "B", "WR", "BAL", "BUF", 0.0, 0.0, {"rec_tgt": 5.0}),
        "3": pr.PlayerProjection("3", "C", "WR", "KC", "LAC", 0.0, 0.0, {"rec_tgt": 8.0}),
    }
    shares = pr.opportunity_shares(projections)
    assert shares["1"] == 0.75
    assert shares["2"] == 0.25
    assert shares["3"] == 1.0


def test_opportunity_shares_omits_teams_with_no_projected_touches() -> None:
    projections = {
        "1": pr.PlayerProjection("1", "A", "RB", "BAL", "BUF", 0.0, 0.0, {}),
    }
    assert pr.opportunity_shares(projections) == {}


def test_empty_feed_raises_rather_than_returning_no_projections(monkeypatch) -> None:
    """An empty mapping is indistinguishable from 'everyone projects zero' downstream."""
    monkeypatch.setattr(pr.SleeperGraphQLClient, "weekly_stats", lambda *a, **k: [])
    monkeypatch.setattr(pr, "load_scoring", lambda: _SCORING)
    pr.week_projections.cache_clear()
    with pytest.raises(pr.ProjectionsUnavailableError):
        pr.week_projections("2026", 1)
    pr.week_projections.cache_clear()


def test_graphql_errors_array_raises(monkeypatch) -> None:
    client = SleeperGraphQLClient()
    monkeypatch.setattr(client, "_http", _FakeHTTP({"errors": [{"message": "Cannot query field"}]}))
    with pytest.raises(SleeperGraphQLError, match="Cannot query field"):
        client.weekly_stats(season="2026", week=1)


def test_graphql_unwraps_single_object_field(monkeypatch) -> None:
    client = SleeperGraphQLClient()
    payload = {"data": {"get_player_outlook": {"metadata": {"description": "  outlook  "}}}}
    monkeypatch.setattr(client, "_http", _FakeHTTP(payload))
    assert client.player_outlook("4881", "2026") == "outlook"


def test_graphql_news_sorted_newest_first(monkeypatch) -> None:
    client = SleeperGraphQLClient()
    payload = {
        "data": {
            "get_player_news": [
                {"published": 100, "metadata": {"description": "older"}},
                {"published": 300, "metadata": {"description": "newer"}},
                {"published": 200, "metadata": {}},  # no text — dropped
            ]
        }
    }
    monkeypatch.setattr(client, "_http", _FakeHTTP(payload))
    assert client.player_news("4881") == ["newer", "older"]


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeHTTP:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def post(self, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse(self._payload)
