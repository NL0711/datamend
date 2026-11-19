"""Ingest jobs: a file is accepted at once (a job id comes back), then read in chunks and stored in the raw table.

The job table is the queue (one process, no new infrastructure). A job records what it read, stored, skipped as already stored and could not
store, with the first problem rows listed, and every assumption made about the source. A file-level problem fails the job (the file is
rejected); a row-level problem is counted and listed, and the other rows still go in.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.database import async_session_factory
from backend.app.pipeline import cwc
from backend.app.pipeline.models import IngestJob, Observation
from backend.app.pipeline.store import insert_observations, upsert_stations

logger = logging.getLogger(__name__)

SOURCES = {"cwc": cwc}
MAX_BYTES = 300 * 1024 * 1024
CHUNK_ROWS = 2000
MAX_BAD_SAMPLES = 50
UPLOAD_DIR = Path(os.environ.get("PIPELINE_UPLOAD_DIR") or (Path(tempfile.gettempdir()) / "datamend_pipeline_uploads"))


class UploadTooLarge(ValueError):
    pass


async def save_upload(upload: UploadFile) -> Dict[str, Any]:
    """Stream an upload to disk (never all in memory), hashing it and refusing anything over MAX_BYTES."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=UPLOAD_DIR, suffix=".csv")
    sha, size = hashlib.sha256(), 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                block = await upload.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > MAX_BYTES:
                    raise UploadTooLarge(f"file is larger than {MAX_BYTES // (1024 * 1024)} MB")
                sha.update(block)
                out.write(block)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    return {"path": tmp, "sha256": sha.hexdigest(), "size": size}


async def create_job(session: AsyncSession, source: str, filename: str, sha: str, size: int) -> IngestJob:
    mod = SOURCES[source]
    job = IngestJob(source=source, filename=(filename or "upload")[:255], sha256=sha, size_bytes=size, status="queued", assumptions=dict(mod.ASSUMPTIONS))
    session.add(job)
    await session.commit()
    return job


def job_dict(j: IngestJob) -> Dict[str, Any]:
    return {"id": j.id, "created_at": j.created_at.isoformat() if j.created_at else None, "source": j.source, "filename": j.filename, "sha256": j.sha256,
            "size_bytes": j.size_bytes, "status": j.status, "rows_read": j.rows_read, "rows_inserted": j.rows_inserted, "rows_duplicate": j.rows_duplicate,
            "rows_bad": j.rows_bad, "stations": j.stations, "bad_samples": j.bad_samples, "assumptions": j.assumptions, "error": j.error,
            "started_at": j.started_at.isoformat() if j.started_at else None, "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "run_id": j.run_id}


async def fail_interrupted_jobs() -> int:
    """At start-up: a job still queued or running was cut off by a restart (its file is gone with the old process). Mark it failed so it is
    never shown running forever; the owner uploads the file again (re-ingest is safe, rows already stored are skipped)."""
    async with async_session_factory() as session:
        jobs = (await session.execute(select(IngestJob).where(IngestJob.status.in_(("queued", "running"))))).scalars().all()
        for j in jobs:
            j.status, j.error, j.finished_at = "failed", "interrupted by a server restart; upload the file again (rows already stored are skipped)", datetime.now(timezone.utc)
        await session.commit()
        return len(jobs)


async def run_job(job_id: int, path: str) -> None:
    """Read the saved file and fill the raw store. Uses its own session (it runs after the request has returned). Never raises."""
    async with async_session_factory() as session:
        job = await session.get(IngestJob, job_id)
        if job is None:
            return
        job.status, job.started_at = "running", datetime.now(timezone.utc)
        await session.commit()
        mod = SOURCES[job.source]
        seen_stations: set = set()
        bad: List[Dict[str, Any]] = []
        n_read = n_bad = 0
        obs: List[Dict[str, Any]] = []
        stn: Dict[str, Dict[str, Any]] = {}
        try:
            async def flush() -> None:
                nonlocal obs, stn
                if stn:
                    await upsert_stations(session, list(stn.values()))
                if obs:
                    await insert_observations(session, obs)
                job.rows_read, job.rows_bad, job.stations = n_read, n_bad, len(seen_stations)
                job.bad_samples = bad[:MAX_BAD_SAMPLES]
                await session.commit()
                obs, stn = [], {}
                await asyncio.sleep(0)                       # let other requests in between chunks

            for row in mod.read_rows(path):
                n_read += 1
                if row.problem:
                    n_bad += 1
                    if len(bad) < MAX_BAD_SAMPLES:
                        bad.append({"row": row.row_number, "problem": row.problem})
                else:
                    seen_stations.add(row.station_key)
                    stn.setdefault(row.station_key, mod.station_record(row))
                    obs.append({"source": job.source, "station_key": row.station_key, "observed_at": row.observed_at,
                                "value_mm": row.value_mm, "job_id": job.id})
                if len(obs) >= CHUNK_ROWS:
                    await flush()
            await flush()
            stored = (await session.execute(select(func.count()).select_from(Observation).where(Observation.job_id == job.id))).scalar_one()
            job.rows_inserted = stored
            job.rows_duplicate = n_read - n_bad - stored
            job.status = "done"
        except Exception as exc:                              # a file-level problem (wrong format) or a storage error
            await session.rollback()
            job = await session.get(IngestJob, job_id)
            job.status, job.error = "failed", str(exc)[:500]
            job.rows_read, job.rows_bad, job.stations, job.bad_samples = n_read, n_bad, len(seen_stations), bad[:MAX_BAD_SAMPLES]
            logger.warning("ingest job %s failed: %s", job_id, exc)
        job.finished_at = datetime.now(timezone.utc)
        await session.commit()
    Path(path).unlink(missing_ok=True)
