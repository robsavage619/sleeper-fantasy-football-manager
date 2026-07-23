"""Player-season context — the situation a player produced in.

Answers "what changed around this player" for every player-season since 2014:
did he change teams, did his play-caller change, did his quarterback change, and
how much opportunity was sitting vacant on his team when he got there.

The engine has plenty of signal on what a player *did* (usage, efficiency, points)
and none on the circumstance he did it in. This table is that missing half, and the
input to the situation-change studies: when production moves, was it the player or
the situation?

Coach and quarterback continuity are derived from ``schedules.parquet``, which
carries ``home_coach``/``away_coach`` and ``home_qb_id``/``away_qb_id`` per game
back to 2014 — no additional data source required.

Two distinct change flags exist because they answer different questions:
    ``coach_changed`` is player-centric — the play-caller he lines up for is not
    the one he lined up for last year, whether because he moved or the team did.
    ``team_coach_changed`` is team-centric — his current team replaced its coach.
A player who switches to a team with a stable coaching staff has the first flag
set and the second clear.
"""

from __future__ import annotations

import logging

import polars as pl

from sleeper_ffm.config import DATA_DIR
from sleeper_ffm.nflverse.loader import load_id_map, load_schedules, load_weekly

log = logging.getLogger(__name__)

RESEARCH_DIR = DATA_DIR / "research"
CONTEXT_TABLE_PATH = RESEARCH_DIR / "player_season_context.parquet"

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

# Age is measured at Sept 1 of the season — roughly opening weekend, so a player's
# listed age matches the season he is credited with rather than his birthday month.
_SEASON_AGE_MONTH = 9
_SEASON_AGE_DAY = 1

# A player-season needs this many games before its usage shares mean anything.
_MIN_GAMES = 1


def _modal(
    df: pl.DataFrame,
    group_cols: list[str],
    value_col: str,
    alias: str,
) -> pl.DataFrame:
    """Pick the most frequent non-null ``value_col`` per group.

    Ties break on the value itself so the result is deterministic across runs
    (a mid-season coaching change that splits a season 9-8 must not flip between
    ingests).
    """
    counts = (
        df.filter(pl.col(value_col).is_not_null()).group_by([*group_cols, value_col]).len("games")
    )
    ranked = counts.sort(["games", value_col], descending=[True, False])
    return (
        ranked.group_by(group_cols, maintain_order=True)
        .agg(pl.col(value_col).first().alias(alias))
        .select([*group_cols, alias])
    )


def build_team_seasons(seasons: list[int] | None = None) -> pl.DataFrame:
    """Build the head-coach and primary-quarterback record for every team-season.

    Args:
        seasons: Seasons to cover. Defaults to everything in the schedules cache.

    Returns:
        One row per (season, team) with ``head_coach``, ``primary_qb_id``, the
        prior season's values, and ``team_coach_changed`` / ``team_qb_changed``.
    """
    schedules = load_schedules(seasons=seasons)
    if schedules.is_empty():
        log.warning("build_team_seasons: no schedule data available")
        return pl.DataFrame()

    reg = schedules.filter(pl.col("game_type") == "REG")
    sides = pl.concat(
        [
            reg.select(
                "season",
                pl.col("home_team").alias("team"),
                pl.col("home_coach").alias("coach"),
                pl.col("home_qb_id").alias("qb_id"),
            ),
            reg.select(
                "season",
                pl.col("away_team").alias("team"),
                pl.col("away_coach").alias("coach"),
                pl.col("away_qb_id").alias("qb_id"),
            ),
        ]
    )

    base = sides.select("season", "team").unique()
    coaches = _modal(sides, ["season", "team"], "coach", "head_coach")
    qbs = _modal(sides, ["season", "team"], "qb_id", "primary_qb_id")

    team_seasons = base.join(coaches, on=["season", "team"], how="left").join(
        qbs, on=["season", "team"], how="left"
    )

    prior = team_seasons.select(
        (pl.col("season") + 1).alias("season"),
        "team",
        pl.col("head_coach").alias("prior_head_coach"),
        pl.col("primary_qb_id").alias("prior_primary_qb_id"),
    )

    return (
        team_seasons.join(prior, on=["season", "team"], how="left")
        .with_columns(
            team_coach_changed=pl.when(pl.col("prior_head_coach").is_null())
            .then(None)
            .otherwise(pl.col("head_coach") != pl.col("prior_head_coach")),
            team_qb_changed=pl.when(pl.col("prior_primary_qb_id").is_null())
            .then(None)
            .otherwise(pl.col("primary_qb_id") != pl.col("prior_primary_qb_id")),
        )
        .sort(["season", "team"])
    )


