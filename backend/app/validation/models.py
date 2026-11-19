"""Tables of the validation platform (spec section 5): validation_runs, validation_results, validation_check_hits.

Written to work on SQLite now and PostgreSQL later: only generic column types (JSON, not a dialect type). On the Render free tier
SQLite resets on restart, so the API labels storage "demo storage, resets on restart"; the JSON export is the durable copy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    profile: Mapped[str] = mapped_column(String(16))                 # reading | daily
    source: Mapped[str] = mapped_column(String(16))                  # upload | live
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)   # file name, or "live <rain day>"
    input_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    n_rows: Mapped[int] = mapped_column(Integer, default=0)
    n_stations: Mapped[int] = mapped_column(Integer, default=0)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)      # thresholds, accumulation mode, radius, interval
    platform_version: Mapped[str] = mapped_column(String(32))
    git_commit: Mapped[str] = mapped_column(String(64))              # "unknown" when the build has no git metadata
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="completed")     # completed | failed | open (live)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    not_run: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    renamed_headers: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict)
    issue_counts: Mapped[Dict[str, int]] = mapped_column(JSON, default=dict)
    report: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    rain_day: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, index=True)   # live runs: the date the rain day ends
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)  # the uploader declared the data synthetic


class ValidationResult(Base):
    __tablename__ = "validation_results"
    __table_args__ = (Index("ix_vr_run_score", "run_id", "rule_score"), Index("ix_vr_run_station", "run_id", "station_id", "time_key"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)                   # order of the row in the input
    row_ref: Mapped[str] = mapped_column(String(64))
    station_id: Mapped[str] = mapped_column(String(64))
    time_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # ISO UTC timestamp, or the day; sorts as text
    intensity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accumulation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verdict: Mapped[str] = mapped_column(String(12), index=True)
    rule_score: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    original_row: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)   # the input row, untouched
    issues: Mapped[List[Dict[str, str]]] = mapped_column(JSON, default=list)   # input-integrity issues from the parser


class ValidationCheckHit(Base):
    __tablename__ = "validation_check_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True)
    result_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_results.id", ondelete="CASCADE"), index=True)
    check: Mapped[str] = mapped_column(String(48), index=True)
    layer: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(12))
    weight: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
