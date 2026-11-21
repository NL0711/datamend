"""Services of the telemetry stream: store and check a reading, query what was stored, control the simulator, describe the data sources.

The API routes (api/stream.py) only map these to HTTP. Typed errors (stream/types.py) are raised here and mapped there.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import database
from backend.app.rainfall.catalog import load_catalog
from backend.app.stream import frames
from backend.app.stream.manager import StreamManager, StreamStatus
from backend.app.stream.models import StreamEvent, StreamReadingRow
from backend.app.stream.scoring import NO_CHECKS, CheckOutcome, as_record, score_reading
from backend.app.stream.simulator import SimulatorSource
from backend.app.stream.types import SimulatorNotRunning, StreamReading, UnknownSource, UnknownStation, utcnow
from backend.app.validation.records import Reading

logger = logging.getLogger(__name__)

ACTIVE_WITHIN_S = 15 * 60          # a station counts as active when a reading of it was stored in the last 15 minutes
MAX_PAGE = 500
CONNECTION = {"running": "RUNNING", "stale": "DEGRADED", "disconnected": "DISCONNECTED", "stopped": "STOPPED"}
UI_STATUS = {"SUSPECT": "QC_FLAGGED", "UNCERTAIN": "QC_FLAGGED", "OK": "QC_PASSED", "NO_DATA": "NO_DATA", NO_CHECKS: NO_CHECKS}


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands timestamps back without a zone; everything stored here is UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return frames.iso(aware(dt))


# ---------------------------------------------------------------------------------------------------- store and check one reading
class ReadingProcessor:
    """The manager's processor in production: run the checks that exist for the reading, append it (and any detection) to the database, and
    return the frame data. Raw values are written as sent; nothing is overwritten later."""

    async def _history(self, session: AsyncSession, reading: StreamReading) -> List[Reading]:
        rows = (await session.execute(
            select(StreamReadingRow).where(StreamReadingRow.station_id == reading.station_id, StreamReadingRow.rain_mm.is_not(None),
                                           StreamReadingRow.timestamp < reading.timestamp)
            .order_by(desc(StreamReadingRow.timestamp)).limit(12))).scalars().all()
        return [as_record(StreamReading(r.station_id, aware(r.timestamp), r.source, rain_mm=r.rain_mm), r.id) for r in reversed(rows)]  # type: ignore[arg-type]

    async def __call__(self, reading: StreamReading) -> Dict[str, Any]:
        async with database.async_session_factory() as session:
            history = await self._history(session, reading) if reading.rain_mm is not None else []
            outcome = score_reading(reading, history)
            row = StreamReadingRow(station_id=reading.station_id, timestamp=reading.timestamp, temperature_c=reading.temperature_c,
                                   pressure_hpa=reading.pressure_hpa, humidity_pct=reading.humidity_pct, rain_mm=reading.rain_mm, source=reading.source,
                                   injected_fault=reading.injected, check_status=outcome.status, rule_score=outcome.rule_score)
            session.add(row)
            await session.flush()
            if outcome.flagged:
                session.add(StreamEvent(reading_id=row.id, station_id=reading.station_id, timestamp=reading.timestamp, variable="rain", verdict=outcome.status,
                                        rule_score=outcome.rule_score or 0.0, severity=outcome.severity or "low", classification=outcome.classification or "",
                                        is_fault=outcome.status == "SUSPECT", reason=outcome.reason or "", hits=outcome.hits, not_run=outcome.not_run,
                                        source=reading.source))
            await session.commit()
        return frames.observation_data(reading, outcome, stored=True)


# ---------------------------------------------------------------------------------------------------- stations
def station_directory(manager: StreamManager) -> List[Dict[str, Any]]:
    """The one station list: the Weather Union catalogue plus the stations of every registered source. A source's station carries no label."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for s in load_catalog().values():
        out.append({"station_id": s.locality_id, "name": f"{s.place}, {s.city}", "latitude": s.latitude, "longitude": s.longitude, "elevation": None})
        seen.add(s.locality_id)
    for src in manager.sources():
        for st in src.stations():
            if st.station_id in seen:
                logger.warning("station %s of source %s is already in the list and is skipped", st.station_id, src.source_id)
                continue
            seen.add(st.station_id)
            out.append({"station_id": st.station_id, "name": st.name, "latitude": st.latitude, "longitude": st.longitude, "elevation": st.elevation})
    return out


