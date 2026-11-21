"""Import step: bring data in from a user-supplied Amazon S3 link or a Kaggle dataset.

GET  /api/pipeline/import/sources   the providers, link forms, formats, optional declarations and limits (for the Import page)
POST /api/pipeline/import           fetch the link (admin session), then per file: a CWC or NOAA ISD file starts an ingest job (progress is read from
                                    /api/pipeline/jobs); a reading or daily CSV/JSON goes through the same intake as an upload and gives a validation run

The fetch and the format check happen before the answer (so a bad link, a refusal or an unknown format is answered at once); reading CWC and ISD rows
into the raw store runs in the background. Credentials come in per-request headers only and are never stored, logged or echoed. Public Kaggle datasets
need no token; a private one answers 428 and the page asks for a token (header X-Kaggle-Token, this request only). The public S3 path was run once
against a real NOAA ISD file (2026-11-21); the public Kaggle path once against a real public dataset (2026-11-20).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api import pipeline as pipeline_api
from backend.app.api.settings import require_admin
from backend.app.db.database import get_db
from backend.app.pipeline import aws_trigger as aws_svc
from backend.app.pipeline import importers
from backend.app.pipeline import jobs as jobs_svc
from backend.app.validation import runs as runs_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pipeline", tags=["pipeline-import"])

FORMATS = [{"id": "auto", "label": "Detect from the file"},
           {"id": "cwc", "label": "CWC hourly CSV"},
           {"id": "isd", "label": "NOAA ISD hourly (fixed-width or CSV, plain or .gz): file format only"},
           {"id": "reading", "label": "Reading CSV or JSON (timestamp, station_id, accumulation and/or intensity)"},
           {"id": "daily", "label": "Daily CSV or JSON (day, station_id, mm)"}]
# Optional request fields for a reading or daily file: the same names, defaults and checks as the upload form of POST /api/validation/runs.
DECLARATIONS = [{"id": "accumulation_mode", "values": ["cumulative", "per_reading"], "needed_when": "a reading file has an accumulation column (no default)"},
                {"id": "timezone", "values": "UTC, an offset such as +05:30, or an IANA name", "needed_when": "reading timestamps carry no offset"},
                {"id": "interval_minutes", "values": "a number greater than 0", "needed_when": "optional; without it the gap check is reported as not run"},
                {"id": "synthetic", "values": [True, False], "needed_when": "optional; label the run as synthetic data (default false)"}]


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
        "formats": FORMATS,
        "declarations": DECLARATIONS,
        "limits": {"max_mb": jobs_svc.MAX_BYTES // (1024 * 1024), "max_files": importers.MAX_FILES,
                   "max_mb_reading_daily": importers.intake_ingest.MAX_BYTES // (1024 * 1024)},
    }


class ImportBody(BaseModel):
    provider: Literal["aws", "kaggle"]
    url: str = ""                  # length and form are checked by the parser, which never echoes the link (a pydantic 422 would)
    format: Literal["auto", "cwc", "isd", "reading", "daily"] = "auto"
    accumulation_mode: Optional[str] = None       # the next four apply to reading and daily files only, as in the upload form
    timezone: Optional[str] = None
    interval_minutes: Optional[float] = None
    synthetic: bool = False


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
async def start_import(body: ImportBody, background: BackgroundTasks, response: Response, session: AsyncSession = Depends(get_db),
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
    runs: List[Any] = []
    skipped: List[Dict[str, str]] = []
    try:
        ready = []
        for f in fetched:
            try:
                ready.append(importers.prepare(f, body.format))
                paths.append(ready[-1][0].path)
            except importers.ImportRefused as e:
                if len(fetched) == 1:
                    raise HTTPException(e.status, str(e))
                skipped.append({"name": f.name, "reason": e.short})
        # reading and daily files first: a rejection of the only file answers before any background job has been queued
        for f, fmt in ready:
            if fmt not in ("reading", "daily"):
                continue
            try:
                runs.append(await importers.run_reading_file(session, f, fmt, body.accumulation_mode, body.timezone, body.interval_minutes, body.synthetic))
            except importers.ImportRefused as e:
                if len(fetched) == 1:
                    raise HTTPException(e.status, str(e))
                skipped.append({"name": f.name, "reason": e.short})
        if not ready or (len(fetched) > 1 and not runs and all(fmt in ("reading", "daily") for _f, fmt in ready)):
            listed = "; ".join(f"{s['name']}: {s['reason'][:160]}" for s in skipped[:5])
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"none of the {len(fetched)} files could be imported ({listed}). {importers.ACCEPTED_FORMATS}")
        pipeline_api._obs_count_cache["at"] = 0.0
        for f, fmt in ready:
            if fmt in ("reading", "daily"):
                continue
            extra = {"import": {"provider": body.provider, "origin": origin, "requested_format": body.format},
                     "format_detection": "sniffed from the file content" if body.format == "auto" else "given by the caller"}
            job = await jobs_svc.create_job(session, fmt, f.name, f.sha256, f.size, extra)
            jobs.append(job)
            background.add_task(jobs_svc.run_job, job.id, f.path)
            handed.add(f.path)
    finally:
        for p in set(paths) - handed:                       # anything not handed to a job: nobody else will remove it
            Path(p).unlink(missing_ok=True)
    logger.info("import accepted: provider=%s jobs=%d runs=%d skipped=%d", body.provider, len(jobs), len(runs), len(skipped))      # no link, no credentials
    common = {"provider": body.provider, "origin": origin, "job_ids": [j.id for j in jobs], "run_ids": [r.id for r in runs],
              "skipped_files": [s["name"] for s in skipped], "skipped": skipped}
    if jobs:
        return {**jobs_svc.job_dict(jobs[0]), "kind": "jobs", **common}
    response.status_code = status.HTTP_201_CREATED          # a run is already complete when the answer comes back, as for an upload
    return {"kind": "runs", "id": runs[0].id, "run_id": runs[0].id, "run": runs_svc.run_dict(runs[0], full=True), **common}
