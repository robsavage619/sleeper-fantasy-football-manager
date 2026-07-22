"""`sffm eval` — deterministic scenario suites + tier-3 prompt grading."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from sleeper_ffm.evals.harness import run_suite
from sleeper_ffm.evals.scenarios import RUNS_DIR

eval_app = typer.Typer(help="Engine calibration + prompt fine-tuning eval harness.")


@eval_app.command("arena")
def arena_cmd(
    season: int = typer.Argument(..., help="Completed season to replay (2020-2025)."),
    projector: str = typer.Option("engine", "--projector", help="engine | season_avg | recency"),
    h2h: bool = typer.Option(False, "--h2h", help="Head-to-head: would the engine have won more?"),
    roster_id: int | None = typer.Option(
        None, "--roster", help="H2H target roster (default: mine)."
    ),
    league: bool = typer.Option(False, "--league", help="H2H for every roster in the league."),
    ledger: bool = typer.Option(False, "--ledger", help="Append the result to the arena ledger."),
) -> None:
    """Replay a season's start/sit decisions blind and report engine vs managers vs optimal."""
    from sleeper_ffm.evals.arena import (
        ArenaUnavailableError,
        append_arena_ledger,
        make_engine_projector,
        recency_projector,
        run_arena,
        run_h2h,
        run_league_h2h,
        season_average_projector,
    )

    try:
        if league:
            result = run_league_h2h(season)
            typer.echo(result.summary())
            for r in sorted(result.per_roster, key=lambda x: -x.points_margin):
                typer.echo(f"  {r.summary()}")
            return
        if h2h:
            typer.echo(run_h2h(season, roster_id=roster_id).summary())
            return
    except ArenaUnavailableError as exc:
        typer.echo(f"arena unavailable: {exc}")
        raise typer.Exit(1) from exc

    builders = {
        "engine": lambda: (make_engine_projector(season), "engine_forecast+avail+vegas"),
        "season_avg": lambda: (season_average_projector, "season_avg"),
        "recency": lambda: (recency_projector, "recency_L4"),
    }
    if projector not in builders:
        typer.echo(f"unknown projector '{projector}' (choose: {', '.join(builders)})")
        raise typer.Exit(1)

    proj, name = builders[projector]()
    try:
        result = run_arena(season, proj, name)
    except ArenaUnavailableError as exc:
        typer.echo(f"arena unavailable: {exc}")
        raise typer.Exit(1) from exc

    typer.echo(result.summary())
    typer.echo(
        f"  engine {result.engine_mean:.1f}  |  managers {result.actual_mean:.1f}  |  "
        f"optimal {result.optimal_mean:.1f} pts/wk  ({result.n_roster_weeks} roster-weeks)"
    )
    if ledger:
        path = append_arena_ledger(result)
        typer.echo(f"  logged to {path}")


@eval_app.command("gap")
def gap_cmd(
    seasons: list[int] = typer.Argument(
        ..., help="Completed seasons to decompose (e.g. 2022 2023 2024)."
    ),
    projector: str = typer.Option("engine", "--projector", help="engine | season_avg | recency"),
) -> None:
    """Bucket every point of capture loss vs optimal: engine vs managers, side by side."""
    from sleeper_ffm.evals.arena import (
        ArenaUnavailableError,
        make_engine_projector,
        recency_projector,
        season_average_projector,
    )
    from sleeper_ffm.evals.gap_report import merge_gap_reports, run_gap_report

    builders = {
        "engine": lambda s: (make_engine_projector(s), "engine_forecast+avail+vegas"),
        "season_avg": lambda s: (season_average_projector, "season_avg"),
        "recency": lambda s: (recency_projector, "recency_L4"),
    }
    if projector not in builders:
        typer.echo(f"unknown projector '{projector}' (choose: {', '.join(builders)})")
        raise typer.Exit(1)

    reports = []
    for season in seasons:
        proj, name = builders[projector](season)
        try:
            report = run_gap_report(season, proj, name)
        except ArenaUnavailableError as exc:
            typer.echo(f"gap report unavailable for {season}: {exc}")
            raise typer.Exit(1) from exc
        typer.echo(report.table())
        reports.append(report)
    if len(reports) > 1:
        typer.echo(merge_gap_reports(reports).table())


