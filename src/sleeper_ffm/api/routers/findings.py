"""FastAPI router for findings — Claude Code posts here, dashboard reads here."""

from __future__ import annotations

from typing import Any

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