async def _last_reading_times(session: AsyncSession) -> Dict[str, datetime]:
    rows = (await session.execute(select(StreamReadingRow.station_id, func.max(StreamReadingRow.timestamp)).group_by(StreamReadingRow.station_id))).all()
    return {sid: aware(ts) for sid, ts in rows if ts is not None}      # type: ignore[misc]


def _station_object(idx: int, d: Dict[str, Any], last: Optional[datetime], now: datetime) -> Dict[str, Any]:
    active = last is not None and (now - last).total_seconds() <= ACTIVE_WITHIN_S
    return {"id": idx, **d, "status": "active" if active else "inactive", "created_at": None, "updated_at": frames.iso(last)}


async def list_stations(session: AsyncSession, manager: StreamManager, status: Optional[str] = None) -> Dict[str, Any]:
    last, now = await _last_reading_times(session), utcnow()
    items = [_station_object(i + 1, d, last.get(d["station_id"]), now) for i, d in enumerate(station_directory(manager))]
    if status:
        items = [i for i in items if i["status"] == status.lower()]
    return {"items": items, "total": len(items)}


async def get_station(session: AsyncSession, manager: StreamManager, station_id: str) -> Optional[Dict[str, Any]]:
    for i, d in enumerate(station_directory(manager)):
        if d["station_id"] == station_id:
            last = (await _last_reading_times(session)).get(station_id)
            return _station_object(i + 1, d, last, utcnow())
    return None


# ---------------------------------------------------------------------------------------------------- observations and detections
def observation_dict(r: StreamReadingRow) -> Dict[str, Any]:
    return {"id": r.id, "timestamp": _iso(r.timestamp), "station_id": r.station_id, "temperature": r.temperature_c, "pressure": r.pressure_hpa,
            "humidity": r.humidity_pct, "rain_mm": r.rain_mm, "source": r.source, "injected_fault": r.injected_fault,
            "validation_status": UI_STATUS.get(r.check_status, r.check_status), "check_status": r.check_status, "rule_score": r.rule_score}


async def list_observations(session: AsyncSession, station_id: Optional[str], limit: int, page: int) -> Dict[str, Any]:
    limit = max(1, min(limit, MAX_PAGE))
    q = select(StreamReadingRow)
    n = select(func.count()).select_from(StreamReadingRow)
    if station_id:
        q, n = q.where(StreamReadingRow.station_id == station_id), n.where(StreamReadingRow.station_id == station_id)
    rows = (await session.execute(q.order_by(desc(StreamReadingRow.timestamp), desc(StreamReadingRow.id)).limit(limit).offset((max(1, page) - 1) * limit))).scalars().all()
    return {"items": [observation_dict(r) for r in rows], "total": (await session.execute(n)).scalar_one()}


def anomaly_dict(e: StreamEvent) -> Dict[str, Any]:
    """The dashboard's AnomalyEvent. Fields the platform has no honest value for (confidence, explanation, tier scores) are left out."""
    return {"id": e.id, "observation_id": e.reading_id, "station_id": e.station_id, "timestamp": _iso(e.timestamp), "is_anomaly": True,
            "anomaly_score": e.rule_score, "severity": e.severity.upper(), "anomaly_type": e.classification.split(", ")[0] if e.classification else None,
            "classification": e.classification, "is_fault": e.is_fault, "reason": e.reason, "raw_values": {}, "source_id": e.source,
            "variable": e.variable, "verdict": e.verdict, "score_kind": "uncalibrated rule score", "evidence": e.hits, "not_run": e.not_run,
            "created_at": _iso(e.created_at)}