@eval_app.command("avail-sweep")
def avail_sweep_cmd(
    seasons: list[int] = typer.Argument(..., help="Seasons to pool (fit set, e.g. 2022 2023)."),
    q: str = typer.Option("0.5,0.65,0.8,0.9,1.0", "--q", help="Questionable factors to sweep."),
    dnp: str = typer.Option("0.1,0.2,0.3,0.45,0.6", "--dnp", help="DNP factors to sweep."),
) -> None:
    """Sweep the availability shade constants (Levers A/B) against the arena."""
    from sleeper_ffm.evals.arena import ArenaUnavailableError
    from sleeper_ffm.evals.avail_sweep import run_avail_sweep

    q_factors = tuple(float(x) for x in q.split(","))
    dnp_factors = tuple(float(x) for x in dnp.split(","))
    try:
        cells = run_avail_sweep(tuple(seasons), q_factors, dnp_factors)
    except ArenaUnavailableError as exc:
        typer.echo(f"sweep unavailable: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(f"seasons {seasons}: {cells[0].n_roster_weeks} roster-weeks per cell")
    for cell in cells:
        typer.echo(f"  {cell.row()}")


@eval_app.command("winprob")
def winprob_cmd(
    seasons: list[int] = typer.Argument(..., help="Seasons to replay (e.g. 2022 2023 2024)."),
) -> None:
    """Win-prob selector vs mean selector: does risk-adjusting lineups win more matchups?"""
    from sleeper_ffm.evals.arena import ArenaUnavailableError
    from sleeper_ffm.evals.winprob import run_winprob_league

    for season in seasons:
        try:
            typer.echo(run_winprob_league(season).summary())
        except ArenaUnavailableError as exc:
            typer.echo(f"winprob unavailable for {season}: {exc}")
            raise typer.Exit(1) from exc


@eval_app.command("waivers")
def waivers_cmd(
    season: int = typer.Argument(..., help="Completed season to replay."),
    horizon: int = typer.Option(4, "--horizon", help="Weeks of realized value per pickup."),
    top_k: int = typer.Option(3, "--top-k", help="Top-ranked adds the engine 'makes' weekly."),
) -> None:
    """Blind waiver-wire replay: how well does the engine rank the week's pickups?"""
    from sleeper_ffm.evals.arena import ArenaUnavailableError
    from sleeper_ffm.evals.waiver_arena import run_waiver_arena

    try:
        typer.echo(run_waiver_arena(season, horizon=horizon, top_k=top_k).summary())
    except ArenaUnavailableError as exc:
        typer.echo(f"waiver arena unavailable: {exc}")
        raise typer.Exit(1) from exc


@eval_app.command("trades")
def trades_cmd(
    seasons: list[int] = typer.Argument(
        ..., help="Completed seasons to pool (e.g. 2022 2023 2024)."
    ),
) -> None:
    """Trade retrospective: did the engine prefer the more-productive side (win-now lens)?"""
    from sleeper_ffm.evals.arena import ArenaUnavailableError
    from sleeper_ffm.evals.trade_retro import run_trade_retro

    try:
        result = run_trade_retro(tuple(seasons))
    except ArenaUnavailableError as exc:
        typer.echo(f"trade retro unavailable: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(result.summary())


@eval_app.command("run")
def run_cmd(
    split: str = typer.Option("train", "--split", help="train | holdout"),
    tier: int = typer.Option(1, "--tier", help="Scenario tier to run."),
    scenario_id: str | None = typer.Option(None, "--id", help="Run a single scenario by id."),
    change_kind: str = typer.Option(
        "engine", "--change-kind", help="engine | scenario | prompt | baseline"
    ),
    change_note: str = typer.Option("", "--change-note", help="Ledger note for this run."),
) -> None:
    """Run tier-1 scenarios and write graded results + a ledger entry."""
    result = run_suite(
        split=split,
        tier=tier,
        scenario_id=scenario_id,
        change_kind=change_kind,
        change_note=change_note,
    )
    typer.echo(f"run {result['run_id']}: {result['passed']}/{result['scenarios_run']} passed")
    for r in result["results"]:
        if not r.passed:
            typer.echo(f"  FAIL {r.scenario_id} ({r.engine}){f': {r.error}' if r.error else ''}")
            for check in r.checks:
                if not check["passed"]:
                    typer.echo(
                        f"    - {check['type']} {check['target']}: "
                        f"expected {check['expected']}, got {check['actual']}"
                    )


@eval_app.command("report")
def report_cmd(
    last: int = typer.Option(10, "--last", help="How many ledger entries to show."),
) -> None:
    """Show the pass-rate trajectory from the ledger."""
    ledger_path = RUNS_DIR / "ledger.jsonl"
    if not ledger_path.exists():
        typer.echo("No runs yet.")
        return
    lines = ledger_path.read_text().strip().splitlines()
    for line in lines[-last:]:
        entry = json.loads(line)
        typer.echo(
            f"{entry['timestamp']} [{entry['git_sha'][:8]}] {entry['split']} "
            f"tier={entry['tier']} {entry['passed']}/{entry['scenarios_run']} passed "
            f"({entry['change_kind']}: {entry['change_note']})"
        )


@eval_app.command("render-briefing")
def render_briefing_cmd(fixture: str = typer.Argument(help="Tier-3 fixture name.")) -> None:
    """Print the rendered tier-3 briefing for a fixture."""
    from sleeper_ffm.evals.briefings import render_briefing

    typer.echo(render_briefing(fixture))


@eval_app.command("grade-doc")
def grade_doc_cmd(
    fixture: str = typer.Argument(help="Tier-3 fixture name."),
    doc_path: Path = typer.Argument(help="Path to a candidate MasterDocument JSON file."),
) -> None:
    """Scripted-grade a candidate MasterDocument against a fixture's planted facts."""
    from sleeper_ffm.evals.grade_doc import grade_doc

    doc_dict = json.loads(doc_path.read_text())
    result = grade_doc(fixture, doc_dict)
    typer.echo(f"schema_ok={result.schema_ok}")
    if result.taxonomy:
        for code, detail in zip(result.taxonomy, result.details, strict=True):
            typer.echo(f"  {code}: {detail}")
    else:
        typer.echo("  no scripted issues found")
