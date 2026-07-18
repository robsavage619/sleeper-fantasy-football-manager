"""FastAPI router for findings — Claude Code posts here, dashboard reads here."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sleeper_ffm.reasoning.findings import (
    Finding,
    latest_finding,
    list_findings,
    post_finding,
)

router = APIRouter(prefix="/findings", tags=["findings"])


class PostFindingRequest(BaseModel):
    """Request body for posting a new finding."""

    kind: str
    body: dict[str, Any]
    prompt_hash: str | None = None


class FindingResponse(BaseModel):
    """Serialized finding for API responses."""

    finding_id: str
    kind: str
    body: dict[str, Any]
    created_at: float
    prompt_hash: str | None = None

    @classmethod
    def from_finding(cls, f: Finding) -> FindingResponse:
        """Construct from a ``Finding`` dataclass."""
        return cls(
            finding_id=f.finding_id,
            kind=f.kind,
            body=f.body,
            created_at=f.created_at,
            prompt_hash=f.prompt_hash,
        )


@router.post("/", response_model=FindingResponse, status_code=201)
def post(req: PostFindingRequest) -> FindingResponse:
    """Post a new Claude Code finding to the store."""
    finding = post_finding(kind=req.kind, body=req.body, prompt_hash=req.prompt_hash)
    return FindingResponse.from_finding(finding)


@router.get("/", response_model=list[FindingResponse])
def list_all(kind: str | None = None, limit: int = 50) -> list[FindingResponse]:
    """List recent findings, optionally filtered by kind."""
    return [FindingResponse.from_finding(f) for f in list_findings(kind=kind, limit=limit)]


@router.get("/latest/{kind}", response_model=FindingResponse)
def latest(kind: str) -> FindingResponse:
    """Return the most recent finding of a given kind."""
    f = latest_finding(kind)
    if f is None:
        raise HTTPException(status_code=404, detail=f"No findings of kind '{kind}'")
    return FindingResponse.from_finding(f)


class TradeRec(BaseModel):
    """One trade recommendation. ``extra=allow``: unknown fields pass through untyped."""

    model_config = {"extra": "allow"}

    partner: str
    # A multi-asset leg ("pick + player") is legitimately a list, not just a string —
    # observed directly from real model output, not a hypothetical.
    send: str | list[str]
    receive: str | list[str]
    urgency: Literal["LOW", "MED", "HIGH"]
    rationale: str = ""


class WaiverRec(BaseModel):
    """One waiver recommendation. ``extra=allow``: unknown fields pass through untyped."""

    model_config = {"extra": "allow"}

    player: str
    faab_bid: int
    drop: str | None = None
    rationale: str = ""


class DraftRec(BaseModel):
    """One draft recommendation. ``extra=allow``: unknown fields pass through untyped."""

    model_config = {"extra": "allow"}

    pick: str
    alternatives: str = ""
    rationale: str = ""


class ProspectNote(BaseModel):
    """One prospect note. ``extra=allow``: unknown fields pass through untyped."""

    model_config = {"extra": "allow"}

    name: str
    verdict: str
    rationale: str = ""


class LineupRec(BaseModel):
    """One lineup recommendation. ``extra=allow``: unknown fields pass through untyped."""

    model_config = {"extra": "allow"}

    start: str
    sit: str
    rationale: str = ""


class MasterDocument(BaseModel):
    """The single JSON document Claude Code returns from the master briefing.

    Fields mirror ``prompts.master.MASTER_SCHEMA``. Every top-level field is
    required so a missing section is rejected LOUDLY with 422 by pydantic —
    never stored raw. Per-item fields are typed where a real format bug was
    observed (``faab_bid`` as a string, ``send``/``receive`` shape) and left
    loose (``extra=allow``) everywhere else, so an unanticipated extra key
    from the model doesn't get silently dropped or rejected.
    """

    model_config = {"extra": "forbid"}

    narrative: str
    trade_recs: list[TradeRec]
    waiver_recs: list[WaiverRec]
    draft_recs: list[DraftRec]
    prospect_notes: list[ProspectNote]
    lineup_recs: list[LineupRec]
    generated_at: str
    data_quality_ack: str


class BulkResponse(BaseModel):
    """Summary of a bulk ingest: how many findings were stored per kind."""

    stored: dict[str, int]
    total: int


# --- Typed single-surface reasoning documents (the /ai/* surfaces) ------------------
# Each focused surface (dossier, market edges, waivers, trade plan, prospect scout) posts
# ONE cohesive document, unlike the master briefing which fans out per item. Every model
# is ``extra=allow`` so an unanticipated key survives, but the load-bearing fields are
# typed so malformed model output is rejected with 422 instead of stored raw.


class _EdgeThesis(BaseModel):
    model_config = {"extra": "allow"}

    player: str
    thesis: str = ""
    target_partner: str = ""


class OwnerDossierDoc(BaseModel):
    """Exploit plan for one rival manager (kind ``owner_dossier``)."""

    model_config = {"extra": "allow"}

    target: str
    exploit_plan: str = ""
    angles: list[TradeRec] = []
    watch_items: list[str] = []
    generated_at: str
    data_quality_ack: str = ""


class MarketEdgeDoc(BaseModel):
    """Reconciled buy/sell board (kind ``market_edge``)."""

    model_config = {"extra": "allow"}

    buys: list[_EdgeThesis] = []
    sells: list[_EdgeThesis] = []
    reconciliations: str = ""
    generated_at: str
    data_quality_ack: str = ""


class _WaiverPlanRec(WaiverRec):
    """WaiverRec plus a bid tier."""

    tier: str = ""


class WaiverPlanDoc(BaseModel):
    """FAAB bid plan (kind ``waiver_plan``)."""

    model_config = {"extra": "allow"}

    waiver_recs: list[_WaiverPlanRec] = []
    holds: list[str] = []
    generated_at: str
    data_quality_ack: str = ""


class TradePlanDoc(BaseModel):
    """Franchise buy/sell posture + sequenced plan (kind ``trade_plan``)."""

    model_config = {"extra": "allow"}

    posture: str
    plan: str = ""
    trade_recs: list[TradeRec] = []
    sequencing: str = ""
    generated_at: str
    data_quality_ack: str = ""


class ProspectScoutDoc(BaseModel):
    """Deep per-prospect scouting insight (kind ``prospect_scout``).

    Mirrors the post shape in ``prompts.prospect_scouting``. ``player_id``/``name`` are
    required so the frontend drawer can match the finding back to a board row.
    """

    model_config = {"extra": "allow"}

    name: str
    player_id: str | None = None
    college: str = ""
    verdict: str = ""
    case: str = ""
    comps: list[str] = []
    team_fit: str = ""
    risk_notes: str | list[str] = ""
    consensus_check: str = ""
    sources: list[str] = []
    generated_at: str | None = None


# kind → validating model. A POST to /ai/finding with a known kind is validated against
# its model; an unknown kind falls through to the untyped POST /findings/ path.
TYPED_KINDS: dict[str, type[BaseModel]] = {
    "owner_dossier": OwnerDossierDoc,
    "market_edge": MarketEdgeDoc,
    "waiver_plan": WaiverPlanDoc,
    "trade_plan": TradePlanDoc,
    "prospect_scout": ProspectScoutDoc,
}


class TypedFindingRequest(BaseModel):
    """A typed single-surface finding: ``kind`` selects the schema ``body`` is checked against."""

    kind: str
    body: dict[str, Any]
    prompt_hash: str | None = None


@router.post("/typed", response_model=FindingResponse, status_code=201)
def post_typed(req: TypedFindingRequest) -> FindingResponse:
    """Post a single-surface finding, validating ``body`` against the kind's schema.

    Unlike ``/bulk`` (which fans a master document out per item), this stores ONE finding
    for the whole document. A known ``kind`` whose ``body`` fails validation is rejected
    422; an unknown ``kind`` is stored as-is (parity with the untyped ``POST /findings/``).
    """
    model = TYPED_KINDS.get(req.kind)
    if model is not None:
        try:
            validated = model.model_validate(req.body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        body = validated.model_dump()
    else:
        body = req.body
    finding = post_finding(kind=req.kind, body=body, prompt_hash=req.prompt_hash)
    return FindingResponse.from_finding(finding)


# Section name → (finding kind, whether the section is a list fanned out per-item).
_SECTION_KINDS: list[tuple[str, str, bool]] = [
    ("narrative", "narrative", False),
    ("trade_recs", "trade", True),
    ("waiver_recs", "waiver", True),
    ("draft_recs", "draft", True),
    ("prospect_notes", "prospect", True),
    ("lineup_recs", "lineup", True),
]


@router.post("/bulk", response_model=BulkResponse, status_code=201)
def post_bulk(doc: MasterDocument) -> BulkResponse:
    """Fan a validated master document out into the findings store, one kind per section.

    Pydantic validates ``doc`` before this handler runs, so a malformed or
    incomplete document is rejected with 422 and nothing is stored.
    """
    stored: dict[str, int] = {}
    for section, kind, is_list in _SECTION_KINDS:
        value = getattr(doc, section)
        items: list[dict[str, Any]] = (
            [rec.model_dump() for rec in value] if is_list else [{section: value}]
        )
        for item in items:
            post_finding(
                kind=kind,
                body={
                    **item,
                    "generated_at": doc.generated_at,
                    "data_quality_ack": doc.data_quality_ack,
                },
            )
        stored[kind] = len(items)
    return BulkResponse(stored=stored, total=sum(stored.values()))
