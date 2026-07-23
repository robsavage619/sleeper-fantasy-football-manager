"""Per-player intel: why a player is likely to thrive here, or not.

The research program (studies S1-S6, `docs/research/`) produced findings the
engine had nowhere to put. Each one answers a different half of "why do players
produce", and individually none is a surface:

- A running back's usage history stops predicting after a team or coach change,
  while a receiver's survives (S2).
- Quarterback accuracy moves a pass catcher's points *per target* and not his
  target count, so a quarterback downgrade is an efficiency event, not a role
  event (S3).
- Archetype does not change how fast a surviving player declines, but it changes
  how likely he is to still be startable next year — receiving backs past 25
  carry roughly double a grinder's attrition (S4).
- Rookie outcomes collapse to three draft-capital tiers, and inside the top tier
  this league's lineup makes backs far safer than quarterbacks (S6).

This module composes them into one read per player, and is deliberately a
*reporting* layer rather than a scoring one: it states what is true about a
player's situation and what the research says that implies, without folding
everything into a single number. The findings have different strengths and
different confidence, and collapsing them would hide exactly the distinctions the
studies were run to establish.

Every flag carries the effect size behind it, because the product audit's standing
complaint is that engines compute explanations and then throw them away.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import polars as pl

log = logging.getLogger(__name__)

# --- Effect sizes from the studies. Changing these means re-running the study. ---

# S2: carryover correlation gap for a back who changed team vs one who did not,
# corrected for range restriction. Receivers show no replicable penalty.
RB_TEAM_CHANGE_GAP = -0.279
RB_COACH_CHANGE_GAP = -0.216

# S4: annual attrition by archetype and age band, P(no startable season next year).
ATTRITION: dict[tuple[str, str, str], float] = {
    ("RB", "grinder", "22-24"): 0.293,
    ("RB", "grinder", "25-27"): 0.285,
    ("RB", "grinder", "28+"): 0.350,
    ("RB", "receiving_back", "22-24"): 0.228,
    ("RB", "receiving_back", "25-27"): 0.411,
    ("RB", "receiving_back", "28+"): 0.560,
    ("WR", "field_stretcher", "22-24"): 0.230,
    ("WR", "field_stretcher", "25-27"): 0.209,
    ("WR", "field_stretcher", "28+"): 0.342,
    ("WR", "possession", "22-24"): 0.287,
    ("WR", "possession", "25-27"): 0.333,
    ("WR", "possession", "28+"): 0.432,
    ("TE", "field_stretcher", "22-24"): 0.208,
    ("TE", "field_stretcher", "25-27"): 0.259,
    ("TE", "field_stretcher", "28+"): 0.254,
    ("TE", "possession", "22-24"): 0.275,
    ("TE", "possession", "25-27"): 0.325,
    ("TE", "possession", "28+"): 0.438,
}

# S6: P(ever startable in career years 1-3) by NFL draft-capital tier, under this
# league's replacement line, with 95% Wilson intervals.
ROOKIE_TIERS: dict[str, tuple[float, float, float]] = {
    "A": (0.579, 0.505, 0.649),
    "B": (0.212, 0.171, 0.260),
    "C": (0.032, 0.023, 0.045),
}

# S6: hit rate inside tier A by position — a property of this lineup, not of football.
TIER_A_BY_POSITION: dict[str, float] = {"RB": 0.882, "WR": 0.568, "TE": 0.481, "QB": 0.389}

# S3: receiver points per game gained per standard deviation of QB accuracy.
QB_QUALITY_PTS_PER_SD: dict[str, float] = {"WR": 0.93, "TE": 0.48}


@dataclass
class IntelFlag:
    """One research-backed statement about a player.

    Attributes:
        kind: Short machine-readable category.
        severity: ``INFO`` | ``WATCH`` | ``ALERT`` — how much it should move a decision.
        headline: One-line human statement.
        evidence: The measured effect behind it, so the claim can be audited.
        study: Which study established it.
    """

    kind: str
    severity: str
    headline: str
    evidence: str
    study: str


@dataclass
class PlayerIntel:
    """Composed research read for one player."""

    player_id: str
    name: str
    position: str
    team: str
    age: float | None
    archetype: str | None
    flags: list[IntelFlag] = field(default_factory=list)

    @property
    def alert_count(self) -> int:
        """Number of flags severe enough to change a roster decision."""
        return sum(1 for f in self.flags if f.severity == "ALERT")


def age_band(age: float | None) -> str | None:
    """Bucket an age into the bands the attrition table is estimated over."""
    if age is None:
        return None
    if age < 25:
        return "22-24"
    if age < 28:
        return "25-27"
    return "28+"


def draft_tier(draft_round: float | None) -> str:
    """Collapse an NFL draft round into the three tiers S6 found are distinguishable."""
    if draft_round is None:
        return "C"
    if draft_round <= 2:
        return "A"
    if draft_round <= 5:
        return "B"
    return "C"


def rookie_hit_rates(draft_year: int) -> dict[str, dict[str, object]]:
    """Map Sleeper player IDs in one draft class to their S6 hit-rate priors.

    A rookie board ranked purely on projected value invites overconfidence: it
    says which prospect is best without saying how often that kind of prospect
    works out at all. This supplies the base rate.

    Args:
        draft_year: NFL entry year of the class.

    Returns:
        ``{sleeper_id: {"round", "tier", "rate", "position_rate"}}``. Players
        without recorded draft capital are treated as tier C, which is what
        undrafted status actually implies.
    """
    from sleeper_ffm.nflverse.loader import load_id_map

    try:
        id_map = load_id_map()
    except (FileNotFoundError, OSError) as exc:
        log.warning("rookie_hit_rates: id_map unavailable (%s)", exc)
        return {}

    rows = id_map.filter(
        (pl.col("draft_year") == draft_year)
        & pl.col("sleeper_id").is_not_null()
        & pl.col("position").is_in(["QB", "RB", "WR", "TE"])
    )

    out: dict[str, dict[str, object]] = {}
    for row in rows.iter_rows(named=True):
        sleeper_id = row.get("sleeper_id")
        if sleeper_id is None:
            continue
        rnd = row.get("draft_round")
        rnd_val = float(rnd) if isinstance(rnd, (int, float)) else None
        tier = draft_tier(rnd_val)
        rate, _low, _high = ROOKIE_TIERS[tier]
        position = str(row.get("position") or "")
        out[str(int(sleeper_id))] = {
            "round": int(rnd_val) if rnd_val is not None else None,
            "tier": tier,
            "rate": rate,
            "position_rate": TIER_A_BY_POSITION.get(position) if tier == "A" else None,
        }
    return out


def qb_context_flag(position: str, team: str, delta: float) -> IntelFlag | None:
    """Flag from S3 — what this player's quarterback situation is worth in points.

    Args:
        position: Player position; only pass catchers are affected.
        team: Team abbreviation, used in the wording.
        delta: Expected points per game versus a league-average quarterback.

    Returns:
        A flag when the effect is large enough to matter, otherwise ``None`` —
        a quarterback near league average is not news.
    """
    if position not in QB_QUALITY_PTS_PER_SD:
        return None
    if abs(delta) < 0.30:
        return None

    helped = delta > 0
    season_swing = abs(delta) * 28
    return IntelFlag(
        kind="qb_context",
        severity="ALERT" if abs(delta) >= 1.0 else "WATCH",
        headline=(
            f"{team}'s quarterback play is worth {delta:+.2f} pts/game to him "
            f"({'roughly ' + format(season_swing, '.0f')} points across a 28-game season"
            f"{' in his favour' if helped else ' against him'})."
        ),
        evidence=(
            "Measured on points per target, not target volume — quarterback quality "
            "moves efficiency (r=+0.34) and not usage (r=-0.09). Association rather "
            "than a clean causal estimate, so treat this as an upper bound."
        ),
        study="S3",
    )


def situation_flags(row: dict[str, object]) -> list[IntelFlag]:
    """Flags from S2 — whether this player's usage history still applies."""
    flags: list[IntelFlag] = []
    position = str(row.get("position") or "")

    if position == "RB":
        if row.get("team_changed") is True:
            flags.append(
                IntelFlag(
                    kind="usage_history_void",
                    severity="ALERT",
                    headline=(
                        "Changed teams — his usage history barely predicts his new role. "
                        "Widen the range rather than lowering the projection."
                    ),
                    evidence=(
                        "Prior target share explains ~17% of new usage for a back who moved "
                        f"vs ~48% for one who stayed (corrected gap {RB_TEAM_CHANGE_GAP})."
                    ),
                    study="S2",
                )
            )
        elif row.get("coach_changed") is True:
            flags.append(
                IntelFlag(
                    kind="play_caller_change",
                    severity="WATCH",
                    headline=(
                        "New play-caller — a back's role is rewritten almost as "
                        "often as by a trade."
                    ),
                    evidence=f"Carryover gap {RB_COACH_CHANGE_GAP} without changing team.",
                    study="S2",
                )
            )
    elif position in ("WR", "TE") and row.get("team_changed") is True:
        flags.append(
            IntelFlag(
                kind="role_travels",
                severity="INFO",
                headline=(
                    "Changed teams, but a receiver's role travels — do not discount his history."
                ),
                evidence="WR carryover penalty was -0.006 out of sample: no replicable effect.",
                study="S2",
            )
        )

    if row.get("qb_changed") is True and position in ("WR", "TE"):
        per_sd = QB_QUALITY_PTS_PER_SD.get(position, 0.0)
        flags.append(
            IntelFlag(
                kind="qb_change_efficiency",
                severity="WATCH",
                headline=(
                    "New quarterback — expect the hit to land on efficiency, not volume. "
                    "His targets should hold; his points per target may not."
                ),
                evidence=(
                    f"QB accuracy moves {position} points per target (r=+0.34) and not "
                    f"target count (r=-0.09). 1sd of QB accuracy is worth ~{per_sd} pts/game."
                ),
                study="S3",
            )
        )
    return flags


