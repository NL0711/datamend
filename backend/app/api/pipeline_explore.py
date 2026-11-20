"""Explore step: dynamic validation tables, the assistant, dataset profiles, cleaning policy and proposals, stations with locations, and the model card.
Reading needs the app-wide sign-in; anything that writes needs the admin session (require_admin). Services hold the logic; routes only translate."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.settings import require_admin
from backend.app.db.database import get_db
from backend.app.pipeline import assistant as assistant_svc
from backend.app.pipeline import cleaning as cleaning_svc
from backend.app.pipeline import explore as explore_svc
from backend.app.pipeline import modelcard as modelcard_svc
from backend.app.pipeline import profile as profile_svc
from backend.app.pipeline import qc as qc_svc
from backend.app.validation.models import ValidationRun
from backend.app.validation.runs import run_dict

router = APIRouter(prefix="/api/pipeline", tags=["pipeline-explore"])


def _bad(e: Exception, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, str(e))


# ------------------------------------------------------------------------------------------------ tables and query
@router.get("/explore/tables")
async def explore_tables() -> Dict[str, Any]:
    return explore_svc.table_list()


class Filter(BaseModel):
    column: str = Field(max_length=40)
    op: str = Field(max_length=12)
    value: Any = None


class Aggregate(BaseModel):
    fn: str = Field(max_length=8)
    column: Optional[str] = Field(None, max_length=40)
    as_: Optional[str] = Field(None, alias="as", max_length=40)
    model_config = {"populate_by_name": True}


class OrderBy(BaseModel):
    column: str = Field(max_length=40)
    dir: str = Field("asc", max_length=12)


class QueryBody(BaseModel):
    table: str = Field(max_length=40)
    columns: Optional[List[str]] = Field(None, max_length=30)
    filters: Optional[List[Filter]] = Field(None, max_length=20)
    group_by: Optional[List[str]] = Field(None, max_length=5)
    aggregates: Optional[List[Aggregate]] = Field(None, max_length=10)
    order_by: Optional[List[OrderBy]] = Field(None, max_length=5)
    limit: Optional[int] = None
    run_id: Optional[int] = None


@router.post("/explore/query")
async def explore_query(body: QueryBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    d = body.model_dump(by_alias=True)
    d["aggregates"] = [{"fn": a["fn"], "column": a["column"], "as": a["as"]} for a in (d.get("aggregates") or [])]
    try:
        return await explore_svc.run_query(session, d)
    except explore_svc.QueryError as e:
        raise _bad(e)


@router.get("/explore/stations")
async def explore_stations(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await explore_svc.stations_view(session)


# ------------------------------------------------------------------------------------------------ profile
@router.get("/explore/profile")
async def get_profile(source: str = Query(..., min_length=1, max_length=16), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await profile_svc.get_profile(session, source)


class ProfileEdit(BaseModel):
    parameter: Optional[str] = Field(None, max_length=40)
    kind: Optional[str] = Field(None, max_length=32)
    units: Optional[str] = Field(None, max_length=20)
    valid_range: Optional[List[float]] = Field(None, max_length=2)
    missing_codes: Optional[List[float]] = Field(None, max_length=20)


@router.put("/explore/profile", dependencies=[Depends(require_admin)])
async def edit_profile(body: ProfileEdit, source: str = Query(..., min_length=1, max_length=16), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Edit what the user knows better than the detection (parameter, kind, units, valid range, missing codes). Detected counts are never editable."""
    try:
        await profile_svc.save_overrides(session, source, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise _bad(e)
    return await profile_svc.get_profile(session, source)


@router.get("/clean/policy/default")
async def default_policy(source: str = Query(..., min_length=1, max_length=16), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    prof = await profile_svc.get_profile(session, source)
    return {"source": source, "policy": profile_svc.default_policy(prof), "profile": prof}


# ------------------------------------------------------------------------------------------------ cleaning
class PlanBody(BaseModel):
    source: str = Field(min_length=1, max_length=16)
    policy: Optional[Dict[str, Any]] = None
    method: Optional[Literal["auto", "linear", "exclude"]] = None          # the first contract's shortcut, mapped onto a policy
    max_gap_hours: Optional[int] = Field(None, ge=1, le=cleaning_svc.MAX_GAP)


@router.post("/clean/plan", dependencies=[Depends(require_admin)])
async def clean_plan(body: PlanBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Create cleaning proposals from a policy (the dataset's default when absent). Refusals come back in `skipped` with the reason."""
    try:
        return await cleaning_svc.plan(session, body.source, body.policy, body.method if body.method != "auto" else None, body.max_gap_hours)
    except cleaning_svc.PolicyError as e:
        raise _bad(e)


@router.get("/clean/proposals")
async def clean_proposals(status_: Literal["pending", "accepted", "rejected", "all"] = Query("pending", alias="status"), station: Optional[str] = Query(None, max_length=64),
                          limit: int = Query(200, ge=1, le=1000), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = await cleaning_svc.list_proposals(session, status_, station, limit)
    return {"proposals": rows, "count": len(rows), "note": "imputed values are derived, not measured; raw observations are never changed"}


class DecideBody(BaseModel):
    accept: bool


@router.post("/clean/proposals/{proposal_id}/decide", dependencies=[Depends(require_admin)])
async def clean_decide(proposal_id: int, body: DecideBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        return await cleaning_svc.decide(session, proposal_id, body.accept)
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        raise _bad(e, status.HTTP_409_CONFLICT)


class ApplyBody(BaseModel):
    source: Optional[str] = Field(None, max_length=16)
    accept_pending: bool = False


@router.post("/clean/apply", dependencies=[Depends(require_admin)])
async def clean_apply(body: ApplyBody = ApplyBody(), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await cleaning_svc.apply_summary(session, body.source, body.accept_pending)


class CleanCheckBody(BaseModel):
    source: str = Field(min_length=1, max_length=16)
    use_clean: bool = True
    start: Optional[date] = None
    end: Optional[date] = None


@router.post("/clean/check", dependencies=[Depends(require_admin)])
async def clean_check(body: CleanCheckBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Run the checks on a source, including accepted cleaning when use_clean. Verdicts exist for rainfall only: another parameter is refused (422)."""
    prof = await profile_svc.get_profile(session, body.source)
    if not prof["verdicts"]["available"] and prof["parameter"] != "unknown":
        raise _bad(ValueError(prof["verdicts"]["note"]), status.HTTP_422_UNPROCESSABLE_ENTITY)
    try:
        run = await qc_svc.run_qc(session, body.source, None, body.start, body.end, use_clean=body.use_clean)
    except ValueError as e:
        raise _bad(e, status.HTTP_422_UNPROCESSABLE_ENTITY)
    return run_dict(run)


# ------------------------------------------------------------------------------------------------ assistant and model card
class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=1000)


class AssistantBody(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: Optional[List[Turn]] = Field(None, max_length=20)
    run_id: Optional[int] = None


@router.post("/assistant")
async def assistant(body: AssistantBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    if body.run_id is not None and await session.get(ValidationRun, body.run_id) is None:
        raise _bad(ValueError("no such run"), status.HTTP_404_NOT_FOUND)
    return await assistant_svc.respond(session, body.message, [t.model_dump() for t in body.history or []], body.run_id)


@router.get("/model-card")
async def model_card(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await modelcard_svc.build(session)
