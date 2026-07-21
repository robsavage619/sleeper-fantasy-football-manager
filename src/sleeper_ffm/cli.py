"""`sffm` CLI entry point."""

from __future__ import annotations

import contextlib
import json
import logging

import typer

from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.evals.cli import eval_app
from sleeper_ffm.nflverse.loader import ingest as nflverse_ingest
from sleeper_ffm.reasoning.findings import load_findings_from_disk, post_finding
from sleeper_ffm.scoring import load_scoring, score
from sleeper_ffm.sleeper import SleeperClient

app = typer.Typer(help="sleeper-ffm — AI dynasty fantasy football GM.", no_args_is_help=True)
app.add_typer(eval_app, name="eval")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def league() -> None:
    """Print verified facts about the configured league (live from Sleeper)."""
    with SleeperClient() as client:
        lg = client.league()
        picks = client.traded_picks()
    typer.echo(f"{lg.name} — {lg.season} — {lg.status} — {lg.total_rosters} teams")
    typer.echo(f"type={lg.settings.get('type')} scoring={lg.scoring_settings.get('rec')} PPR")
    typer.echo(f"previous_league_id={lg.previous_league_id}")
    seasons = sorted({p.season for p in picks})
    typer.echo(f"traded picks: {len(picks)} across seasons {seasons}")


@app.command()
def history() -> None:
    """Show the dynasty season chain (walks previous_league_id)."""
    with SleeperClient() as client:
        for lg in client.league_history():
            typer.echo(f"{lg.season}: {lg.league_id} ({lg.name})")


@app.command("score-line")
def score_line(
    rec: float = typer.Option(0, help="receptions"),
    rec_yd: float = typer.Option(0, help="receiving yards"),
    rec_td: float = typer.Option(0, help="receiving TDs"),
    rush_yd: float = typer.Option(0, help="rushing yards"),
    rush_td: float = typer.Option(0, help="rushing TDs"),
    pass_yd: float = typer.Option(0, help="passing yards"),
    pass_td: float = typer.Option(0, help="passing TDs"),
) -> None:
    """Score a hand-entered stat line under the league's rules (sanity check)."""
    stats = {
        "rec": rec,
        "rec_yd": rec_yd,
        "rec_td": rec_td,
        "rush_yd": rush_yd,
        "rush_td": rush_td,
        "pass_yd": pass_yd,
        "pass_td": pass_td,
    }
    typer.echo(f"{score(stats, load_scoring())} pts")


@app.command()
def ingest(
    full: bool = typer.Option(False, "--full", help="Pull all historical seasons (2014-2025)."),
    season: int | None = typer.Option(None, "--season", help="Pull a single specific season."),
    force: bool = typer.Option(False, "--force", help="Re-fetch even if cached."),
    skip_snaps: bool = typer.Option(False, "--skip-snaps", help="Skip snap-count download."),
    skip_rosters: bool = typer.Option(False, "--skip-rosters", help="Skip roster snapshots."),
    skip_status: bool = typer.Option(
        False, "--skip-status", help="Skip injury / depth-chart / play-by-play feeds."
    ),
) -> None:
    """Ingest nflverse NFL stats to parquet cache.

    Default: incremental (current season only). Use --full for first-time backfill.
    Injuries, depth charts, and play-by-play are pulled too (--skip-status to omit).
    """
    from sleeper_ffm.nflverse.loader import _CURRENT_SEASON, _FIRST_SEASON

    if season:
        seasons = [season]
    elif full:
        seasons = list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    else:
        seasons = [_CURRENT_SEASON]

    typer.echo(f"Ingesting seasons: {seasons}")
    nflverse_ingest(
        seasons=seasons,
        force=force,
        skip_snaps=skip_snaps,
        skip_rosters=skip_rosters,
        skip_status=skip_status,
    )
    typer.echo("Done.")