def _player_seasons(weekly: pl.DataFrame) -> pl.DataFrame:
    """Collapse weekly regular-season rows into one row per player-season."""
    reg = weekly.filter(
        pl.col("season_type").eq("REG") & pl.col("position").is_in(list(SKILL_POSITIONS))
    )
    if reg.is_empty():
        return pl.DataFrame()

    # A player who is traded mid-season is credited to whichever team he played
    # the most games for; his usage totals still cover the whole season.
    primary_team = _modal(reg, ["player_id", "season"], "recent_team", "team")

    agg = reg.group_by(["player_id", "season"]).agg(
        pl.len().alias("games"),
        pl.col("player_display_name").first().alias("name"),
        pl.col("position").first().alias("position"),
        pl.col("targets").fill_null(0).sum().alias("targets"),
        pl.col("carries").fill_null(0).sum().alias("carries"),
        pl.col("receptions").fill_null(0).sum().alias("receptions"),
        pl.col("target_share").mean().alias("target_share"),
        pl.col("air_yards_share").mean().alias("air_yards_share"),
        pl.col("wopr").mean().alias("wopr"),
    )

    return agg.join(primary_team, on=["player_id", "season"], how="left").filter(
        pl.col("games").ge(_MIN_GAMES)
    )


def _vacated_opportunity(player_seasons: pl.DataFrame) -> pl.DataFrame:
    """Compute the share of each team's prior-season volume that left the roster.

    Uses raw target and carry counts rather than per-game share means, so the
    result is an exact fraction of the team's prior-season volume rather than an
    approximation that drifts with games played.
    """
    by_team = player_seasons.select("player_id", "season", "team", "targets", "carries")

    team_totals = by_team.group_by(["season", "team"]).agg(
        pl.col("targets").sum().alias("team_targets"),
        pl.col("carries").sum().alias("team_carries"),
    )

    # Who was on the team in season s and still on it in s+1?
    stayed = by_team.select(
        "player_id",
        "team",
        (pl.col("season") - 1).alias("season"),
        pl.lit(True).alias("stayed"),
    )

    prior_with_flag = by_team.join(stayed, on=["player_id", "season", "team"], how="left")

    vacated = prior_with_flag.group_by(["season", "team"]).agg(
        pl.col("targets").filter(pl.col("stayed").is_null()).sum().alias("vacated_targets"),
        pl.col("carries").filter(pl.col("stayed").is_null()).sum().alias("vacated_carries"),
    )

    return (
        vacated.join(team_totals, on=["season", "team"], how="left")
        .with_columns(
            vacated_target_share=pl.when(pl.col("team_targets") > 0)
            .then(pl.col("vacated_targets") / pl.col("team_targets"))
            .otherwise(None),
            vacated_carry_share=pl.when(pl.col("team_carries") > 0)
            .then(pl.col("vacated_carries") / pl.col("team_carries"))
            .otherwise(None),
        )
        # Shift forward one season: opportunity vacated after season s is what is
        # available to the roster in season s+1.
        .select(
            (pl.col("season") + 1).alias("season"),
            "team",
            "vacated_target_share",
            "vacated_carry_share",
        )
    )


def _player_bio() -> pl.DataFrame:
    """Birthdate and draft capital per player, keyed by gsis_id."""
    id_map = load_id_map()
    cols = ["gsis_id", "birthdate", "draft_year", "draft_round", "draft_ovr", "sleeper_id"]
    present = [c for c in cols if c in id_map.columns]
    bio = id_map.select(present).filter(pl.col("gsis_id").is_not_null()).unique(subset=["gsis_id"])
    if "birthdate" in bio.columns:
        # Casting String->Date directly is deprecated and goes away in Polars 2.0.
        # The id_map ships birthdates as strings, so parse rather than cast.
        birthdate = pl.col("birthdate")
        if bio.schema["birthdate"] == pl.Utf8:
            birthdate = birthdate.str.to_date(strict=False)
        else:
            birthdate = birthdate.cast(pl.Date, strict=False)
        bio = bio.with_columns(birthdate.alias("birthdate"))
    return bio


