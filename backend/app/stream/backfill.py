"""Startup backfill of the simulator: earlier SYNTHETIC readings, pushed through the live ReadingProcessor before the live simulator starts.

Why: the Keras score needs 288 readings per station and variable and a threshold needs about 1,000 clean scores, so a fresh deployment (the free
Render tier keeps no data across restarts) would show nothing for a long time. The backfill generates the missing earlier readings with the SAME
seeded physics as the live simulator (no injected faults), at its cadence, ending one cadence before now, and gives each one to the processor in
strict time order per station: the checks, the per-station history, the scorer windows and clean-error thresholds, and the storage behave exactly
as in a live run of that length. They are stored with the source id of the simulator and stay labelled in the database and the API. No score is
invented: the real scorer client is called; with the scorer absent or failing the readings and checks are still stored and the provider block says
"scorer not available". The live simulator continues from where the backfill stopped (same noise state, later timestamps).

Manual use:  python -m backend.app.stream.backfill [--readings N]
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from backend.app.config import settings
from backend.app.db import database
from backend.app.stream.manager import Processor, StreamManager
from backend.app.stream.models import StreamReadingRow
from backend.app.stream.simulator import SimulatorSource
from backend.app.stream.types import StreamReading, utcnow

logger = logging.getLogger(__name__)

AUTO_WITH_SCORER = 1300        # assumed: 288 (window) + 1000 (SCORER_MIN_CLEAN_SCORES) + margin
AUTO_WITHOUT_SCORER = 300      # assumed: some history for the checks; no model score needs more
WAKE_MAX_S = 60.0
BULK_TIMEOUT_S = 15.0          # per scorer call during the backfill (a freshly woken free-tier service is slow)
BULK_BACKOFF_S = 2.0


@dataclass
class BackfillState:
    """What the status endpoints show: status is idle, running, done, skipped (with a reason) or partial (cut off by the timeout or an error)."""
    status: str = "idle"
    reason: Optional[str] = None
    stations_total: int = 0
    stations_done: int = 0
    readings_target: int = 0           # per station
    readings_done: int = 0             # all stations together
    readings_total: int = 0
    scorer: str = "absent"             # absent | awake | not_awake
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    seconds: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source"] = "simulator"
        d["synthetic"] = True
        if self.status == "running":
            d["message"] = f"backfilling {self.stations_done} of {self.stations_total} stations, {self.readings_done} of {self.readings_total} readings"
        elif self.status in ("done", "partial"):
            d["message"] = f"backfill {self.status}: {self.readings_done} readings for {self.stations_total} stations" + (f" ({self.reason})" if self.reason else "")
        elif self.status == "skipped":
            d["message"] = f"backfill skipped: {self.reason}"
        else:
            d["message"] = "no backfill"
        return d


state = BackfillState()
_task: Optional["asyncio.Task[Any]"] = None


def _now_iso() -> str:
    return utcnow().isoformat().replace("+00:00", "Z")


def target_per_station(override: Optional[int] = None) -> int:
    n = settings.STREAM_BACKFILL_READINGS if override is None else override
    if n < 0:
        return AUTO_WITH_SCORER if settings.SCORER_URL else AUTO_WITHOUT_SCORER
    return n


def enabled() -> bool:
    return target_per_station() > 0 and settings.STREAM_BACKFILL_STATIONS > 0


async def _stored(station_ids: List[str], source: str) -> Dict[str, Any]:
    async with database.async_session_factory() as s:
        rows = (await s.execute(select(StreamReadingRow.station_id, func.count(), func.max(StreamReadingRow.timestamp))
                                .where(StreamReadingRow.source == source, StreamReadingRow.station_id.in_(station_ids))
                                .group_by(StreamReadingRow.station_id))).all()
    return {sid: (n, ts) for sid, n, ts in rows}


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    from backend.app.stream.service import aware
    return aware(dt)


async def run_backfill(sim: SimulatorSource, processor: Processor, readings: Optional[int] = None, stations: Optional[int] = None,
                       timeout_s: Optional[float] = None, now: Optional[datetime] = None) -> BackfillState:
    """Generate and process the missing earlier readings of the simulator's stations. Idempotent: a station with enough stored readings is left alone.
    Never raises for a scorer problem; the state says what happened."""
    global state
    st = state = BackfillState(status="running", started_at=_now_iso())
    t0 = time.monotonic()
    try:
        target = target_per_station(readings)
        cap = settings.STREAM_BACKFILL_STATIONS if stations is None else stations
        st.readings_target = target
        if target <= 0 or cap <= 0:
            st.status, st.reason = "skipped", "disabled (STREAM_BACKFILL_READINGS is 0)" if target <= 0 else "disabled (STREAM_BACKFILL_STATIONS is 0)"
            return st
        ids = sim.active_station_ids[:cap]
        have = await _stored(ids, sim.source_id)
        need = {sid: target - have.get(sid, (0, None))[0] for sid in ids}
        todo = [sid for sid in ids if need[sid] > 0]
        st.stations_total = len(ids)
        if not todo:
            st.status, st.reason, st.stations_done = "skipped", f"every station already has {target} stored readings", len(ids)
            return st
        st.stations_done = len(ids) - len(todo)
        steps = sim.generate_history(max(need[sid] for sid in todo), now)
        per: Dict[str, List[StreamReading]] = {sid: [] for sid in todo}
        for step in steps:
            for r in step:
                if r.station_id in per:
                    per[r.station_id].append(r)
        for sid in todo:                                    # the missing count, newest ones; and never at or before a reading already stored
            rows = per[sid][-need[sid]:]
            last = _aware(have.get(sid, (0, None))[1])
            per[sid] = [r for r in rows if last is None or r.timestamp > last]
        st.readings_total = sum(len(v) for v in per.values())

        scorer = getattr(processor, "scorer", None)
        client = getattr(scorer, "client", None) if scorer is not None and getattr(scorer, "enabled", False) else None
        ctx = contextlib.AsyncExitStack()
        if client is not None:
            st.scorer = "awake" if await client.wake(WAKE_MAX_S) else "not_awake"
            if st.scorer == "awake":
                await ctx.enter_async_context(client.bulk(timeout=max(client.timeout, BULK_TIMEOUT_S), backoff_s=BULK_BACKOFF_S))
            else:
                logger.warning("[BACKFILL] the scorer did not wake within %.0f s: readings and checks are stored without model scores", WAKE_MAX_S)

        async def worker(batch: List[StreamReading], last: bool) -> None:
            for r in batch:
                await processor(r)
                st.readings_done += 1
                await asyncio.sleep(0)
            if last:
                st.stations_done += 1

        async def run_batches(batches: Dict[str, List[StreamReading]], last: bool, budget_s: float) -> List["asyncio.Task[Any]"]:
            """The stations run side by side (each one strictly in time order); what is not finished when the budget ends is cancelled."""
            tasks = [asyncio.create_task(worker(b, last)) for b in batches.values()]
            try:
                _, pending = await asyncio.wait(tasks, timeout=budget_s)
                for p in pending:
                    p.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            except asyncio.CancelledError:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            return tasks

        budget = settings.STREAM_BACKFILL_TIMEOUT_SECONDS if timeout_s is None else timeout_s
        async with ctx:
            tasks = await run_batches(per, True, budget)
            for _ in range(5):          # processing took real time: carry on to the present so the first live reading follows without a gap (not with a fixed `now`)
                left = budget - (time.monotonic() - t0)
                if now is not None or left <= 0 or any(t.cancelled() or t.exception() for t in tasks):
                    break
                extra = sim.catch_up()
                if not extra:
                    break
                more: Dict[str, List[StreamReading]] = {sid: [r for step in extra for r in step if r.station_id == sid] for sid in todo}
                st.readings_total += sum(len(v) for v in more.values())
                tasks += await run_batches(more, False, left)
        errors = [t.exception() for t in tasks if t.done() and not t.cancelled() and t.exception()]
        if errors:
            st.status, st.reason = "partial", f"{type(errors[0]).__name__}: {errors[0]}"
            logger.error("[BACKFILL] a station failed: %s", errors[0])
        elif st.readings_done < st.readings_total:
            st.status, st.reason = "partial", "timeout"
        else:
            st.status = "done"
        return st
    except asyncio.CancelledError:
        st.status, st.reason = "partial", "cancelled"
        raise
    except Exception as exc:                                 # the backfill must never stop the server or the live simulator from starting
        logger.exception("[BACKFILL] failed")
        st.status, st.reason = "partial", f"{type(exc).__name__}: {exc}"
        return st
    finally:
        st.seconds = round(time.monotonic() - t0, 1)
        st.finished_at = _now_iso()
        logger.info("[BACKFILL] %s: %s/%s readings in %.1f s (%s)", st.status, st.readings_done, st.readings_total, st.seconds, st.reason or "ok")


async def backfill_then_select(manager: StreamManager, source_id: str) -> None:
    """The background task of the autostart: backfill, then start the source (unless something else was chosen in the meantime)."""
    try:
        await run_backfill(manager.source("simulator"), manager.processor)           # type: ignore[arg-type]
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("[BACKFILL] task failed")
    if manager.active is None:
        try:
            await manager.select(source_id)
        except Exception as exc:
            logger.warning("[STREAM] the simulator did not start after the backfill: %s", exc)


def start_in_background(manager: StreamManager, source_id: str) -> None:
    global _task
    state.status = "running"                                 # visible at once, before the task is scheduled
    _task = asyncio.create_task(backfill_then_select(manager, source_id))


async def cancel() -> None:
    global _task
    task, _task = _task, None
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def _main(readings: Optional[int]) -> None:
    from backend.app.db.database import close_db, init_db
    from backend.app.stream import runtime
    await init_db()
    manager = runtime.get_manager()
    result = await run_backfill(manager.source("simulator"), manager.processor, readings=readings)       # type: ignore[arg-type]
    print(result.as_dict())
    await close_db()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Backfill the simulator stations with earlier synthetic readings (idempotent).")
    ap.add_argument("--readings", type=int, default=None, help="readings per station (default: STREAM_BACKFILL_READINGS)")
    asyncio.run(_main(ap.parse_args().readings))