def attrition_flag(position: str, archetype: str | None, age: float | None) -> IntelFlag | None:
    """Flag from S4 — the risk that this player is simply gone next year."""
    band = age_band(age)
    if archetype is None or band is None:
        return None
    rate = ATTRITION.get((position, archetype, band))
    if rate is None:
        return None

    counterpart = _counterpart(position, archetype)
    baseline = ATTRITION.get((position, counterpart, band))
    severity = "ALERT" if rate >= 0.40 else "WATCH" if rate >= 0.30 else "INFO"
    comparison = (
        f" against {baseline:.0%} for the {_readable(position, counterpart)} profile"
        if baseline is not None
        else ""
    )
    return IntelFlag(
        kind="attrition_risk",
        severity=severity,
        headline=(
            f"{rate:.0%} chance of not being startable next season as a "
            f"{_readable(position, archetype)} aged {band}."
        ),
        evidence=(
            f"Observed annual attrition {rate:.1%}{comparison}. Archetype changes survival, "
            "not the rate of decline among survivors."
        ),
        study="S4",
    )


def _readable(position: str, archetype: str) -> str:
    """Turn an archetype key into a phrase that reads as English in a sentence."""
    noun = "back" if position == "RB" else "receiver" if position == "WR" else "tight end"
    return {
        "grinder": f"between-the-tackles {noun}",
        "receiving_back": f"pass-catching {noun}",
        "possession": f"possession {noun}",
        "field_stretcher": f"field-stretching {noun}",
    }.get(archetype, archetype.replace("_", " "))


