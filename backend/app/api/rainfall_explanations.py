"""Live evidence and on-demand explanations. No verdict/evidence write endpoints."""
import json
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.rainfall import _require
from backend.app.config import settings
from backend.app.db.database import get_db
from backend.app.rainfall.evidence import DecisionEvidence
from backend.app.rainfall.explanation_service import ExplanationService
from backend.app.rainfall.explanation_store import ExplanationRecord, record_response
from backend.app.rainfall.explanations import MAX_BYTES


def authorize(authorization: str | None = Header(default=None)):
    if settings.EVIDENCE_API_TOKEN and not secrets.compare_digest(
            authorization or "", f"Bearer {settings.EVIDENCE_API_TOKEN}"):
        raise HTTPException(401, "Evidence API token required", headers={"WWW-Authenticate": "Bearer"})


router = APIRouter(prefix="/api/rainfall", tags=["rainfall explanations"], dependencies=[Depends(authorize)])
service = ExplanationService()


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    use_narrator: bool = False


@router.get("/evidence-schema")
async def evidence_schema():
    return DecisionEvidence.model_json_schema()


@router.get("/stations/{station_id}/evidence")
async def live_evidence(station_id: str):
    svc = _require()
    if station_id not in svc.stations:
        raise HTTPException(404, "Station is not being polled")
    try:
        evidence = svc.decision_evidence(station_id)
    except ValueError:
        raise HTTPException(409, "No reading has been received yet")
    payload = {"evidence_hash": evidence.digest(), "evidence": evidence.model_dump()}
    if len(json.dumps(payload).encode()) > MAX_BYTES:
        # No partial evidence: the narrator must explain the same complete decision.
        raise HTTPException(413, "Evidence exceeds the current 64 KB limit")
    return payload


@router.post("/stations/{station_id}/explanations", status_code=201)
async def explain_station(station_id: str, body: ExplainRequest, session: AsyncSession = Depends(get_db)):
    current = await live_evidence(station_id)
    if not secrets.compare_digest(current["evidence_hash"], body.evidence_hash):
        raise HTTPException(409, "Reading or evidence changed; reload the evidence before explaining")
    evidence = DecisionEvidence.model_validate(current["evidence"])
    record = await service.explain(session, evidence, body.use_narrator, settings.NARRATOR_URL, settings.NARRATOR_TOKEN)
    return record_response(record)


@router.get("/explanations/{explanation_id}")
async def stored_explanation(explanation_id: str, session: AsyncSession = Depends(get_db)):
    record = await session.get(ExplanationRecord, explanation_id)
    if record is None:
        raise HTTPException(404, "Explanation not found")
    return record_response(record)