async def list_anomalies(session: AsyncSession, station_id: Optional[str] = None, severity: Optional[str] = None, classification: Optional[str] = None,
                         limit: int = 50, offset: int = 0, since: Optional[datetime] = None, severities: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    limit = max(1, min(limit, MAX_PAGE))
    conds = []
    if station_id:
        conds.append(StreamEvent.station_id == station_id)
    if severity:
        conds.append(StreamEvent.severity == severity.lower())
    if severities:
        conds.append(StreamEvent.severity.in_([s.lower() for s in severities]))
    if classification:
        conds.append(StreamEvent.classification.contains(classification))
    if since is not None:
        conds.append(StreamEvent.timestamp >= since)
    rows = (await session.execute(select(StreamEvent).where(*conds).order_by(desc(StreamEvent.timestamp), desc(StreamEvent.id)).limit(limit).offset(max(0, offset)))).scalars().all()
    total = (await session.execute(select(func.count()).select_from(StreamEvent).where(*conds))).scalar_one()
    items = []
    for e in rows:
        d = anomaly_dict(e)
        reading = await session.get(StreamReadingRow, e.reading_id)
        d["raw_values"] = {"rain_mm": reading.rain_mm} if reading is not None else {}
        items.append(d)
    return {"items": items, "total": total}


async def anomaly_stats(session: AsyncSession, hours: int) -> Dict[str, Any]:
    since = utcnow() - timedelta(hours=hours)
    rows = (await session.execute(select(StreamEvent).where(StreamEvent.timestamp >= since))).scalars().all()
    by_sev: Dict[str, int] = {}
    by_cls: Dict[str, int] = {}
    for e in rows:
        by_sev[e.severity.upper()] = by_sev.get(e.severity.upper(), 0) + 1
        for c in (e.classification.split(", ") if e.classification else []):
            by_cls[c] = by_cls.get(c, 0) + 1
    # genuine-extreme versus fault discrimination exists only where checks exist; there is none for the stream yet, so no extreme is ever counted
    return {"period_hours": hours, "total_anomalies": len(rows), "by_severity": by_sev, "by_classification": by_cls,
            "sensor_faults": sum(1 for e in rows if e.is_fault), "meteorological_extremes": 0}


async def anomaly_detail(session: AsyncSession, manager: StreamManager, event_id: int) -> Optional[Dict[str, Any]]:
    e = await session.get(StreamEvent, event_id)
    if e is None:
        return None
    reading = await session.get(StreamReadingRow, e.reading_id)
    d = anomaly_dict(e)
    d["observation"] = observation_dict(reading) if reading is not None else None
    d["raw_values"] = {"rain_mm": reading.rain_mm} if reading is not None else {}
    d["station"] = await get_station(session, manager, e.station_id)
    return d


# ---------------------------------------------------------------------------------------------------- data sources
NOT_IMPLEMENTED = (("EXTERNAL_API", "open-meteo", "Open-Meteo feed", "Planned in slice S3b."),
                   ("WEATHER_UNION", "weather-union", "Weather Union", "Planned in slice S3b."),
                   ("PHYSICAL_AWS", "esp32", "Physical ESP32", "Planned in slice S3b; there is no hardware to verify it against."))


def _source_entry(manager: StreamManager, src: Any, st: StreamStatus, active: bool) -> Dict[str, Any]:
    own = src.status()
    state = st.state if active else own.state
    now = utcnow()
    entry: Dict[str, Any] = {
        "source_type": src.source_type, "source_id": src.source_id, "name": src.name, "description": src.description, "status": CONNECTION[state],
        "is_active": active, "is_available": True, "station_id": "ALL", "is_stale": active and st.state == "stale", "packet_count": st.packet_count if active else 0,
        "polling_interval_seconds": own.expected_interval_s, "metadata": {"station_ids": [s.station_id for s in src.stations()]},
    }
    if active:
        if st.last_reading_at:
            entry["last_received_at"] = frames.iso(st.last_reading_at)
            entry["last_successful_fetch"] = frames.iso(st.last_reading_at)
            entry["data_age_seconds"] = round((now - st.last_reading_at).total_seconds(), 1)
        if st.stale_since:
            entry["metadata"]["stale_since"] = frames.iso(st.stale_since)
    if own.last_error:
        entry["error_message"] = own.last_error
        entry["last_error_at"] = frames.iso(own.last_error_at)
    return entry


def source_list(manager: StreamManager) -> Dict[str, Any]:
    st = manager.status()
    sources = [_source_entry(manager, s, st, manager.active is s) for s in manager.sources()]
    have = {s["source_type"] for s in sources}
    for typ, sid, name, note in NOT_IMPLEMENTED:
        if typ not in have:
            sources.append({"source_type": typ, "source_id": sid, "name": name, "description": f"NOT IMPLEMENTED. {note}", "status": "STOPPED", "is_active": False,
                            "is_available": False, "station_id": "", "is_stale": False, "packet_count": 0})
    return {"active_source": manager.active.source_type if manager.active else None, "active_source_id": manager.active.source_id if manager.active else None,
            "sources": sources, "timestamp": frames.iso(utcnow())}


def active_source_status(manager: StreamManager) -> Optional[Dict[str, Any]]:
    if manager.active is None:
        return None
    return _source_entry(manager, manager.active, manager.status(), True)


def source_by_type(manager: StreamManager, source_type: str) -> Optional[Any]:
    return next((s for s in manager.sources() if s.source_type == source_type), None)


async def select_source(manager: StreamManager, source_type: str) -> Dict[str, Any]:
    src = source_by_type(manager, source_type)
    if src is None:
        raise UnknownSource(f"the data source type '{source_type}' is not implemented")
    await manager.select(src.source_id)
    return _source_entry(manager, src, manager.status(), True)


# ---------------------------------------------------------------------------------------------------- simulator control
def simulator_of(manager: StreamManager) -> SimulatorSource:
    return manager.source("simulator")      # type: ignore[return-value]


def simulation_status(manager: StreamManager, message: Optional[str] = None) -> Dict[str, Any]:
    sim = simulator_of(manager)
    running = manager.active is sim and sim.status().state == "running"
    out: Dict[str, Any] = {"running": running, "interval_seconds": sim.interval_seconds, "active_stations": sim.active_station_ids,
                           "step_count": sim.step_count, "pending_injections_count": sim.pending_injections}
    out["message"] = message or ("Simulation running" if running else "Simulation idle")
    return out


async def start_simulation(manager: StreamManager, station_ids: Optional[List[str]] = None, interval_seconds: Optional[float] = None,
                           noise_level: Optional[float] = None, scenario: Optional[str] = None) -> Dict[str, Any]:
    sim = simulator_of(manager)
    if manager.active is sim and sim.status().state == "running":
        return simulation_status(manager, "Simulation is already running.")
    sim.configure(station_ids, interval_seconds, noise_level, scenario)
    await manager.select(sim.source_id)             # stops any other active source: one source feeds the stream at a time
    return simulation_status(manager, "Simulation started.")


async def stop_simulation(manager: StreamManager) -> Dict[str, Any]:
    if manager.active is simulator_of(manager):
        await manager.stop()
    return simulation_status(manager, "Simulation stopped.")


def inject_fault(manager: StreamManager, kind: str, station_id: Optional[str], parameter: str, magnitude: Optional[float], duration_steps: int,
                 decay: bool) -> Dict[str, Any]:
    sim = simulator_of(manager)
    if manager.active is not sim or sim.status().state != "running":
        raise SimulatorNotRunning("the simulator is not the running source; start it before injecting a fault (injections never touch another source)")
    ack = sim.inject(kind, station_id, parameter, magnitude, duration_steps, decay)
    return {"success": True, "status": "queued", **ack,
            "message": f"Queued a synthetic {ack['anomaly_type']} on {ack['parameter']} for {ack['duration_steps']} step(s); it appears from the next simulator step."}