def build_context_table(
    seasons: list[int] | None = None,
    write: bool = True,
) -> pl.DataFrame:
    """Build the player-season context table.

    Args:
        seasons: Seasons to cover. Defaults to every season in the weekly cache.
        write: Persist the result to ``data/research/player_season_context.parquet``.

    Returns:
        One row per skill-position player-season with situation flags, prior-season
        usage, vacated team opportunity, age and draft capital.
    """
    weekly = load_weekly(seasons=seasons)
    if weekly.is_empty():
        log.warning("build_context_table: no weekly data available")
        return pl.DataFrame()

    players = _player_seasons(weekly)
    if players.is_empty():
        log.warning("build_context_table: no skill-position player-seasons found")
        return pl.DataFrame()

    team_seasons = build_team_seasons(seasons=seasons)
    vacated = _vacated_opportunity(players)

    prior = players.select(
        "player_id",
        (pl.col("season") + 1).alias("season"),
        pl.col("team").alias("prior_team"),
        pl.col("games").alias("prior_games"),
        pl.col("targets").alias("prior_targets"),
        pl.col("carries").alias("prior_carries"),
        pl.col("target_share").alias("prior_target_share"),
        pl.col("air_yards_share").alias("prior_air_yards_share"),
        pl.col("wopr").alias("prior_wopr"),
    )

    df = (
        players.join(prior, on=["player_id", "season"], how="left")
        .join(team_seasons, on=["season", "team"], how="left")
        .join(vacated, on=["season", "team"], how="left")
    )

    # The coach/QB the player actually played for last season — which is his prior
    # team's staff, not his current team's prior staff.
    prior_staff = team_seasons.select(
        (pl.col("season") + 1).alias("season"),
        pl.col("team").alias("prior_team"),
        pl.col("head_coach").alias("prior_player_coach"),
        pl.col("primary_qb_id").alias("prior_player_qb_id"),
    )
    df = df.join(prior_staff, on=["season", "prior_team"], how="left")

    df = df.with_columns(
        team_changed=pl.when(pl.col("prior_team").is_null())
        .then(None)
        .otherwise(pl.col("team") != pl.col("prior_team")),
        coach_changed=pl.when(pl.col("prior_player_coach").is_null())
        .then(None)
        .otherwise(pl.col("head_coach") != pl.col("prior_player_coach")),
        qb_changed=pl.when(pl.col("prior_player_qb_id").is_null())
        .then(None)
        .otherwise(pl.col("primary_qb_id") != pl.col("prior_player_qb_id")),
    )

    bio = _player_bio()
    if bio.is_empty():
        log.warning("context table: id_map empty — age and draft capital columns omitted")
    else:
        df = df.join(bio, left_on="player_id", right_on="gsis_id", how="left")

    if "birthdate" in df.columns:
        df = df.with_columns(
            season_age=(
                (
                    pl.date(pl.col("season"), _SEASON_AGE_MONTH, _SEASON_AGE_DAY)
                    - pl.col("birthdate")
                ).dt.total_days()
                / 365.25
            ).round(1)
        )
    if "draft_year" in df.columns:
        df = df.with_columns(
            years_exp=(pl.col("season") - pl.col("draft_year")).cast(pl.Int32, strict=False)
        )

    df = df.sort(["season", "player_id"])

    if write:
        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        df.write_parquet(CONTEXT_TABLE_PATH)
        log.info("context table: %d player-seasons written to %s", len(df), CONTEXT_TABLE_PATH)

    return df


def load_context_table(rebuild: bool = False) -> pl.DataFrame:
    """Load the cached context table, building it if absent.

    Args:
        rebuild: Rebuild from source even when a cached parquet exists.
    """
    if CONTEXT_TABLE_PATH.exists() and not rebuild:
        return pl.read_parquet(CONTEXT_TABLE_PATH)
    return build_context_table()
