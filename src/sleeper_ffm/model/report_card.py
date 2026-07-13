"""League Report Card — graded, ranked franchise report for every manager.

Composes the data the app already computes (manager skill index, owner
profiles, transaction history) plus season-by-season standings into a single
graded report card. Every dimension is graded **on the curve within this
league** — the point is comparative ("who is running the best franchise
here"), so grades are rank-based, not fabricated absolute thresholds.

Dimensions (weight):
  VALUE 0.25     — current dynasty roster value
  SKILL 0.25     — manager acumen (all-play, lineup efficiency, luck-adjusted)
  TRACK 0.20     — historical win% + championships
  BUILD 0.10     — roster balance across skill positions
  CAPITAL 0.10   — future draft-pick stockpile
  ACTIVITY 0.10  — engagement (trades / waivers / FAAB per season)
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)

# Rank-based letter ladder (best → worst). Interpolated across league size.
_LETTERS = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D"]

_SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

_WEIGHTS = {
    "value": 0.25,
    "skill": 0.25,
    "track": 0.20,
    "build": 0.10,
    "capital": 0.10,
    "activity": 0.10,
}


@dataclass
class DimensionGrade:
    """One graded dimension for one manager."""

    key: str
    label: str
    grade: str
    rank: int
    of: int
    value: float  # the underlying raw metric (for display)
    detail: str


@dataclass
class ManagerReportCard:
    """A full graded, ranked report card for one manager."""

    roster_id: int
    display_name: str
    avatar: str | None
    is_me: bool
    overall_grade: str
    overall_rank: int
    overall_score: float  # 0-100 composite
    dimensions: list[dict] = field(default_factory=list)
    # Track record
    record: str = "—"
    win_pct: float = 0.0
    titles: int = 0
    playoff_appearances: int = 0
    seasons_played: int = 0
    best_finish: int | None = None
    season_history: list[dict] = field(default_factory=list)
    headline: str = ""


def _grade_for_rank(rank: int, n: int) -> str:
    if n <= 1:
        return _LETTERS[0]
    idx = round((rank - 1) / (n - 1) * (len(_LETTERS) - 1))
    return _LETTERS[min(idx, len(_LETTERS) - 1)]


def _rank_desc(values: dict[int, float]) -> dict[int, int]:
    """Return {roster_id: rank} with 1 = highest value (ties broken by roster_id)."""
    ordered = sorted(values, key=lambda rid: (values[rid], -rid), reverse=True)
    return {rid: i + 1 for i, rid in enumerate(ordered)}


def _balance_score(positions: dict[str, int]) -> float:
    """Roster construction proxy: penalize holes at skill positions, reward depth."""
    counts = [positions.get(p, 0) for p in _SKILL_POSITIONS]
    if not any(counts):
        return 0.0
    holes = sum(1 for c in counts if c <= 1)
    depth = sum(min(c, 5) for c in counts)
    return depth - holes * 2.5


def _activity_score(hist) -> float:
    return (hist.trades_per_season * 3.0) + hist.adds_per_season + (hist.faab_per_season / 25.0)


def build_report_card(my_roster_id: int | None = None) -> list[dict]:
    """Build the ranked, graded league report card for every manager."""
    from sleeper_ffm.config import MY_ROSTER_ID
    from sleeper_ffm.model.owner_history import build_league_history
    from sleeper_ffm.model.owner_profile import build_owner_profiles
    from sleeper_ffm.model.owner_skill import build_owner_skill
    from sleeper_ffm.model.season_standings import build_season_standings

    me = my_roster_id if my_roster_id is not None else MY_ROSTER_ID

    skills = {s.roster_id: s for s in build_owner_skill()}
    profiles = {p.roster_id: p for p in build_owner_profiles()}
    history = {h.roster_id: h for h in build_league_history().owners}
    tracks = build_season_standings()

    roster_ids = sorted(profiles)
    n = len(roster_ids)
    if not n:
        return []

    # Raw metric per dimension, keyed by roster_id.
    raw: dict[str, dict[int, float]] = {
        "value": {
            rid: float(getattr(skills.get(rid), "roster_value", 0) or 0) for rid in roster_ids
        },
        "skill": {
            rid: float(getattr(skills.get(rid), "skill_score", 0) or 0) for rid in roster_ids
        },
        "track": {
            rid: (tracks[rid].win_pct * 100 + tracks[rid].titles * 12 if rid in tracks else 0.0)
            for rid in roster_ids
        },
        "build": {rid: _balance_score(profiles[rid].positions) for rid in roster_ids},
        "capital": {rid: float(profiles[rid].picks_owned) for rid in roster_ids},
        "activity": {
            rid: _activity_score(history[rid]) if rid in history else 0.0 for rid in roster_ids
        },
    }
    ranks = {dim: _rank_desc(vals) for dim, vals in raw.items()}

    labels = {
        "value": "Roster Value",
        "skill": "Manager Skill",
        "track": "Track Record",
        "build": "Roster Build",
        "capital": "Draft Capital",
        "activity": "Activity",
    }

    def detail(dim: str, rid: int) -> str:
        s, p, h, t = skills.get(rid), profiles[rid], history.get(rid), tracks.get(rid)
        if dim == "value" and s:
            return f"{int(s.roster_value):,} DV ({s.roster_value_pct:.0%} of avg)"
        if dim == "skill" and s:
            return (
                f"skill {s.skill_score:.0f} · {s.allplay_pct:.0%} all-play · "
                f"{s.schedule_luck:+.1f} luck"
            )
        if dim == "track" and t:
            titles = f"{t.titles} title{'s' if t.titles != 1 else ''}"
            return f"{t.win_pct:.0%} win · {titles} · {t.playoff_appearances} playoff"
        if dim == "build":
            return " ".join(f"{pos}{p.positions.get(pos, 0)}" for pos in _SKILL_POSITIONS)
        if dim == "capital":
            return f"{p.picks_owned} picks held"
        if dim == "activity" and h:
            return (
                f"{h.trades_per_season:.1f} trades · {h.adds_per_season:.0f} adds · "
                f"{h.faab_per_season:.0f} FAAB /yr"
            )
        return ""

    # Composite: normalize each dimension 0-1 (min-max), weight, scale to 0-100.
    overall_raw: dict[int, float] = {}
    for rid in roster_ids:
        total = 0.0
        for dim, w in _WEIGHTS.items():
            vals = list(raw[dim].values())
            lo, hi = min(vals), max(vals)
            norm = (raw[dim][rid] - lo) / (hi - lo) if hi > lo else 0.5
            total += norm * w
        overall_raw[rid] = round(total * 100, 1)
    overall_rank = _rank_desc(overall_raw)

    cards: list[ManagerReportCard] = []
    for rid in roster_ids:
        prof = profiles[rid]
        sk = skills.get(rid)
        trk = tracks.get(rid)
        dims = [
            DimensionGrade(
                key=dim,
                label=labels[dim],
                grade=_grade_for_rank(ranks[dim][rid], n),
                rank=ranks[dim][rid],
                of=n,
                value=round(raw[dim][rid], 1),
                detail=detail(dim, rid),
            )
            for dim in _WEIGHTS
        ]
        record = (
            f"{trk.career_wins}-{trk.career_losses}"
            + (f"-{trk.career_ties}" if trk and trk.career_ties else "")
            if trk and trk.seasons_played
            else "—"
        )
        card = ManagerReportCard(
            roster_id=rid,
            display_name=prof.display_name or f"Roster {rid}",
            avatar=getattr(sk, "avatar", None) or getattr(prof, "avatar", None),
            is_me=rid == me,
            overall_grade=_grade_for_rank(overall_rank[rid], n),
            overall_rank=overall_rank[rid],
            overall_score=overall_raw[rid],
            dimensions=[asdict(d) for d in dims],
            record=record,
            win_pct=trk.win_pct if trk else 0.0,
            titles=trk.titles if trk else 0,
            playoff_appearances=trk.playoff_appearances if trk else 0,
            seasons_played=trk.seasons_played if trk else 0,
            best_finish=trk.best_finish if trk else None,
            season_history=[asdict(s) for s in (trk.seasons if trk else [])],
            headline=_headline(prof, sk, trk, dims),
        )
        cards.append(card)

    cards.sort(key=lambda c: c.overall_rank)
    return [asdict(c) for c in cards]


def _headline(prof, sk, trk, dims) -> str:
    """One-line character read for this manager."""
    best = min(dims, key=lambda d: d.rank)
    worst = max(dims, key=lambda d: d.rank)
    title_bit = f"{trk.titles}x champ · " if trk and trk.titles else ""
    return f"{title_bit}elite {best.label.lower()}, soft {worst.label.lower()}"
