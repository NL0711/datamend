"""REST endpoints of the rainfall validation platform (backend/app/validation). Routes only parse and delegate to services.

Read-only except creating a run (POST /runs). Evidence is loaded one row at a time; rows come in server-side pages of at most 50.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.database import get_db
from backend.app.validation import runs as svc
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
