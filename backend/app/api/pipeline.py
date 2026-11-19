"""HTTP surface of the ingest and feedback loop (backend/app/pipeline). Reading needs a signed-in session (the app-wide login gate);
anything that writes needs the admin session as well (require_admin). Services hold the logic; routes only translate.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.settings import require_admin
from backend.app.db.database import get_db
from backend.app.pipeline import audit as audit_svc
from backend.app.pipeline import jobs as jobs_svc
from backend.app.pipeline import kaggle_trigger as kaggle_svc
from backend.app.pipeline import lineage as lineage_svc
from backend.app.pipeline import training as train_svc
from backend.app.pipeline import proposals as prop_svc
from backend.app.pipeline import qc as qc_svc
from backend.app.pipeline import registry as reg_svc
from backend.app.pipeline import snapshot as snap_svc
from backend.app.pipeline.models import AuditItem, IngestJob, ModelVersion, Observation, PipelineStation, Proposal, TrainingJob, TrainingSnapshot
from backend.app.validation.runs import run_dict

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

NOT_IMPLEMENTED = [
    "retraining the RF25 STNet from labels (only the small label-fusion model is retrained, on the server's CPU or as a Kaggle notebook)",
    "scoring with a registered model on the server (needs RF25 grid neighbours; see the map ticket on station-to-cell mapping)",
    "the shadow run of a candidate beside the champion",
    "the LLM proposer and explainer (the narrator team's service; the rule-based baseline works without it)",
]


def _bad(e: Exception, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, str(e))


@router.get("/status")
async def pipeline_status(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    n_obs = (await session.execute(select(func.count()).select_from(Observation))).scalar_one()
    return {"observations": n_obs, "stations": (await session.execute(select(func.count()).select_from(PipelineStation))).scalar_one(),
            "jobs": (await session.execute(select(func.count()).select_from(IngestJob))).scalar_one(),
            "proposals_pending": (await session.execute(select(func.count()).select_from(Proposal).where(Proposal.status == "pending"))).scalar_one(),
            "snapshots": (await session.execute(select(func.count()).select_from(TrainingSnapshot))).scalar_one(),
            "champions": [reg_svc.model_dict(m) for m in (await session.execute(select(ModelVersion).where(ModelVersion.alias == "champion"))).scalars()],
            "sources": sorted(jobs_svc.SOURCES), "max_upload_mb": jobs_svc.MAX_BYTES // (1024 * 1024), "not_implemented": NOT_IMPLEMENTED}


# ------------------------------------------------------------------------------------------------ ingest
@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
async def ingest(background: BackgroundTasks, file: UploadFile = File(...), source: str = Form("cwc"), wait: bool = Form(False),
                 session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Accept a file and return a job at once; the file is read in chunks in the background (``wait`` runs it before returning, for small files)."""
    if source not in jobs_svc.SOURCES:
        raise _bad(ValueError(f"unknown source {source!r}; available: {sorted(jobs_svc.SOURCES)}"))
    try:
        saved = await jobs_svc.save_upload(file)
    except jobs_svc.UploadTooLarge as e:
        raise _bad(e, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    job = await jobs_svc.create_job(session, source, file.filename or "upload", saved["sha256"], saved["size"])
    if wait:
        await jobs_svc.run_job(job.id, saved["path"])
        await session.refresh(job)
    else:
        background.add_task(jobs_svc.run_job, job.id, saved["path"])
    return jobs_svc.job_dict(job)


@router.get("/jobs")
async def list_jobs(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = (await session.execute(select(IngestJob).order_by(IngestJob.id.desc()).limit(50))).scalars().all()
    return {"jobs": [jobs_svc.job_dict(j) for j in rows]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    j = await session.get(IngestJob, job_id)
    if j is None:
        raise HTTPException(404, "no such job")
    await session.refresh(j)
    return jobs_svc.job_dict(j)


class CheckBody(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None


@router.post("/jobs/{job_id}/check", dependencies=[Depends(require_admin)])
async def check_job(job_id: int, body: CheckBody = CheckBody(), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Roll the job's source up to rain-day totals and run the daily checks as one validation run (source 'pipeline')."""
    j = await session.get(IngestJob, job_id)
    if j is None:
        raise HTTPException(404, "no such job")
    if j.status != "done":
        raise _bad(ValueError(f"the job is {j.status}; check it when it is done"), status.HTTP_409_CONFLICT)
    try:
        run = await qc_svc.run_qc(session, j.source, j, body.start, body.end)
    except ValueError as e:
        raise _bad(e, status.HTTP_422_UNPROCESSABLE_ENTITY)
    return run_dict(run)


# ------------------------------------------------------------------------------------------------ proposals
class GenerateBody(BaseModel):
    generator: str = "baseline-rules"


@router.post("/runs/{run_id}/proposals", dependencies=[Depends(require_admin)])
async def generate_proposals(run_id: int, body: GenerateBody = GenerateBody(), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        made = await prop_svc.generate(session, run_id, body.generator)
    except ValueError as e:
        raise _bad(e)
    return {"created": len(made), "proposals": [prop_svc.proposal_dict(p) for p in made]}


@router.get("/proposals")
async def list_proposals(run_id: Optional[int] = None, status_: str = Query("pending", alias="status"), limit: int = 200,
                         session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    q = select(Proposal).order_by(Proposal.id).limit(max(1, min(limit, 500)))
    if run_id is not None:
        q = q.where(Proposal.run_id == run_id)
    if status_ != "all":
        q = q.where(Proposal.status == status_)
    return {"proposals": [prop_svc.proposal_dict(p) for p in (await session.execute(q)).scalars()],
            "note": "Generated suggestions. They change nothing until a reviewer accepts one."}


class DecideBody(BaseModel):
    accept: bool
    reviewer: Optional[str] = Field(None, max_length=60)
    note: Optional[str] = Field(None, max_length=1000)
    corrected_mm: Optional[float] = None


@router.post("/proposals/{proposal_id}/decide", dependencies=[Depends(require_admin)])
async def decide_proposal(proposal_id: int, body: DecideBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        p = await prop_svc.decide(session, proposal_id, body.accept, body.reviewer, body.note, body.corrected_mm)
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        raise _bad(e, status.HTTP_409_CONFLICT)
    return prop_svc.proposal_dict(p)


# ------------------------------------------------------------------------------------------------ audit sample
class DrawBody(BaseModel):
    n: int = Field(30, ge=1, le=audit_svc.MAX_SAMPLE)
    seed: Optional[int] = None


@router.post("/runs/{run_id}/audit", dependencies=[Depends(require_admin)])
async def draw_audit(run_id: int, body: DrawBody = DrawBody(), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        items = await audit_svc.draw(session, run_id, body.n, body.seed)
    except ValueError as e:
        raise _bad(e)
    return {"drawn": len(items), "items": [audit_svc.audit_dict(a) for a in items]}


@router.get("/runs/{run_id}/audit")
async def list_audit(run_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = (await session.execute(select(AuditItem).where(AuditItem.run_id == run_id).order_by(AuditItem.id))).scalars().all()
    return {"items": [audit_svc.audit_dict(a) for a in rows], "estimate": await audit_svc.estimate(session, run_id)}


class AuditDecideBody(BaseModel):
    decision: str
    reviewer: Optional[str] = Field(None, max_length=60)
    note: Optional[str] = Field(None, max_length=1000)


@router.post("/audit/{item_id}/decide", dependencies=[Depends(require_admin)])
async def decide_audit(item_id: int, body: AuditDecideBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        a = await audit_svc.decide(session, item_id, body.decision, body.reviewer, body.note)
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        raise _bad(e)
    return audit_svc.audit_dict(a)


# ------------------------------------------------------------------------------------------------ snapshots
class SnapshotBody(BaseModel):
    cut_day: date
    exclude_years: Optional[List[int]] = None
    allow_test_years: bool = False


@router.post("/snapshots", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def make_snapshot(body: SnapshotBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    snap = await snap_svc.build(session, body.cut_day, body.exclude_years, body.allow_test_years)
    return snap_svc.snapshot_dict(snap)


@router.get("/snapshots")
async def list_snapshots(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = (await session.execute(select(TrainingSnapshot).order_by(TrainingSnapshot.id.desc()).limit(50))).scalars().all()
    return {"snapshots": [snap_svc.snapshot_dict(s) for s in rows]}


@router.get("/snapshots/{snapshot_id}/data.jsonl")
async def snapshot_data(snapshot_id: int, session: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    s = await session.get(TrainingSnapshot, snapshot_id)
    if s is None:
        raise HTTPException(404, "no such snapshot")
    return PlainTextResponse(s.content, media_type="application/x-ndjson", headers={"X-Snapshot-Sha256": s.sha256})


# ------------------------------------------------------------------------------------------------ model registry
class RegisterBody(BaseModel):
    name: str = Field(max_length=64)
    version: str = Field(max_length=32)
    metrics: Dict[str, Any]
    snapshot_id: Optional[int] = None
    artifact_sha256: Optional[str] = Field(None, max_length=64)
    artifact_uri: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=1000)


@router.post("/models", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def register_model(body: RegisterBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    if body.snapshot_id is not None and await session.get(TrainingSnapshot, body.snapshot_id) is None:
        raise _bad(ValueError("no such snapshot"), status.HTTP_404_NOT_FOUND)
    m = await reg_svc.register(session, body.name, body.version, body.metrics, body.snapshot_id, body.artifact_sha256, body.artifact_uri, body.notes)
    return reg_svc.model_dict(m)


@router.get("/models")
async def list_models(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = (await session.execute(select(ModelVersion).order_by(ModelVersion.id.desc()).limit(100))).scalars().all()
    return {"models": [reg_svc.model_dict(m) for m in rows], "not_implemented": NOT_IMPLEMENTED}


@router.post("/models/{model_id}/promote", dependencies=[Depends(require_admin)])
async def promote_model(model_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        m = await reg_svc.promote(session, model_id)
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        raise _bad(e, status.HTTP_409_CONFLICT)
    return reg_svc.model_dict(m)


# ------------------------------------------------------------------------------------------------ retraining and lineage
class TrainBody(BaseModel):
    snapshot_id: int
    target: str = "local"                        # local (server CPU) | kaggle (a private notebook)
    name: str = Field("label-fusion", max_length=64)


def kaggle_creds(x_kaggle_username: Optional[str] = Header(None), x_kaggle_key: Optional[str] = Header(None)) -> Optional[kaggle_svc.Credentials]:
    """The caller's own Kaggle account from the two headers, for this request only (never stored or echoed); None means use the server's."""
    try:
        return kaggle_svc.from_request(x_kaggle_username, x_kaggle_key)
    except ValueError as e:
        raise _bad(e)


@router.post("/train", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
async def train(body: TrainBody, session: AsyncSession = Depends(get_db), creds: Optional[kaggle_svc.Credentials] = Depends(kaggle_creds)) -> Dict[str, Any]:
    """Retrain the label-fusion model from a snapshot. A finished run registers a challenger; only the gate can promote it. A Kaggle run uses
    the caller's own Kaggle account when the X-Kaggle-Username and X-Kaggle-Key headers are sent, otherwise the server's."""
    try:
        job = await train_svc.start(session, body.snapshot_id, body.target, body.name, creds)
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except PermissionError as e:
        raise _bad(e, status.HTTP_409_CONFLICT)
    except ValueError as e:
        raise _bad(e)
    return train_svc.job_dict(job)


@router.get("/train/jobs")
async def train_jobs(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = (await session.execute(select(TrainingJob).order_by(TrainingJob.id.desc()).limit(50))).scalars().all()
    return {"jobs": [train_svc.job_dict(j) for j in rows], "kaggle_configured": kaggle_svc.configured(), "byo_supported": True}


@router.post("/train/jobs/{job_id}/refresh", dependencies=[Depends(require_admin)])
async def refresh_train_job(job_id: int, session: AsyncSession = Depends(get_db), creds: Optional[kaggle_svc.Credentials] = Depends(kaggle_creds)) -> Dict[str, Any]:
    try:
        job = await train_svc.refresh(session, job_id, creds)
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except PermissionError as e:
        raise _bad(e, status.HTTP_409_CONFLICT)
    return train_svc.job_dict(job)


@router.get("/lineage")
async def get_lineage(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await lineage_svc.build(session)


@router.post("/models/{name}/rollback", dependencies=[Depends(require_admin)])
async def rollback_model(name: str, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        m = await reg_svc.rollback(session, name)
    except ValueError as e:
        raise _bad(e, status.HTTP_409_CONFLICT)
    return reg_svc.model_dict(m)
