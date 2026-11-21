"""Import step: bring bulk station data in from a user-supplied Amazon S3 link or a Kaggle dataset.

GET  /api/pipeline/import/sources   the providers, link forms, formats and limits (for the Import page)
POST /api/pipeline/import           fetch the link (admin session), start one ingest job per file; progress is read from /api/pipeline/jobs

The fetch happens before the 202 (so a bad link, a refusal or an unknown format is answered at once); reading the rows into the raw store runs
in the background. Credentials come in per-request headers only and are never stored, logged or echoed. Public Kaggle datasets need no token;
a private one answers 428 and the page asks for a token (header X-Kaggle-Token, this request only). UNTESTED against live S3; the public Kaggle
path was run once against a real public dataset (2026-11-20).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api import pipeline as pipeline_api
from backend.app.api.settings import require_admin
from backend.app.db.database import get_db
from backend.app.pipeline import aws_trigger as aws_svc
from backend.app.pipeline import importers
from backend.app.pipeline import jobs as jobs_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pipeline", tags=["pipeline-import"])


@router.get("/import/sources")
async def import_sources() -> Dict[str, Any]:
    return {
        "providers": [
            {"id": "aws", "label": "Amazon S3 (AWS)",
             "accepts": ["s3://bucket/key", "https://bucket.s3.<region>.amazonaws.com/key", "https://s3.<region>.amazonaws.com/bucket/key",
                         "a presigned https URL on amazonaws.com"],
             "credentials": "optional: only for private buckets",
             "examples": ["s3://example-bucket/rain/tripura.csv", "https://example-bucket.s3.eu-west-1.amazonaws.com/rain/tripura.csv"]},
            {"id": "kaggle", "label": "Kaggle",
             "accepts": ["owner/dataset-slug", "a kaggle.com dataset link", "kernel:owner/notebook-slug (output)"],
             "credentials": "none for public datasets; an API token only for private ones",
             "examples": ["example-owner/example-rainfall-dataset", "kernel:example-owner/example-notebook"]},
        ],
        "formats": [{"id": "auto", "label": "Detect from the file"}, {"id": "cwc", "label": "CWC hourly CSV"}],
        "limits": {"max_mb": jobs_svc.MAX_BYTES // (1024 * 1024), "max_files": importers.MAX_FILES},
    }


class ImportBody(BaseModel):
    provider: Literal["aws", "kaggle"]
    url: str = ""                  # length and form are checked by the parser, which never echoes the link (a pydantic 422 would)
    format: Literal["auto", "cwc"] = "auto"


def aws_import_request(x_aws_access_key_id: Optional[str] = Header(None), x_aws_secret_access_key: Optional[str] = Header(None),
                       x_aws_session_token: Optional[str] = Header(None), x_aws_region: Optional[str] = Header(None)) -> Optional[aws_svc.Request]:
    """The caller's AWS credentials for this request only (never stored or echoed); None means anonymous access."""
    try:
        return aws_svc.from_request(x_aws_access_key_id, x_aws_secret_access_key, x_aws_session_token, x_aws_region, None)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


def kaggle_token(x_kaggle_token: Optional[str] = Header(None)) -> Optional[str]:
    """The caller's Kaggle API token for this request only (never stored, logged or echoed); None for a public dataset."""
    try:
        return importers.clean_kaggle_token(x_kaggle_token)
    except importers.ImportRefused as e:
        raise HTTPException(e.status, str(e))


@router.post("/import", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
async def start_import(body: ImportBody, background: BackgroundTasks, session: AsyncSession = Depends(get_db),
                       aws_req: Optional[aws_svc.Request] = Depends(aws_import_request),
                       kg_token: Optional[str] = Depends(kaggle_token)) -> Dict[str, Any]:
    try:
        if body.provider == "aws":
            link = importers.parse_aws_link(body.url)
            origin = link.origin
            fetched = await importers.fetch_aws(link, aws_req)
        else:
            ref = importers.parse_kaggle_ref(body.url)
            origin = ref.origin
            fetched = await importers.fetch_kaggle(ref, kg_token)
    except importers.ImportRefused as e:
        raise HTTPException(e.status, str(e))

    handed: set = set()
    paths: List[str] = [f.path for f in fetched]
    jobs: List[Any] = []
    skipped: List[str] = []
    try:
        ready = []
        for f in fetched:
            try:
                ready.append(importers.prepare(f, body.format))
                paths.append(ready[-1][0].path)
            except importers.ImportRefused as e:
                if len(fetched) == 1:
                    raise HTTPException(e.status, str(e))
                skipped.append(f.name)
        if not ready:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, importers.UNKNOWN_FORMAT)
        pipeline_api._obs_count_cache["at"] = 0.0
        for f, fmt in ready:
            extra = {"import": {"provider": body.provider, "origin": origin, "requested_format": body.format},
                     "format_detection": "sniffed from the file content" if body.format == "auto" else "given by the caller"}
            job = await jobs_svc.create_job(session, fmt, f.name, f.sha256, f.size, extra)
            jobs.append(job)
            background.add_task(jobs_svc.run_job, job.id, f.path)
            handed.add(f.path)
    finally:
        for p in set(paths) - handed:                       # anything not handed to a job: nobody else will remove it
            Path(p).unlink(missing_ok=True)
    logger.info("import accepted: provider=%s jobs=%d skipped=%d", body.provider, len(jobs), len(skipped))      # no link, no credentials
    return {**jobs_svc.job_dict(jobs[0]), "provider": body.provider, "origin": origin, "job_ids": [j.id for j in jobs], "skipped_files": skipped}
