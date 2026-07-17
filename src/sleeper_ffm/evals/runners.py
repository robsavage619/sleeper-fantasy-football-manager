"""Engine adapters — map a scenario's inputs onto the real engine entry points.

Every adapter calls the actual production function (never a reimplementation)
with hand-built, dependency-injected inputs, mirroring the DI patterns already
used in ``tests/test_trade_realism.py`` and ``tests/test_mispricing.py``. Live
fetches (FantasyCalc pick pricing, Sleeper rosters) are patched at the seam the
existing tests already use, never called for real during an eval run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest import mock

import polars as pl

from sleeper_ffm.evals.scenarios import Scenario, _spearman
from sleeper_ffm.model.dynasty import PickAsset, PlayerAsset, value_pick, value_player
from sleeper_ffm.model.faab_market import (
    FaabMarket,
    PositionBidStats,
    predicted_clearing_price,
    recommended_bid,
)
from sleeper_ffm.model.mispricing import build_mispricing
from sleeper_ffm.model.owner_dossier import ContentionWindow, OwnerDossier, PositionRank
from sleeper_ffm.model.owner_history import OwnerHistory
from sleeper_ffm.model.trade_acceptance import TradeAsset, _acceptance_score, _impact
from sleeper_ffm.season.startsit import PlayerProjection, _solve_lineup
from sleeper_ffm.season.waivers import analyze_waivers
from sleeper_ffm.sleeper.models import TrendingPlayer

CaseResults = dict[str, dict[str, Any]]


def _mini_dossier(spec: dict[str, Any]) -> OwnerDossier:
    """Build a minimal ``OwnerDossier`` exposing only the fields the acceptance scorer reads."""
    contention = ContentionWindow(
        score=0.0, label=spec.get("contention_label", "OPEN"), window="", rationale=""
    )
    return OwnerDossier(
        roster_id=spec.get("roster_id", 1),
        user_id=str(spec.get("roster_id", 1)),
        display_name=spec.get("display_name", "Team"),
        avatar=None,
        archetype="",
        archetype_rationale="",
        total_dynasty_value=0.0,
        player_count=0,
        avg_age=0.0,
        avg_starter_age=0.0,
        players=[],
        age_buckets=[],
        value_by_position=[],
        contention=contention,
        picks_owned=[],
        league_size=spec.get("league_size", 10),
        position_ranks=[PositionRank(**pr) for pr in spec.get("position_ranks", [])],
    )


def _mini_history(spec: dict[str, Any] | None) -> OwnerHistory | None:
    if spec is None:
        return None
    return OwnerHistory(
        roster_id=spec.get("roster_id", 1),
        user_id=str(spec.get("roster_id", 1)),
        trade_count=spec.get("trade_count", 0),
        approachability=spec.get("approachability", "DORMANT"),
        behavioral_tags=spec.get("behavioral_tags", []),
    )


def _trade_asset(spec: dict[str, Any]) -> TradeAsset:
    return TradeAsset(**spec)


def _optional_trade_asset(spec: dict[str, Any] | None) -> TradeAsset | None:
    return None if spec is None else TradeAsset(**spec)


def _trade_acceptance(scenario: Scenario) -> CaseResults:
    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        my_dossier = _mini_dossier(case.get("my_dossier", {}))
        partner = _mini_dossier(case.get("partner", {}))
        history = _mini_history(case.get("history"))
        give_asset = _trade_asset(case["give_asset"])
        receive_asset = _trade_asset(case["receive_asset"])
        sweetener = _optional_trade_asset(case.get("sweetener"))
        score, confidence, rationale = _acceptance_score(
            my_dossier, partner, history, give_asset, receive_asset, sweetener
        )
        give_value = give_asset.value + (sweetener.value if sweetener else 0.0)
        results[case_name] = {
            "score": score,
            "confidence": confidence,
            "margin": round(give_value - receive_asset.value, 1),
            "rationale": rationale,
        }
    return results


def _dynasty_value(scenario: Scenario) -> CaseResults:
    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        kind = case["kind"]
        if kind == "player":
            asset = PlayerAsset(**case["player"])
            results[case_name] = {"value": value_player(asset)}
        elif kind == "pick_list":
            values: list[float] = []
            for pick_spec in case["picks"]:
                pick = PickAsset(**pick_spec["pick"])
                market_value = pick_spec.get("market_value")
                class_strength = pick_spec.get("class_strength_for_season", 1.0)
                with (
                    mock.patch(
                        "sleeper_ffm.market.blend.market_pick_value", return_value=market_value
                    ),
                    mock.patch(
                        "sleeper_ffm.model.draft_class.class_strength_for_season",
                        return_value=class_strength,
                    ),
                ):
                    values.append(value_pick(pick))
            if case.get("mode", "sum") == "sum":
                results[case_name] = {"value": round(sum(values), 2)}
            else:
                results[case_name] = {"values": values}
        else:
            raise ValueError(f"unknown dynasty_value case kind: {kind}")
    return results


def _faab(scenario: Scenario) -> CaseResults:
    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        by_position = {
            pos: PositionBidStats(position=pos, **stats)
            for pos, stats in case.get("by_position", {}).items()
        }
        market = FaabMarket(seasons_covered=[], bids=[], by_position=by_position, by_owner={})
        clearing = predicted_clearing_price(case["position"], case["add_priority"], market)
        bid = recommended_bid(
            case["position"], case["add_priority"], market, case["budget_remaining"]
        )
        results[case_name] = {"clearing_price": clearing, "bid": bid}
    return results


def _waivers(scenario: Scenario) -> CaseResults:
    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        trending_adds = [
            TrendingPlayer(player_id=pid, count=c) for pid, c in case["trending_adds"].items()
        ]
        trending_drops = [
            TrendingPlayer(player_id=pid, count=c)
            for pid, c in case.get("trending_drops", {}).items()
        ]
        my_roster_ids = case.get("my_roster_ids")
        candidates = analyze_waivers(
            sleeper_players=case["sleeper_players"],
            trending_adds=trending_adds,
            trending_drops=trending_drops,
            rostered_ids=set(case.get("rostered_ids", [])),
            my_roster_ids=set(my_roster_ids) if my_roster_ids else None,
            faab_budget=case.get("faab_budget", 500),
        )
        results[case_name] = {
            "priorities": [c.add_priority for c in candidates],
            "player_ids": [c.player_id for c in candidates],
            "top_priority": candidates[0].add_priority if candidates else None,
        }
    return results


def _trade_impact(scenario: Scenario) -> CaseResults:
    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        receive_asset = _trade_asset(case["receive_asset"])
        impact, label = _impact(
            receive_asset,
            give_value=case["give_value"],
            receive_value=case["receive_value"],
            my_needs=set(case.get("my_needs", [])),
            timeline_mismatch=case.get("timeline_mismatch", False),
        )
        results[case_name] = {"impact": impact, "label": label}
    return results


def _startsit_solver(scenario: Scenario) -> CaseResults:
    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        projections = [PlayerProjection(**p) for p in case["players"]]
        lineup = _solve_lineup(projections)
        results[case_name] = {
            "starter_ids": [p.player_id for p in lineup],
            "total_pts": round(sum(p.projected_pts for p in lineup), 1),
        }
    return results


_MISPRICING_SCHEMA = {
    "gsis_id": pl.Utf8,
    "season": pl.Int64,
    "position": pl.Utf8,
    "season_fp": pl.Float64,
    "games_played": pl.Float64,
    "name": pl.Utf8,
    "team": pl.Utf8,
    "sleeper_id_str": pl.Utf8,
}


def _mispricing(scenario: Scenario) -> CaseResults:
    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        players = case["players"]
        season = case.get("season", 2025)
        our_rows = [
            {
                "gsis_id": p["sid"],
                "season": season,
                "position": p["position"],
                "season_fp": p["our_fp"],
                "games_played": p.get("games_played", 12.0),
                "name": p.get("name", p["sid"]),
                "team": p.get("team", "FA"),
                "sleeper_id_str": p["sid"],
            }
            for p in players
        ]
        generic_rows = [
            {**row, "season_fp": p["generic_fp"]} for row, p in zip(our_rows, players, strict=True)
        ]
        our_df = pl.DataFrame(our_rows, schema=_MISPRICING_SCHEMA)
        generic_df = pl.DataFrame(generic_rows, schema=_MISPRICING_SCHEMA)
        market = case.get("market", {})

        def _fake_totals(
            *_args: Any,
            _our: pl.DataFrame = our_df,
            _generic: pl.DataFrame = generic_df,
            **kwargs: Any,
        ) -> pl.DataFrame:
            return _generic if "scoring" in kwargs else _our

        with (
            mock.patch(
                "sleeper_ffm.model.mispricing.compute_season_totals", side_effect=_fake_totals
            ),
            mock.patch("sleeper_ffm.model.mispricing.market_anchor", return_value=market),
            mock.patch("sleeper_ffm.model.mispricing._live_player_status", return_value={}),
        ):
            board = build_mispricing(seasons=[season], min_games=case.get("min_games", 6))

        buys = sorted(board.buys, key=lambda e: e.edge_pct, reverse=True)
        sells = sorted(board.sells, key=lambda e: e.edge_pct)
        results[case_name] = {
            "verdict_by_sid": {e.player_id: e.verdict for e in board.entries},
            "top_buy_sid": buys[0].player_id if buys else None,
            "top_sell_sid": sells[0].player_id if sells else None,
        }
    return results


def _redzone_backtest(scenario: Scenario) -> CaseResults:
    """Real out-of-sample backtest: red-zone-opportunity vs yardage expected-TD MAE.

    Unlike the hand-built fixtures above, this reads the on-disk nflverse parquet
    cache (completed seasons are immutable, so the run is deterministic). Missing
    cache degrades to a non-crashing miss (mae 0/0) rather than raising, so the
    suite's "every scenario runs" self-check stays green in a data-less checkout.
    """
    from sleeper_ffm.evals.backtest import BacktestUnavailableError, run_redzone_backtest

    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        try:
            r = run_redzone_backtest(
                train_season=case["train_season"],
                eval_season=case["eval_season"],
                min_yards=case.get("min_yards", 250),
            )
            results[case_name] = {
                "mae_redzone": r.mae_redzone,
                "mae_yardage": r.mae_yardage,
                "improvement_pct": r.improvement_pct,
                "n_players": r.n_players,
            }
        except BacktestUnavailableError as exc:
            results[case_name] = {
                "mae_redzone": 0.0,
                "mae_yardage": 0.0,
                "improvement_pct": 0.0,
                "n_players": 0,
                "unavailable": str(exc),
            }
    return results


def _calibration_rank_corr(scenario: Scenario) -> CaseResults:
    results: CaseResults = {}
    for case_name, case in scenario.inputs["cases"].items():
        model_values: list[float] = []
        market_values: list[float] = []
        for player_spec in case["players"]:
            asset = PlayerAsset(**player_spec["player"])
            model_values.append(value_player(asset))
            market_values.append(player_spec["market_value"])
        results[case_name] = {
            "model_values": model_values,
            "market_values": market_values,
            "rank_corr": round(_spearman(model_values, market_values), 3),
        }
    return results


ADAPTERS: dict[str, Callable[[Scenario], CaseResults]] = {
    "trade_acceptance": _trade_acceptance,
    "dynasty_value": _dynasty_value,
    "faab": _faab,
    "waivers": _waivers,
    "startsit_solver": _startsit_solver,
    "mispricing": _mispricing,
    "calibration_rank_corr": _calibration_rank_corr,
    "trade_impact": _trade_impact,
    "redzone_backtest": _redzone_backtest,
}
