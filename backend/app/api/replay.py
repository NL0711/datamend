"""NOAA ISD India replay endpoints (backend/app/rainfall/isd_replay.py). The replay is real station data, labelled REPLAY, never live.

GET  /api/validation/replay/isd   status of the replay job and of the stored replay run (needs a signed-in session like every /api route)
POST /api/validation/replay/isd   start it (admin session or ADMIN_TOKEN); it runs in the background and replaces an earlier replay run
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.settings import require_admin
from backend.app.config import settings
from backend.app.db.database import async_session_factory, get_db
from backend.app.rainfall import isd_replay
from backend.app.validation import runs as runs_svc
from backend.app.validation.models import ValidationRun

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/validation/replay", tags=["replay"])


def _ids() -> Sequence[str]:
    custom = [s.strip() for s in (settings.ISD_REPLAY_STATIONS or "").split(",") if s.strip()]
    return custom or isd_replay.DEFAULT_STATIONS


async def _run_job(ids: Sequence[str], year: int, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
    job = isd_replay.JOB
    job.state, job.started_at, job.finished_at, job.run_id, job.message, job.stations = "running", datetime.now(timezone.utc).isoformat(), None, None, None, []
    try:
        res = await isd_replay.build(ids, year, transport)
        job.stations = res.stations
        if not res.records:
            raise RuntimeError("no daily totals could be fetched from NOAA for any station")
        ok = sum(1 for s in res.stations if s["ok"])
        last = max(r.day for r in res.records if r.day)
        label = f"NOAA ISD replay {year}: {ok} stations, real observations to {last}, not live"
        info = {"year": year, "stations": res.stations, "fetched_at": res.fetched_at, "note": res.note, "source": isd_replay.URL}
        async with async_session_factory() as session:
            run = await runs_svc.run_replay(session, res.records, label, info)
        job.run_id, job.state = run.id, "done"
        job.message = f"{len(res.records)} daily totals from {ok} of {len(res.stations)} stations"
    except Exception as e:                                                  # the job must end in a state the page can show
        logger.warning("[ISD REPLAY] failed: %s", e)
        job.state, job.message = "failed", str(e)[:300]
    finally:
        job.finished_at = datetime.now(timezone.utc).isoformat()


def start_job(transport: Optional[httpx.AsyncBaseTransport] = None) -> bool:
    """Start the replay in the background. False when one is already running."""
    if isd_replay.JOB.running:
        return False
    isd_replay.JOB.state = "running"                 # marked now, so a second request before the task starts is refused
    isd_replay.JOB._task = asyncio.create_task(_run_job(_ids(), isd_replay.YEAR, transport))
    return True


async def start_replay_on_boot() -> None:
    """At startup, when ISD_REPLAY_ON_START is set and no replay run is stored yet."""
    if not settings.ISD_REPLAY_ON_START:
        return
    async with async_session_factory() as session:
        exists = (await session.execute(select(ValidationRun.id).where(ValidationRun.source == "replay").limit(1))).first()
    if exists is None:
        start_job()
        logger.info("[ISD REPLAY] started at launch (ISD_REPLAY_ON_START)")


@router.get("/isd")
async def replay_status(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    run = (await session.execute(select(ValidationRun).where(ValidationRun.source == "replay").order_by(ValidationRun.id.desc()).limit(1))).scalars().first()
    out = isd_replay.JOB.status()
    out["stored_run_id"] = run.id if run else None
    out["stored_run_label"] = run.label if run else None
    out["on_start"] = bool(settings.ISD_REPLAY_ON_START)
    return out


@router.post("/isd", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
async def replay_start() -> Dict[str, Any]:
    if not start_job():
        raise HTTPException(status.HTTP_409_CONFLICT, "the replay is already running")
    return {**isd_replay.JOB.status(), "state": "running", "message": "started in the background"}