def _counterpart(position: str, archetype: str) -> str:
    """The other archetype at this position, for contrast in the evidence line."""
    if position == "RB":
        return "grinder" if archetype == "receiving_back" else "receiving_back"
    return "field_stretcher" if archetype == "possession" else "possession"


def rookie_flag(position: str, draft_round: float | None, is_rookie: bool) -> IntelFlag | None:
    """Flag from S6 — what this player's draft capital is worth in this league."""
    if not is_rookie:
        return None
    tier = draft_tier(draft_round)
    rate, low, high = ROOKIE_TIERS[tier]
    severity = "INFO" if tier == "A" else "WATCH" if tier == "B" else "ALERT"

    position_note = ""
    if tier == "A" and position in TIER_A_BY_POSITION:
        pos_rate = TIER_A_BY_POSITION[position]
        position_note = (
            f" Within this tier, {position}s hit {pos_rate:.0%} in this lineup"
            f"{' — the safest rookie asset here' if position == 'RB' else ''}"
            f"{' — the least reliable, since only one starts' if position == 'QB' else ''}."
        )
    return IntelFlag(
        kind="rookie_tier",
        severity=severity,
        headline=(
            f"Draft-capital tier {tier}: {rate:.0%} chance of a startable season in years 1-3."
            f"{position_note}"
        ),
        evidence=(
            f"95% CI [{low:.0%}, {high:.0%}], measured against this league's own replacement "
            "line, counting players who never played as misses."
        ),
        study="S6",
    )


