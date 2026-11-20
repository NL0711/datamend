"""Tables of the ingest and feedback loop. Generic column types only (SQLite now, PostgreSQL and Timescale on Tiger Cloud).

``pipeline_observations`` is the raw store: one row per source, station and hour, written once, never updated. Its primary key contains the
time column so Timescale can make it a hypertable (see store.ensure_timescale).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStation(Base):
    __tablename__ = "pipeline_stations"

    station_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128))
    state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Observation(Base):
    """One hourly rainfall value as the source reported it, time in UTC. Immutable: a correction is a separate row in ``pipeline_corrections``."""
    __tablename__ = "pipeline_observations"
    __table_args__ = (Index("ix_pobs_job", "job_id"),)

    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    station_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value_mm: Mapped[float] = mapped_column(Float)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class IngestJob(Base):
    __tablename__ = "pipeline_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    source: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="queued")        # queued | running | done | failed
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)          # already stored (same source, station, hour)
    rows_bad: Mapped[int] = mapped_column(Integer, default=0)                # could not be stored; the first ones are listed in bad_samples
    stations: Mapped[int] = mapped_column(Integer, default=0)
    bad_samples: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    assumptions: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)  # e.g. the assumed time zone; every assumption is written down
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # the checking run made from this source, if any


class Proposal(Base):
    """A suggested correction for a flagged station-day. Always generated, stored apart from the data, no effect until a reviewer accepts."""
    __tablename__ = "pipeline_proposals"
    __table_args__ = (Index("ix_pprop_run_row", "run_id", "row_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True)
    row_ref: Mapped[str] = mapped_column(String(64))
    station_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))                            # exclude_value | review_peak | review_repeat
    original_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    proposed_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # None with exclude_value = "treat as no data"
    text: Mapped[str] = mapped_column(Text)
    generator: Mapped[str] = mapped_column(String(24))                       # baseline-rules | mcp-narrator
    generated: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)   # pending | accepted | rejected
    decided_by: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Correction(Base):
    """A reviewer-accepted replacement for one station-day. The original value is kept beside it; observations are never changed."""
    __tablename__ = "pipeline_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True)
    row_ref: Mapped[str] = mapped_column(String(64))
    station_id: Mapped[str] = mapped_column(String(64))
    original_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    corrected_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # None = excluded (no data)
    proposal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reviewer: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditItem(Base):
    """A randomly drawn UNFLAGGED station-day sent to the reviewer, with its weight, so missed faults can be estimated."""
    __tablename__ = "pipeline_audit"
    __table_args__ = (Index("ix_paudit_run_row", "run_id", "row_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True)
    row_ref: Mapped[str] = mapped_column(String(64))
    station_id: Mapped[str] = mapped_column(String(64))
    inclusion_probability: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)                              # 1 / inclusion probability
    decision: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)   # ok | missed_fault | unsure
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingSnapshot(Base):
    """A frozen export of labelled station-days cut by time, for ONE offline training run. The content is stored so it can never change."""
    __tablename__ = "pipeline_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    cut_day: Mapped[str] = mapped_column(String(10))                          # nothing after this rain day is in the snapshot
    n_rows: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    content: Mapped[str] = mapped_column(Text)                                # JSON lines, ordered


class TrainingJob(Base):
    """One retraining run started from a snapshot: here on the server's CPU, or as a Kaggle notebook. A finished job registers a challenger."""
    __tablename__ = "pipeline_training_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    snapshot_id: Mapped[int] = mapped_column(Integer, index=True)
    target: Mapped[str] = mapped_column(String(8))                            # local | kaggle | aws
    name: Mapped[str] = mapped_column(String(64), default="label-fusion")
    slug: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)    # the Kaggle notebook, user/slug; for aws: aws:<region>:<instance id>
    status: Mapped[str] = mapped_column(String(10), default="running")        # running | complete | failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelVersion(Base):
    """A model trained offline, registered with its metrics. Only a passed gate moves the champion alias."""
    __tablename__ = "pipeline_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    name: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    artifact_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    artifact_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    snapshot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    gate: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    alias: Mapped[str] = mapped_column(String(12), default="challenger", index=True)   # champion | challenger | archived | rejected
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ModelScore(Base):
    """What a registered model scored on one row of a pipeline run. Stored apart from the verdict and the rule score, which it never changes.
    ``score`` is the model's own number (a logistic output for label_fusion), ``flagged`` is score >= the threshold fixed at training time."""
    __tablename__ = "pipeline_model_scores"
    __table_args__ = (Index("ix_pms_run_row", "run_id", "row_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipeline_models.id", ondelete="CASCADE"), index=True)
    row_ref: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float)
    flagged: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ShadowRun(Base):
    """A challenger scored beside the champion on the same run. The report is measured on rows a reviewer labelled; it changes nothing by itself."""
    __tablename__ = "pipeline_shadow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True)
    champion_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    challenger_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipeline_models.id", ondelete="CASCADE"), index=True)
    report: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CleaningPlan(Base):
    """One run of the cleaning planner: the policy it was given and the profile it was judged against, stored so the result is reproducible."""
    __tablename__ = "pipeline_cleaning_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    source: Mapped[str] = mapped_column(String(16), index=True)
    policy: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    profile: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class PipelineCleaning(Base):
    """A cleaning proposal (fill a missing step, or exclude an impossible value). Raw observations are never changed: an accepted proposal is
    applied only when a check run is asked to ``use_clean``. Values filled in are derived (imputed), never measured."""
    __tablename__ = "pipeline_cleaning"
    __table_args__ = (Index("ix_pclean_src_station", "source", "station_key", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(16))
    station_key: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(12))                            # interpolate | exclude
    original: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    proposed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # None with exclude = treat as no data
    method: Mapped[str] = mapped_column(String(16))                          # linear | previous | range | missing_code
    why: Mapped[str] = mapped_column(Text)
    neighbours: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    basis: Mapped[str] = mapped_column(String(8), default="derived")
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)   # pending | accepted | rejected
    decided_by: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PipelineProfile(Base):
    """The user's edits to a dataset's variable profile (parameter, kind, units, valid range, missing codes). Detection never writes here."""
    __tablename__ = "pipeline_profiles"

    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    overrides: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
