"""Retraining from a snapshot: on the server's CPU (the label-fusion model is small) or as a Kaggle notebook. A finished run registers a
CHALLENGER with its metrics; only the gate (registry.promote) can make it champion. Nothing here scores data or changes a verdict.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline import fusion, kaggle_trigger as kg
from backend.app.pipeline.models import ModelVersion, TrainingJob, TrainingSnapshot
from backend.app.pipeline.registry import register


def job_dict(j: TrainingJob) -> Dict[str, Any]:
    return {"id": j.id, "created_at": j.created_at.isoformat() if j.created_at else None, "snapshot_id": j.snapshot_id, "target": j.target,
            "name": j.name, "slug": j.slug, "status": j.status, "error": j.error, "model_id": j.model_id,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


async def _register(session: AsyncSession, job: TrainingJob, snap: TrainingSnapshot, metrics: Dict[str, Any]) -> ModelVersion:
    n = (await session.execute(select(func.count()).select_from(ModelVersion).where(ModelVersion.name == job.name))).scalar_one()
    m = await register(session, job.name, f"s{snap.id}-{n + 1}", metrics, snapshot_id=snap.id, artifact_sha256=snap.sha256,
                       notes=f"trained {job.target} from snapshot {snap.id}; labels are one reviewer's judgements")
    job.model_id, job.status, job.finished_at = m.id, "complete", datetime.now(timezone.utc)
    await session.commit()
    return m


async def start(session: AsyncSession, snapshot_id: int, target: str, name: str = "label-fusion",
                creds: Optional[kg.Credentials] = None) -> TrainingJob:
    """``creds`` are the caller's own Kaggle credentials for this request only (never stored); without them the server's are used."""
    snap = await session.get(TrainingSnapshot, snapshot_id)
    if snap is None:
        raise LookupError("no such snapshot")
    if target not in ("local", "kaggle"):
        raise ValueError("target must be 'local' or 'kaggle'")
    account = kg.resolve(creds)
    if target == "kaggle" and account is None:
        raise PermissionError(kg.NO_CREDENTIALS)
    job = TrainingJob(snapshot_id=snapshot_id, target=target, name=name, status="running")
    session.add(job)
    await session.commit()
    if target == "local":
        try:
            result = await asyncio.to_thread(fusion.train, fusion.parse_snapshot(snap.content), fusion.BUDGET_PER_1000, fusion.MIN_FAULT, fusion.MIN_CLEAN, snap.sha256)
            await _register(session, job, snap, result)
        except fusion.NotEnoughLabels as e:
            job.status, job.error, job.finished_at = "failed", str(e), datetime.now(timezone.utc)
            await session.commit()
        return job
    job.slug = kg.slug_for(snapshot_id, job.id)
    try:
        job.slug = await asyncio.to_thread(kg.push, snap.content, snap.sha256, kg.slug_for(snapshot_id, job.id), account)
    except kg.KaggleError as e:
        job.status, job.error, job.finished_at = "failed", str(e), datetime.now(timezone.utc)
    await session.commit()
    return job


async def refresh(session: AsyncSession, job_id: int, creds: Optional[kg.Credentials] = None) -> TrainingJob:
    """Ask Kaggle about a running notebook; when it has finished, fetch its result and register the challenger. The credentials (the
    caller's, else the server's) must belong to the account that owns the notebook: a different account is refused, never used."""
    job = await session.get(TrainingJob, job_id)
    if job is None:
        raise LookupError("no such training job")
    if job.target != "kaggle" or job.status != "running" or not job.slug:
        return job
    account = kg.resolve(creds)
    if account is None:
        raise PermissionError(kg.NO_CREDENTIALS)
    if not kg.same_account(job.slug, account):
        raise PermissionError(f"this notebook belongs to the Kaggle account '{kg.owner_of(job.slug)}', but the credentials supplied are for "
                              f"'{account.username}'; supply the credentials of '{kg.owner_of(job.slug)}' to check it")
    try:
        st = await asyncio.to_thread(kg.status, job.slug, account)
        if st == "failed":
            job.status, job.error, job.finished_at = "failed", "the Kaggle notebook failed or was cancelled; see it on kaggle.com", datetime.now(timezone.utc)
        elif st == "complete":
            res = await asyncio.to_thread(kg.fetch_result, job.slug, account)
            snap = await session.get(TrainingSnapshot, job.snapshot_id)
            if res.get("ok") and snap is not None:
                await _register(session, job, snap, res["metrics"])
                return job
            job.status, job.error, job.finished_at = "failed", str(res.get("error") or "no metrics in the result"), datetime.now(timezone.utc)
    except kg.KaggleError as e:
        job.error = str(e)                      # a failed check does not end the job: try again later
    await session.commit()
    return job
