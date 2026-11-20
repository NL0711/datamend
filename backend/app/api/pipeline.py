"""HTTP surface of the ingest and feedback loop (backend/app/pipeline). Reading needs a signed-in session (the app-wide login gate);
anything that writes needs the admin session as well (require_admin). Services hold the logic; routes only translate.
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.settings import require_admin
from backend.app.db.database import get_db
from backend.app.pipeline import audit as audit_svc
from backend.app.pipeline import aws_trigger as aws_svc
from backend.app.pipeline import jobs as jobs_svc
from backend.app.pipeline import kaggle_trigger as kaggle_svc
from backend.app.pipeline import lineage as lineage_svc
from backend.app.pipeline import training as train_svc
from backend.app.pipeline import proposals as prop_svc
from backend.app.pipeline import qc as qc_svc
from backend.app.pipeline import registry as reg_svc
from backend.app.pipeline import scoring as scoring_svc
from backend.app.pipeline import snapshot as snap_svc
from backend.app.pipeline.models import AuditItem, IngestJob, ModelVersion, Observation, PipelineStation, Proposal, TrainingJob, TrainingSnapshot
from backend.app.validation import narrate
from backend.app.validation.runs import run_dict

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

NOT_IMPLEMENTED = [
    "retraining the RF25 STNet from labels (only the small label-fusion model is retrained, on the server's CPU or as a Kaggle notebook)",
    "scoring with the RF25 STNet on the server (needs RF25 grid neighbours; see the map ticket on station-to-cell mapping); only the label-fusion model scores here",
    "the AI team's MCP narrator (the interim Gemini layer works when GEMINI_API_KEY is set; the rule-based baseline works without either)",
]


def _bad(e: Exception, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, str(e))


OBS_COUNT_TTL = 30.0
_obs_count_cache: Dict[str, Any] = {"at": 0.0, "n": 0, "bind": None}


async def _observation_count(session: AsyncSession) -> int:
    """count(*) over the whole raw table is expensive on millions of rows: refresh it at most every 30 seconds (the response says it is cached)."""
    now = time.monotonic()
    bind = id(session.bind) if session.bind is not None else None
    if _obs_count_cache["at"] == 0.0 or _obs_count_cache["bind"] != bind or now - _obs_count_cache["at"] > OBS_COUNT_TTL:
        _obs_count_cache.update(n=(await session.execute(select(func.count()).select_from(Observation))).scalar_one(), at=now, bind=bind)
    return int(_obs_count_cache["n"])


@router.get("/status")
async def pipeline_status(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    n_obs = await _observation_count(session)
    return {"observations": n_obs, "observations_note": f"cached for up to {int(OBS_COUNT_TTL)} seconds","stations": (await session.execute(select(func.count()).select_from(PipelineStation))).scalar_one(),
            "jobs": (await session.execute(select(func.count()).select_from(IngestJob))).scalar_one(),
            "proposals_pending": (await session.execute(select(func.count()).select_from(Proposal).where(Proposal.status == "pending"))).scalar_one(),
            "snapshots": (await session.execute(select(func.count()).select_from(TrainingSnapshot))).scalar_one(),
            "champions": [reg_svc.model_dict(m) for m in (await session.execute(select(ModelVersion).where(ModelVersion.alias == "champion"))).scalars()],
            "sources": sorted(jobs_svc.SOURCES), "max_upload_mb": jobs_svc.MAX_BYTES // (1024 * 1024), "not_implemented": NOT_IMPLEMENTED}


# ------------------------------------------------------------------------------------------------ ingest
@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
async def ingest(background: BackgroundTasks, file: UploadFile = File(...), source: str = Form("cwc"), wait: bool = Form(False),
                 session: AsyncSession = Depends(get_db), content_length: Optional[int] = Header(None)) -> Dict[str, Any]:
    """Accept a file and return a job at once; the file is read in chunks in the background (``wait`` runs it before returning, for small files)."""
    if source not in jobs_svc.SOURCES:
        raise _bad(ValueError(f"unknown source {source!r}; available: {sorted(jobs_svc.SOURCES)}"))
    if content_length is not None and content_length > jobs_svc.MAX_BYTES:         # refuse before reading a byte of it
        raise _bad(jobs_svc.UploadTooLarge(f"file is larger than {jobs_svc.MAX_BYTES // (1024 * 1024)} MB"), status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    try:
        saved = await jobs_svc.save_upload(file)
    except jobs_svc.UploadTooLarge as e:
        raise _bad(e, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    handed_over = False
    _obs_count_cache["at"] = 0.0                        # a new file is about to change the count
    try:
        job = await jobs_svc.create_job(session, source, file.filename or "upload", saved["sha256"], saved["size"])
        if wait:
            handed_over = True                          # run_job removes the file itself
            await jobs_svc.run_job(job.id, saved["path"])
            _obs_count_cache["at"] = 0.0
            await session.refresh(job)
        else:
            background.add_task(jobs_svc.run_job, job.id, saved["path"])
            handed_over = True
    finally:
        if not handed_over:                             # create_job failed: nobody else will remove the saved upload
            Path(saved["path"]).unlink(missing_ok=True)
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
async def generate_proposals(run_id: int, body: GenerateBody = GenerateBody(), session: AsyncSession = Depends(get_db),
                             llm=Depends(narrate.get_narrator)) -> Dict[str, Any]:
    """generator 'baseline-rules' (default) or 'ai' (the connected LLM proposes a reviewer label per flagged row)."""
    if body.generator == "ai":
        try:
            res = await prop_svc.generate_llm(session, run_id, llm)
        except ValueError as e:
            raise _bad(e, status.HTTP_503_SERVICE_UNAVAILABLE if llm is None else status.HTTP_502_BAD_GATEWAY)
        return {"created": len(res["made"]), "skipped_over_limit": res["skipped"], "stopped": res["stopped"],
                "proposals": [prop_svc.proposal_dict(p) for p in res["made"]]}
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
    try:
        snap = await snap_svc.build(session, body.cut_day, body.exclude_years, body.allow_test_years)
    except ValueError as e:
        raise _bad(e)
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
async def promote_model(model_id: int, require_shadow: bool = Query(False), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Run the promotion gate. With require_shadow=true the challenger's newest shadow run must also pass (none yet: it stays a challenger)."""
    try:
        m = await reg_svc.promote(session, model_id, require_shadow)
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        raise _bad(e, status.HTTP_409_CONFLICT)
    return reg_svc.model_dict(m)