def build_player_intel(
    context_row: dict[str, object],
    archetype: str | None = None,
    is_rookie: bool = False,
    qb_context: dict[str, float] | None = None,
) -> PlayerIntel:
    """Compose every applicable research flag for one player.

    Args:
        context_row: A row from the player-season context table, carrying the
            situation-change flags, position, team and age.
        archetype: Archetype label from :mod:`model.research.archetypes`, if known.
        is_rookie: Whether this is the player's entry season.
        qb_context: ``{team: pts/game}`` from
            :func:`model.research.qb_quality.team_qb_context`, if available.

    Returns:
        The player's intel record, flags ordered most severe first.
    """
    position = str(context_row.get("position") or "")
    age_raw = context_row.get("season_age")
    age = float(age_raw) if isinstance(age_raw, (int, float)) else None

    flags = situation_flags(context_row)

    team = str(context_row.get("team") or "")
    if qb_context and team in qb_context:
        qb_flag = qb_context_flag(position, team, qb_context[team])
        if qb_flag is not None:
            flags.append(qb_flag)

    attrition = attrition_flag(position, archetype, age)
    if attrition is not None:
        flags.append(attrition)

    draft_round_raw = context_row.get("draft_round")
    draft_round = float(draft_round_raw) if isinstance(draft_round_raw, (int, float)) else None
    rookie = rookie_flag(position, draft_round, is_rookie)
    if rookie is not None:
        flags.append(rookie)

    order = {"ALERT": 0, "WATCH": 1, "INFO": 2}
    flags.sort(key=lambda f: order.get(f.severity, 3))

    return PlayerIntel(
        player_id=str(context_row.get("player_id") or ""),
        name=str(context_row.get("name") or ""),
        position=position,
        team=str(context_row.get("team") or ""),
        age=age,
        archetype=archetype,
        flags=flags,
    )


def build_roster_intel(
    context: pl.DataFrame,
    archetypes: pl.DataFrame | None = None,
    season: int | None = None,
    sleeper_ids: set[str] | None = None,
    qb_context: dict[str, float] | None = None,
) -> list[PlayerIntel]:
    """Build intel for players in a context frame.

    Args:
        context: Player-season context rows (see :mod:`model.context_table`).
        archetypes: Optional archetype labels keyed by ``player_id``/``season``.
        season: Restrict to this season; defaults to the latest present.
        sleeper_ids: Restrict to these Sleeper player IDs — pass a roster to get
            intel about players you actually hold. Omitting it scans the league,
            which is what a waiver or trade-target sweep wants.
        qb_context: ``{team: pts/game}`` quarterback-quality effects, if available.

    Returns:
        Intel records sorted by alert count descending — the players whose
        situation most undermines their track record come first.
    """
    if context.is_empty():
        return []

    target = season if season is not None else context["season"].max()
    rows = context.filter(pl.col("season") == target)

    if sleeper_ids is not None:
        if "sleeper_id" not in rows.columns:
            log.warning("build_roster_intel: no sleeper_id column; cannot scope to a roster")
            return []
        wanted = {str(s) for s in sleeper_ids}
        rows = rows.filter(
            pl.col("sleeper_id").is_not_null()
            & pl.col("sleeper_id").cast(pl.Int64, strict=False).cast(pl.Utf8).is_in(list(wanted))
        )

    if rows.is_empty():
        return []

    archetype_by_player: dict[str, str] = {}
    if archetypes is not None and not archetypes.is_empty():
        sub = archetypes.filter(pl.col("season") == target)
        archetype_by_player = {
            str(r["player_id"]): str(r["archetype"]) for r in sub.iter_rows(named=True)
        }

    intel: list[PlayerIntel] = []
    for row in rows.iter_rows(named=True):
        player_id = str(row.get("player_id") or "")
        draft_year = row.get("draft_year")
        is_rookie = isinstance(draft_year, (int, float)) and int(draft_year) == target
        intel.append(
            build_player_intel(
                row,
                archetype=archetype_by_player.get(player_id),
                is_rookie=is_rookie,
                qb_context=qb_context,
            )
        )

    return sorted(intel, key=lambda i: i.alert_count, reverse=True)
