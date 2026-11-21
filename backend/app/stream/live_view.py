"""Read-only view of the CURRENT live feed of one station, for the MCP tools and the agent's gate (PROTOTYPE).

Everything here only reads. ``stream_readings`` and ``stream_events`` are append-only, so a snapshot is defined by a CUTOFF reading id: the same
station, window and cutoff always return the same rows and therefore the same ``snapshot_hash`` (a live feed moves every second; the evidence the
agent held must not). The cutoff is an id, not a timestamp, because a late reading may carry an earlier timestamp but never an earlier id; the
cutoff's timestamp is reported next to it.

Values are the raw values as stored (a variable the source did not send is null; nothing is filled in). Scores are labelled: the rule score is
uncalibrated, the Keras provider block is "not validated" and never a verdict.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.scorer.service import NOTE as MODEL_NOTE
from backend.app.scorer.service import SCORE_KIND
from backend.app.scorer.service import expand as scorer_expand
from backend.app.stream import frames
from backend.app.stream.manager import StreamManager
from backend.app.stream.models import StreamEvent, StreamReadingRow

DEFAULT_WINDOW = 60
MAX_WINDOW = 288                 # the Keras model's window length; also keeps a result far below the MCP result cap
DEFAULT_DETECTIONS = 20
MAX_DETECTIONS = 50
COLUMNS = ["id", "timestamp", "temperature", "pressure", "humidity", "rain_mm", "source", "check_status", "rule_score"]
RULE_SCORE_NOTE = "uncalibrated rule score (an ordering of suspicion, not a probability)"
MODEL_LABEL = "not validated"


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return frames.iso(aware(dt))


def _reading_row(r: StreamReadingRow) -> list:
    return [r.id, _iso(r.timestamp), r.temperature_c, r.pressure_hpa, r.humidity_pct, r.rain_mm, r.source, r.check_status, r.rule_score]


def snapshot_hash(station_id: str, cutoff_id: Optional[int], window: int, rows: List[list], detections: List[list]) -> str:
    """Hash of an immutable snapshot: the station, cutoff, window and the stored rows (``COLUMNS`` order) and detection keys of it."""
    payload = {"station_id": station_id, "cutoff_id": cutoff_id, "window": window, "readings": rows, "detections": detections}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def detection_key(e: StreamEvent) -> list:
    return [e.id, e.reading_id, e.verdict, e.rule_score, e.classification]


async def _window_rows(session: AsyncSession, station_id: str, window: int, up_to_id: Optional[int]) -> List[StreamReadingRow]:
    q = select(StreamReadingRow).where(StreamReadingRow.station_id == station_id)
    if up_to_id is not None:
        q = q.where(StreamReadingRow.id <= up_to_id)
    rows = (await session.execute(q.order_by(desc(StreamReadingRow.id)).limit(window))).scalars().all()
    return list(reversed(rows))


async def _window_events(session: AsyncSession, station_id: str, first_id: int, cutoff_id: int, limit: Optional[int] = None) -> List[StreamEvent]:
    q = (select(StreamEvent).where(StreamEvent.station_id == station_id, StreamEvent.reading_id >= first_id, StreamEvent.reading_id <= cutoff_id)
         .order_by(desc(StreamEvent.id)))
    if limit:
        q = q.limit(limit)
    return list((await session.execute(q)).scalars().all())


async def snapshot_digest(session: AsyncSession, station_id: str, window: int, up_to_id: Optional[int]) -> Optional[str]:
    """The hash of the snapshot (station, window, cutoff) as it is stored NOW; None when the station has no readings up to the cutoff."""
    window = max(1, min(int(window), MAX_WINDOW))
    rows = await _window_rows(session, station_id, window, up_to_id)
    if not rows:
        return None
    events = await _window_events(session, station_id, rows[0].id, rows[-1].id)
    return snapshot_hash(station_id, rows[-1].id, window, [_reading_row(r) for r in rows], sorted(detection_key(e) for e in events))


def source_state(manager: StreamManager, station_id: str) -> Dict[str, Any]:
    """The source state as it is now. ``feed_state`` is the state of THIS station's feed: the manager's state when the active source serves the
    station, ``not_streaming`` when it does not (stored readings are then history, not a live feed)."""
    st = manager.status()
    active = manager.active
    served = active is not None and any(s.station_id == station_id for s in active.stations())
    feed = st.state if served or active is None else "not_streaming"
    return {"feed_state": feed, "source_state": st.state, "source_id": st.source_id, "source_type": st.source_type, "station_served": bool(served),
            "cadence_seconds": st.expected_interval_s, "stale_after_seconds": st.stale_after_s, "stale_since": frames.iso(st.stale_since),
            "source_last_reading_at": frames.iso(st.last_reading_at), "last_error": st.last_error}


async def feed_view(session: AsyncSession, manager: StreamManager, station_id: str, window: int = DEFAULT_WINDOW, up_to_id: Optional[int] = None) -> Dict[str, Any]:
    window = max(1, min(int(window), MAX_WINDOW))
    rows = await _window_rows(session, station_id, window, up_to_id)
    state = source_state(manager, station_id)
    events: List[StreamEvent] = await _window_events(session, station_id, rows[0].id, rows[-1].id) if rows else []
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r.check_status] = counts.get(r.check_status, 0) + 1
    not_run: Dict[str, str] = {}
    for e in events:
        for item in e.not_run or []:
            not_run.setdefault(str(item.get("check")), str(item.get("reason", "")))
    last = rows[-1] if rows else None
    latest_provider = next((r for r in reversed(rows) if r.provider), None)
    now = datetime.now(timezone.utc)
    cutoff_id = last.id if last else None
    return {
        "station_id": station_id, **state, "window": window, "n_readings": len(rows),
        "snapshot": {"cutoff_id": cutoff_id, "cutoff_timestamp": _iso(last.timestamp) if last else None, "immutable": True,
                     "note": "append-only rows up to the cutoff id; pass up_to_id=cutoff_id to read the same window again"},
        "last_reading_at": _iso(last.timestamp) if last else None, "last_reading_id": cutoff_id,
        "data_age_seconds": round((now - aware(last.timestamp)).total_seconds(), 1) if last else None,
        "last_verdict": last.check_status if last else None, "last_rule_score": last.rule_score if last else None,
        "counts_by_check_status": counts, "detections_in_window": len(events),
        # readings keep no 'not run' list, only detections do: an empty list would read as 'all checks ran' (or 'none ran'), so it is null with a note
        "checks_not_run": [{"check": k, "reason": v} for k, v in sorted(not_run.items())] or None,
        "checks_not_run_note": None if not_run else "not available: stored readings keep no list of checks that did not run; do not say that no checks ran or that all checks ran",
        "readings_with_no_checks": counts.get("NO_CHECKS", 0) + counts.get("NO_DATA", 0),
        "model_score": {"present": latest_provider is not None, "label": MODEL_LABEL, "kind": SCORE_KIND,
                        "provider": scorer_expand(latest_provider.provider) if latest_provider else None,
                        "at_reading_id": latest_provider.id if latest_provider else None},
        "score_kind": RULE_SCORE_NOTE,
        "columns": COLUMNS, "readings": [_reading_row(r) for r in rows],
        "values_note": "raw values as stored (null = the source did not send it, never filled in); source says which source produced each reading",
        "snapshot_hash": snapshot_hash(station_id, cutoff_id, window, [_reading_row(r) for r in rows], sorted(detection_key(e) for e in events)) if rows else None,
    }


async def detections_view(session: AsyncSession, manager: StreamManager, station_id: str, limit: int = DEFAULT_DETECTIONS, up_to_id: Optional[int] = None,
                          window: int = DEFAULT_WINDOW) -> Dict[str, Any]:
    """The newest detections of the station (checks that fired, with evidence) inside the same window the feed view uses, newest first."""
    limit = max(1, min(int(limit), MAX_DETECTIONS))
    window = max(1, min(int(window), MAX_WINDOW))
    rows = await _window_rows(session, station_id, window, up_to_id)
    events: List[StreamEvent] = await _window_events(session, station_id, rows[0].id, rows[-1].id) if rows else []
    items = []
    for e in events[:limit]:
        items.append({"id": e.id, "reading_id": e.reading_id, "timestamp": _iso(e.timestamp), "variable": e.variable, "verdict": e.verdict, "rule_score": e.rule_score,
                      "score_kind": RULE_SCORE_NOTE, "severity": e.severity, "classification": e.classification, "is_fault": e.is_fault, "reason": e.reason,
                      "checks_fired": [h.get("check") for h in (e.hits or []) if h.get("check")], "evidence": e.hits, "not_run": e.not_run, "source": e.source,
                      "provider": scorer_expand(e.provider) if e.provider else None,
                      "provider_label": f"{MODEL_LABEL}; a reconstruction-error score, never a verdict" if e.provider else None, "note": MODEL_NOTE if e.provider else None})
    return {"station_id": station_id, **{k: v for k, v in source_state(manager, station_id).items() if k in ("feed_state", "source_id")},
            "window": window, "cutoff_id": rows[-1].id if rows else None, "total_in_window": len(events), "returned": len(items), "limit": limit,
            "detections": items, "snapshot_hash": snapshot_hash(station_id, rows[-1].id, window, [_reading_row(r) for r in rows], sorted(detection_key(e) for e in events)) if rows else None}