@app.command("draft")
def draft_board(
    top: int = typer.Option(30, "--top", help="How many available players to show in the prompt."),
    prompt_only: bool = typer.Option(False, "--prompt-only", help="Just print the Claude prompt."),
    season: int = typer.Option(
        DEFAULT_VALUE_SEASON, "--season", help="Season to use for player FPAR."
    ),
) -> None:
    """Show the live draft board and generate a Claude Code prompt for the next pick.

    Syncs the draft live from Sleeper, scores available players via nflverse FPAR,
    and prints either a quick board summary or a full prompt for Claude Code.
    """
    from sleeper_ffm.draft.assistant import build_pick_prompt, sync_board

    typer.echo("Syncing board from Sleeper...", err=True)
    board = sync_board()

    if board.is_complete():
        typer.echo("Draft is complete.", err=True)
        raise typer.Exit(0)

    typer.echo(
        f"Pick {board.current_pick_no}/{board.total_picks} "
        f"(Round {board.current_round}) — "
        f"{board.picks_until_my_turn} picks until my turn (slot {board.my_slot})",
        err=True,
    )

    typer.echo("Building draft pool (veterans + rookies)...", err=True)
    from sleeper_ffm.draft.assistant import build_full_pool

    pool = build_full_pool(board, seasons=[season])

    if prompt_only:
        prompt = build_pick_prompt(board, pool, top_n=top)
        typer.echo(prompt)
    else:
        typer.echo(f"\nTop {min(top, len(pool))} available (dynasty FPAR):")
        for i, p in enumerate(pool[:top], 1):
            rookie = " [rookie]" if p.is_taxi else ""
            typer.echo(
                f"  {i:2}. {p.name:26s} {p.position:3s}  "
                f"age {p.age:4.1f}  FPAR {p.current_fpar:6.1f}  {p.team}{rookie}"
            )
        typer.echo("\nRun with --prompt-only to generate the Claude Code reasoning prompt.")


@app.command("trade")
def trade_prompt(
    give: str = typer.Option(..., "--give", help="Comma-separated Sleeper player IDs to give"),
    get: str = typer.Option(..., "--get", help="Comma-separated Sleeper player IDs to receive"),
    give_picks: str = typer.Option("", "--give-picks", help="Pick IDs to give (YEAR_ROUND_SLOT)"),
    get_picks: str = typer.Option("", "--get-picks", help="Comma-separated pick IDs to receive"),
    season: int = typer.Option(
        DEFAULT_VALUE_SEASON, "--season", help="Season to use for player FPAR"
    ),
) -> None:
    """Build a Claude Code prompt for evaluating a dynasty trade offer.

    Prints the structured prompt to stdout; paste into Claude Code for reasoning.
    """
    from sleeper_ffm.prompts.trade import build_trade_prompt

    give_ids = [x.strip() for x in give.split(",") if x.strip()]
    get_ids = [x.strip() for x in get.split(",") if x.strip()]
    give_pick_ids = [x.strip() for x in give_picks.split(",") if x.strip()]
    get_pick_ids = [x.strip() for x in get_picks.split(",") if x.strip()]

    typer.echo("Building trade analysis prompt...", err=True)
    prompt = build_trade_prompt(
        give_player_ids=give_ids,
        get_player_ids=get_ids,
        give_pick_ids=give_pick_ids,
        get_pick_ids=get_pick_ids,
        seasons=[season],
    )
    typer.echo(prompt)


@app.command("startsit")
def startsit_cmd(
    week: int = typer.Option(0, "--week", help="NFL week (0 = current week from Sleeper state)."),
    season: int = typer.Option(DEFAULT_VALUE_SEASON, "--season", help="NFL season year."),
) -> None:
    """Optimal start/sit lineup for the week.

    Projects each roster player's expected points, solves the optimal lineup,
    and prints recommended changes plus a Claude Code reasoning prompt.
    """
    from rich.console import Console
    from rich.table import Table

    from sleeper_ffm.season.startsit import build_startsit
    from sleeper_ffm.sleeper.client import SleeperClient

    resolved_week = week
    resolved_season = season
    if resolved_week == 0:
        typer.echo("Fetching current week from Sleeper...", err=True)
        with SleeperClient() as c:
            state = c.state_nfl()
        resolved_week = state.week or 1
        if state.season:
            with contextlib.suppress(ValueError):
                resolved_season = int(state.season)

    typer.echo(f"Building start/sit for week {resolved_week} {resolved_season}...", err=True)
    rec = build_startsit(week=resolved_week, season=resolved_season)

    console = Console()

    if not rec.changes:
        console.print(
            f"[green]LINEUP · OPTIMAL[/green] — no changes needed  "
            f"(projected {rec.total_projected_pts:.1f} pts)"
        )
    else:
        table = Table(
            title=f"START/SIT — WEEK {resolved_week} {resolved_season}",
            show_lines=False,
        )
        table.add_column("START", style="green", min_width=22)
        table.add_column("SIT", style="dim", min_width=22)
        table.add_column("GAIN", justify="right", style="bold")

        proj_by_id = {p.player_id: p for p in rec.projected_starters + rec.current_starters}
        for c in rec.changes:
            start_p = proj_by_id.get(c["start"])
            sit_p = proj_by_id.get(c["sit"])
            start_name = start_p.name if start_p else c["start"]
            sit_name = sit_p.name if sit_p else c["sit"]
            gain = c["gain"]
            table.add_row(start_name, sit_name, f"+{gain:.1f}")

        console.print(table)
        console.print(
            f"\nOptimal: [bold]{rec.total_projected_pts:.1f} pts[/bold]  "
            f"Current: {rec.current_projected_pts:.1f} pts  "
            f"Gain: [green]+{rec.total_projected_pts - rec.current_projected_pts:.1f}[/green]"
        )

    typer.echo("\n--- CLAUDE CODE PROMPT ---\n")
    typer.echo(rec.prompt)


