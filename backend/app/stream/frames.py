"""The JSON frames the telemetry WebSocket sends. The shapes follow the dashboard's own client (frontend/src/services/websocket.ts):

* ``{"type": "observation", "station_id": ..., "data": {...}}``: one reading. ``data`` has timestamp, station_id, temperature, pressure,
  humidity, rain_mm (None where the source has no such variable) and ``validation_status`` (NO_CHECKS, OK, UNCERTAIN, SUSPECT, NO_DATA). Score,
  severity, classification, reason and ``is_anomaly`` appear only when a check ran. The source label is NOT in the frame (stored readings only).
* ``{"type": "status", "data": {...}}``: the stream's state. It has no station_id, so the client does not mistake it for a reading.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.stream.scoring import CheckOutcome
from backend.app.stream.types import StreamReading


def iso(dt) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def observation_data(reading: StreamReading, outcome: Optional[CheckOutcome] = None, *, stored: bool = True) -> Dict[str, Any]:
    outcome = outcome or CheckOutcome()
    data: Dict[str, Any] = {
        "timestamp": iso(reading.timestamp), "station_id": reading.station_id,
        "temperature": reading.temperature_c, "pressure": reading.pressure_hpa, "humidity": reading.humidity_pct, "rain_mm": reading.rain_mm,
        "validation_status": outcome.status, "checks_run": outcome.ran, "not_run": outcome.not_run, "stored": stored,
    }
    if outcome.ran:
        data.update(anomaly_score=outcome.rule_score, is_anomaly=outcome.flagged, severity=(outcome.severity or "none").upper() if outcome.flagged else "NORMAL",
                    classification=outcome.classification or "no_check_fired", reason=outcome.reason, is_fault=outcome.status == "SUSPECT")
    return data


def observation_frame(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "observation", "station_id": data["station_id"], "data": data}


def status_frame(status: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "status", "data": status}
