"""REST endpoints of the rainfall validation platform (backend/app/validation). Routes only parse and delegate to services.

Read-only except creating a run (POST /runs). Evidence is loaded one row at a time; rows come in server-side pages of at most 50.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.database import get_db
from backend.app.validation import narrate
from backend.app.validation import runs as svc
from backend.app.validation.explain import NarratorRateLimited, NarratorUnavailable
from backend.app.validation.ingest import MAX_BYTES, InputRejected, UploadOptions

router = APIRouter(prefix="/api/validation", tags=["validation"])


async def _run_or_404(session: AsyncSession, run_id: int):
    run = await svc.get_run(session, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"run {run_id} not found (demo storage resets on restart)")
    return run


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    file: UploadFile = File(...),
    profile: str = Form(...),
    accumulation_mode: Optional[str] = Form(None),
    timezone: Optional[str] = Form(None),
    interval_minutes: Optional[float] = Form(None),
    synthetic: bool = Form(False),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    name = file.filename or "upload"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("csv", "json"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unsupported file type .{ext}: use .csv or .json (parquet is NOT IMPLEMENTED)")
    content = await file.read(MAX_BYTES + 1)
    opts = UploadOptions(profile=profile, fmt=ext, accumulation_mode=accumulation_mode or None, timezone=timezone or None,
                         interval_minutes=interval_minutes)
    try:
        run = await svc.run_upload(session, content, name, opts, synthetic=synthetic)
    except InputRejected as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"rejected": True, "reason": str(e), "run_id": getattr(e, "run_id", None)})
    return svc.run_dict(run, full=True)


@router.get("/runs")
async def list_runs(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return {"storage": svc.STORAGE_LABEL, "cap": svc.RUN_CAP, "runs": [svc.run_dict(r) for r in await svc.list_runs(session)]}


@router.get("/runs/{run_id}")
async def get_run(run_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return svc.run_dict(await _run_or_404(session, run_id), full=True)


@router.get("/runs/{run_id}/rows")
async def get_rows(run_id: int, page: int = Query(1, ge=1), page_size: int = Query(svc.PAGE_SIZE, ge=1, le=svc.PAGE_SIZE),
                   verdict: Optional[str] = Query(None, pattern="^(OK|SUSPECT|UNCERTAIN|NO_DATA)$"), check: Optional[str] = None,
                   station: Optional[str] = None, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    return await svc.rows_page(session, run_id, page, page_size, verdict, check, station)


@router.get("/runs/{run_id}/rows/{result_id}")
async def get_row_evidence(run_id: int, result_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    ev = await svc.row_evidence(session, run_id, result_id)
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"row {result_id} not in run {run_id}")
    return ev


async def _row_or_404(session: AsyncSession, run_id: int, result_id: int):
    row = await svc.get_row(session, run_id, result_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"row {result_id} not in run {run_id}")
    return row


@router.get("/narrator")
async def narrator_status(narrator=Depends(narrate.get_narrator)) -> Dict[str, Any]:
    """Whether an AI narrator is configured. The URL is set in the environment only; this never reveals the token."""
    return narrate.narrator_status(narrator)


@router.get("/runs/{run_id}/rows/{result_id}/evidence")
async def get_evidence_v1(run_id: int, result_id: int, check: Optional[str] = None, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """GET-only evidence-v1 payloads (docs/contracts/evidence-v1.schema.json), one per fired check, each at most 64 KB."""
    run = await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    return {"schema": "evidence-v1", "evidence": await narrate.evidence_for_row(session, run, row, check)}


@router.get("/runs/{run_id}/rows/{result_id}/explanations")
async def get_explanations(run_id: int, result_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    items = await narrate.list_explanations(session, run_id, row.row_ref, kind="explain")
    return {"explanations": [narrate.explanation_dict(e) for e in items]}


class ExplainRequest(BaseModel):
    generator: Literal["baseline", "narrator"] = "baseline"
    check: Optional[str] = Field(None, max_length=48)


@router.post("/runs/{run_id}/rows/{result_id}/explain", status_code=status.HTTP_201_CREATED)
async def explain(run_id: int, result_id: int, body: ExplainRequest, session: AsyncSession = Depends(get_db),
                  narrator=Depends(narrate.get_narrator)) -> Dict[str, Any]:
    """Explain the fired check(s) of a row and store the reply (the only write besides creating a run). The baseline always works;
    the narrator answers 503 'AI narrator not connected' when none is configured."""
    run = await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    if body.generator == "narrator":
        if narrator is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI narrator not connected")
        explainer = narrator
    else:
        explainer = narrate.BASELINE
    try:
        made = await narrate.explain_row(session, run, row, explainer, body.check)
    except NarratorRateLimited as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e))
    except NarratorUnavailable as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY if body.generator == "narrator" else status.HTTP_404_NOT_FOUND, str(e))
    return {"explanations": [narrate.explanation_dict(e) for e in made]}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=narrate.MAX_QUESTION_CHARS)
    row_id: Optional[int] = None

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("the question is empty")
        return v


@router.get("/runs/{run_id}/chat")
async def get_chat(run_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    return {"messages": [narrate.explanation_dict(e) for e in await narrate.list_explanations(session, run_id, kind="chat")]}


@router.post("/runs/{run_id}/chat", status_code=status.HTTP_201_CREATED)
async def chat(run_id: int, body: ChatRequest, session: AsyncSession = Depends(get_db), narrator=Depends(narrate.get_narrator)) -> Dict[str, Any]:
    """Ask the AI narrator a question about the run or a selected row. With no narrator configured this answers 503 and nothing is
    invented; the narrator's reply is stored as generated text and cannot change any verdict, score or evidence."""
    run = await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, body.row_id) if body.row_id is not None else None
    if narrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI narrator not connected")
    try:
        saved = await narrate.chat_turn(session, run, body.message, narrator, row)
    except NarratorRateLimited as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e))
    except NarratorUnavailable as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return narrate.explanation_dict(saved)


@router.get("/runs/{run_id}/series")
async def get_series(run_id: int, station: str, max_points: int = Query(1500, ge=50, le=5000), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    return await svc.series(session, run_id, station, max_points)


@router.get("/runs/{run_id}/export.json")
async def export_json(run_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    run = await _run_or_404(session, run_id)
    body = json.dumps(await svc.export_json(session, run), default=str)
    return Response(body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="validation-run-{run_id}.json"'})


@router.get("/runs/{run_id}/export.csv")
async def export_csv(run_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    run = await _run_or_404(session, run_id)
    return Response(await svc.export_csv(session, run), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="validation-run-{run_id}.csv"'})
