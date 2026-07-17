"""Tier-3 scripted grading — validate a candidate MasterDocument against a fixture.

Runs entirely in-process: no server, no ``POST /findings/bulk``, zero writes to
``data/findings.jsonl``. Only the fully-scriptable checks live here (schema
validity, planted-fact presence, closed-universe player names, FAAB bounds);
prose-quality judgment is the in-chat model's job, guided by
``evals/rubrics/tier3_rubric.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from sleeper_ffm.api.routers.findings import MasterDocument
from sleeper_ffm.evals.briefings import FIXTURES


@dataclass
class GradeResult:
    """Scripted grading outcome for one candidate MasterDocument."""

    fixture: str
    schema_ok: bool
    taxonomy: list[str]
    details: list[str]


def _collect_text(value: Any, parts: list[str]) -> None:
    """Flatten every string in a nested dict/list structure into ``parts``."""
    if isinstance(value, str):
        parts.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_text(v, parts)
    elif isinstance(value, list):
        for v in value:
            _collect_text(v, parts)


def grade_doc(fixture_name: str, doc_dict: dict[str, Any]) -> GradeResult:
    """Score a candidate MasterDocument against a fixture's planted-fact spec.

    Args:
        fixture_name: A key in ``sleeper_ffm.evals.briefings.FIXTURES``.
        doc_dict: The candidate document, parsed from the model's raw JSON output.

    Returns:
        A ``GradeResult`` listing every scripted taxonomy code triggered.

    Raises:
        ValueError: If ``fixture_name`` is not a known fixture.
    """
    fixture = FIXTURES.get(fixture_name)
    if fixture is None:
        raise ValueError(f"unknown tier-3 fixture: {fixture_name}")

    try:
        MasterDocument.model_validate(doc_dict)
    except ValidationError as exc:
        return GradeResult(fixture_name, False, ["SCHEMA_VIOLATION"], [str(exc)])

    spec = fixture.expect
    taxonomy: list[str] = []
    details: list[str] = []

    text_parts: list[str] = []
    _collect_text(doc_dict, text_parts)
    blob = "\n".join(text_parts)

    blob_lower = blob.lower()
    for phrase in spec.must_mention:
        if phrase.lower() not in blob_lower:
            taxonomy.append("MISSED_PLANTED_SIGNAL")
            details.append(f"missing required mention: {phrase!r}")

    # Scoped to structured decision fields (a cited trade partner or waiver
    # player), not the whole document blob: correctly naming a decoy rumor in
    # the narrative/ack in order to DISMISS it is the desired behavior, not a
    # hallucination. Only acting on the decoy as a real partner/asset counts.
    decision_fields: list[str] = []
    for rec in doc_dict.get("trade_recs", []):
        decision_fields += [str(rec.get(f, "")) for f in ("partner", "send", "receive")]
    for rec in doc_dict.get("waiver_recs", []):
        decision_fields.append(str(rec.get("player", "")))
    decision_blob = "\n".join(decision_fields).lower()
    for phrase in spec.must_not_mention:
        if phrase.lower() in decision_blob:
            taxonomy.append("HALLUCINATED_ENTITY")
            details.append(f"cited forbidden entity as a decision object: {phrase!r}")

    if spec.allowed_player_names:
        allowed_lower = [a.lower() for a in spec.allowed_player_names]
        for rec in doc_dict.get("trade_recs", []) + doc_dict.get("waiver_recs", []):
            for field_name in ("send", "receive", "player"):
                value = rec.get(field_name)
                # A multi-asset trade leg may legitimately be a list of strings,
                # not just one string — check each entry, not the field as a whole.
                names = value if isinstance(value, list) else [value] if value else []
                for name in names:
                    # Draft-pick legs ("2027 1st-round pick") are not players and
                    # were never in allowed_player_names to begin with — skip them.
                    if isinstance(name, str) and "pick" in name.lower():
                        continue
                    if isinstance(name, str) and not any(a in name.lower() for a in allowed_lower):
                        taxonomy.append("HALLUCINATED_ENTITY")
                        details.append(f"unrecognized player name: {name!r}")

    ack_lower = doc_dict.get("data_quality_ack", "").lower()
    for phrase in spec.ack_must_contain:
        if phrase.lower() not in ack_lower:
            taxonomy.append("MISSED_PLANTED_SIGNAL")
            details.append(f"data_quality_ack missing: {phrase!r}")

    for player_name, (lo, hi) in spec.faab_bounds.items():
        for rec in doc_dict.get("waiver_recs", []):
            # Substring match, not exact equality: real output routinely appends
            # a position tag ("Jamal Otis (WR)"), which an exact match would miss.
            if player_name.lower() in str(rec.get("player", "")).lower():
                bid = rec.get("faab_bid")
                if not (isinstance(bid, int | float) and lo <= bid <= hi):
                    taxonomy.append("UNJUSTIFIED_CONFIDENCE")
                    details.append(f"{player_name} faab_bid {bid} outside [{lo}, {hi}]")

    return GradeResult(fixture_name, True, taxonomy, details)