@app.command("finding")
def finding_post(
    kind: str = typer.Argument(help="Finding type: draft|waiver|trade|startsit|pick_arb"),
    body: str = typer.Option(..., "--body", help="JSON body string"),
) -> None:
    """Post a Claude Code finding to the store (called by Claude after reasoning)."""
    try:
        body_dict = json.loads(body)
    except json.JSONDecodeError as exc:
        typer.echo(f"ERROR: invalid JSON body: {exc}", err=True)
        raise typer.Exit(1) from exc
    load_findings_from_disk()
    f = post_finding(kind=kind, body=body_dict)
    typer.echo(f"posted: {f.finding_id}")


@app.command("roster")
def roster_overview(
    season: int = typer.Option(
        DEFAULT_VALUE_SEASON, "--season", help="Season for context (unused in profiles)."
    ),
) -> None:
    """League-wide owner behavioral profiles — roster composition and archetypes."""
    from rich.console import Console
    from rich.table import Table

    from sleeper_ffm.model.owner_profile import build_owner_profiles

    profiles = build_owner_profiles()
    console = Console()
    table = Table(title="Owner Profiles", show_lines=False)
    table.add_column("Name", style="bold", min_width=16)
    table.add_column("Players", justify="right")
    table.add_column("QB", justify="right")
    table.add_column("RB", justify="right")
    table.add_column("WR", justify="right")
    table.add_column("TE", justify="right")
    table.add_column("Picks", justify="right")
    table.add_column("Archetype", style="cyan")

    for p in profiles:
        pos = p.positions
        table.add_row(
            p.display_name[:20],
            str(p.player_count),
            str(pos.get("QB", 0)),
            str(pos.get("RB", 0)),
            str(pos.get("WR", 0)),
            str(pos.get("TE", 0)),
            str(p.picks_owned),
            p.archetype,
        )
    console.print(table)


@app.command("trends")
def trends_cmd(
    top: int = typer.Option(20, "--top", help="Number of signals to show."),
    direction: str = typer.Option("all", "--direction", help="rising | falling | all"),
    season: int = typer.Option(DEFAULT_VALUE_SEASON, "--season", help="Season to analyze."),
) -> None:
    """Target-share and FPAR trend signals — breakout and decline candidates."""
    from rich.console import Console
    from rich.table import Table

    from sleeper_ffm.model.trends import compute_trends

    signals = compute_trends(seasons=[season])
    direction_upper = direction.upper()
    if direction_upper != "ALL":
        signals = [s for s in signals if s.direction == direction_upper]
    signals = signals[:top]

    console = Console()
    table = Table(title=f"Trend Signals ({season})", show_lines=False)
    table.add_column("Name", min_width=20)
    table.add_column("Pos", justify="center")
    table.add_column("Team", justify="center")
    table.add_column("Direction", justify="center")
    table.add_column("FPAR Δ", justify="right")
    table.add_column("Tgt% Δ", justify="right")

    dir_colors = {"RISING": "green", "FALLING": "red", "FLAT": "yellow"}
    for s in signals:
        color = dir_colors.get(s.direction, "white")
        fpar_str = f"{s.fpar_delta:+.1f}" if s.fpar_delta is not None else "—"
        ts_str = f"{s.target_share_delta:+.3f}" if s.target_share_delta is not None else "—"
        table.add_row(
            s.name[:24],
            s.position,
            s.team or "—",
            f"[{color}]{s.direction}[/{color}]",
            fpar_str,
            ts_str,
        )
    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8001, help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Hot-reload on file changes"),
) -> None:
    """Start the FastAPI development server."""
    import uvicorn

    uvicorn.run(
        "sleeper_ffm.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
