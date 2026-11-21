"""Tables of the telemetry stream: stored readings and the events (detections) the checks raised on them.

``stream_readings`` is append-only: a reading is written once with the values the source sent (a None stays NULL, a corrupt number stays as
sent) and the outcome of the checks at that moment; nothing is updated or filled in later. ``source`` is the id of the source that produced
it. ``injected_fault`` is the synthetic ground-truth label of a fault the simulator injected on purpose (NULL for everything else).
``stream_events`` holds a detection only when a check actually fired, with the evidence of every check that fired.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StreamReadingRow(Base):
    __tablename__ = "stream_readings"
    __table_args__ = (Index("ix_stream_readings_station_time", "station_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rain_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    injected_fault: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    check_status: Mapped[str] = mapped_column(String(12))            # NO_CHECKS | OK | UNCERTAIN | SUSPECT | NO_DATA
    rule_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # NULL when no check ran; the uncalibrated rule score, never a probability


class StreamEvent(Base):
    __tablename__ = "stream_events"
    __table_args__ = (Index("ix_stream_events_station_time", "station_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_id: Mapped[int] = mapped_column(Integer, ForeignKey("stream_readings.id", ondelete="CASCADE"), index=True)
    station_id: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    variable: Mapped[str] = mapped_column(String(16))                # rain (the only variable with checks so far)
    verdict: Mapped[str] = mapped_column(String(12))                 # SUSPECT | UNCERTAIN
    rule_score: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(8))                 # low | medium | high
    classification: Mapped[str] = mapped_column(String(160))         # the names of the checks that fired
    is_fault: Mapped[bool] = mapped_column(Boolean)                  # a fault-kind check fired (verdict SUSPECT)
    reason: Mapped[str] = mapped_column(Text)
    hits: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)       # evidence of every check that fired
    not_run: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)    # checks that could not run, with the reason
    source: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