# ------------------------------------------------------------------------------------------------ scoring with a registered model, shadow run
class ScoreBody(BaseModel):
    model_id: int


@router.post("/runs/{run_id}/score", dependencies=[Depends(require_admin)])
async def score_run(run_id: int, body: ScoreBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Score a pipeline run with a registered label-fusion model. Stores the scores apart; verdicts and rule scores are unchanged."""
    try:
        return await scoring_svc.score_run(session, run_id, body.model_id)
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except scoring_svc.CannotScore as e:
        raise _bad(e, status.HTTP_422_UNPROCESSABLE_ENTITY)


@router.get("/runs/{run_id}/scores")
async def run_scores(run_id: int, model_id: Optional[int] = None, flagged_only: bool = False, limit: int = 500, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return {"scores": await scoring_svc.scores_for_run(session, run_id, model_id, flagged_only, limit),
            "note": "a model's own numbers, stored apart from the verdict; never a probability of a fault and never ground truth"}


@router.post("/runs/{run_id}/shadow", dependencies=[Depends(require_admin)])
async def shadow_run(run_id: int, body: ScoreBody, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Score a run with the champion and a challenger side by side and report both on the rows a reviewer labelled. model_id is the challenger."""
    try:
        return scoring_svc.shadow_dict(await scoring_svc.shadow(session, run_id, body.model_id))
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except scoring_svc.CannotScore as e:
        raise _bad(e, status.HTTP_422_UNPROCESSABLE_ENTITY)


@router.get("/models/{model_id}/shadow")
async def model_shadow(model_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    sh = await scoring_svc.latest_shadow(session, model_id)
    return {"shadow": scoring_svc.shadow_dict(sh) if sh else None}


# ------------------------------------------------------------------------------------------------ retraining and lineage
class TrainBody(BaseModel):
    snapshot_id: int
    target: str = "local"                        # local (server CPU) | kaggle (a private notebook) | aws (one short-lived EC2 instance in the caller's account)
    name: str = Field("label-fusion", max_length=64)
    instance_type: str = Field(aws_svc.DEFAULT_INSTANCE_TYPE, max_length=32)       # aws only; checked against an allowlist
    max_minutes: int = aws_svc.DEFAULT_MINUTES                                    # aws only; the hard time cap, 1 to 120
    spot: bool = False                                                            # aws only


def kaggle_creds(x_kaggle_username: Optional[str] = Header(None), x_kaggle_key: Optional[str] = Header(None)) -> Optional[kaggle_svc.Credentials]:
    """The caller's own Kaggle account from the two headers, for this request only (never stored or echoed); None means use the server's."""
    try:
        return kaggle_svc.from_request(x_kaggle_username, x_kaggle_key)
    except ValueError as e:
        raise _bad(e)


def aws_request(x_aws_access_key_id: Optional[str] = Header(None), x_aws_secret_access_key: Optional[str] = Header(None),
                x_aws_session_token: Optional[str] = Header(None), x_aws_region: Optional[str] = Header(None),
                x_aws_bucket: Optional[str] = Header(None)) -> Optional[aws_svc.Request]:
    """The caller's own AWS account, region and bucket from the headers, for this request only (never stored or echoed); None means use the server's."""
    try:
        return aws_svc.from_request(x_aws_access_key_id, x_aws_secret_access_key, x_aws_session_token, x_aws_region, x_aws_bucket)
    except ValueError as e:
        raise _bad(e)


@router.post("/train", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
async def train(body: TrainBody, session: AsyncSession = Depends(get_db), creds: Optional[kaggle_svc.Credentials] = Depends(kaggle_creds),
                aws_req: Optional[aws_svc.Request] = Depends(aws_request)) -> Dict[str, Any]:
    """Retrain the label-fusion model from a snapshot. A finished run registers a challenger; only the gate can promote it. A Kaggle run uses
    the caller's own Kaggle account when the X-Kaggle-Username and X-Kaggle-Key headers are sent, otherwise the server's. An AWS run starts one
    short-lived EC2 instance in the caller's AWS account (the X-Aws-* headers, otherwise the server's); AWS bills the account owner."""
    try:
        job = await train_svc.start(session, body.snapshot_id, body.target, body.name, creds, aws_req, (body.instance_type, body.max_minutes, body.spot))
    except LookupError as e:
        raise _bad(e, status.HTTP_404_NOT_FOUND)
    except PermissionError as e:
        raise _bad(e, status.HTTP_409_CONFLICT)
    except ValueError as e:
        raise _bad(e)
    out = train_svc.job_dict(job)
    if body.target == "aws":
        out.update(instance_type=body.instance_type, max_minutes=body.max_minutes, spot=body.spot)
        if aws_svc.ALLOWED_INSTANCE_TYPES.get(body.instance_type):
            out["gpu_note"] = aws_svc.GPU_NOTE
    return out


@router.get("/train/jobs")
async def train_jobs(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = (await session.execute(select(TrainingJob).order_by(TrainingJob.id.desc()).limit(50))).scalars().all()
    return {"jobs": [train_svc.job_dict(j) for j in rows], "kaggle_configured": kaggle_svc.configured(), "byo_supported": True,
            "aws_supported": True, "aws_configured": aws_svc.configured()}


@router.post("/train/jobs/{job_id}/refresh", dependencies=[Depends(require_admin)])
async def refresh_train_job(job_id: int, session: AsyncSession = Depends(get_db), creds: Optional[kaggle_svc.Credentials] = Depends(kaggle_creds),
                            aws_req: Optional[aws_svc.Request] = Depends(aws_request)) -> Dict[str, Any]:
    try:
        job = await train_svc.refresh(session, job_id, creds, aws_req)
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
