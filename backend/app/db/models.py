"""
backend/app/db/models.py
SkyGuard AI — SQLAlchemy 2.0 ORM Models for AWS Telemetry, AI Diagnostics, and Sensor Health.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.database import Base


def utcnow() -> datetime:
    """Helper returning timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Station(Base):
    """Automatic Weather Station (AWS) registration and metadata."""
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    elevation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    observations: Mapped[List[Observation]] = relationship(
        "Observation", back_populates="station", cascade="all, delete-orphan", lazy="selectin"
    )
    sensor_health_records: Mapped[List[SensorHealth]] = relationship(
        "SensorHealth", back_populates="station", cascade="all, delete-orphan", lazy="selectin"
    )
    anomaly_events: Mapped[List[AnomalyEvent]] = relationship(
        "AnomalyEvent", back_populates="station", cascade="all, delete-orphan", lazy="selectin"
    )


class Observation(Base):
    """Raw meteorological observation time series from AWS sensors."""
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("stations.station_id", ondelete="CASCADE"), index=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pressure: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="VALID", nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(32), default="SIMULATED", nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    station: Mapped[Station] = relationship("Station", back_populates="observations")
    anomaly_event: Mapped[Optional[AnomalyEvent]] = relationship(
        "AnomalyEvent", back_populates="observation", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_observations_station_timestamp", "station_id", "timestamp"),
    )


class AnomalyEvent(Base):
    """AI-detected anomaly events, fault classifications, and explainability attributions."""
    __tablename__ = "anomaly_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("observations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    station_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("stations.station_id", ondelete="CASCADE"), index=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    anomaly_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    classification: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    is_fault: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(32), default="SIMULATED", nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    tier_scores: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    station: Mapped[Station] = relationship("Station", back_populates="anomaly_events")
    observation: Mapped[Optional[Observation]] = relationship("Observation", back_populates="anomaly_event")

    __table_args__ = (
        Index("ix_anomaly_events_station_timestamp", "station_id", "timestamp"),
        Index("ix_anomaly_events_station_severity", "station_id", "severity"),
    )


class SensorHealth(Base):
    """Dynamic Sensor Health Index (SHI), degradation tracking, and predictive indicators."""
    __tablename__ = "sensor_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("stations.station_id", ondelete="CASCADE"), index=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    health_score: Mapped[float] = mapped_column(Float, nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    anomaly_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    drift_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    data_quality_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    degradation_risk: Mapped[str] = mapped_column(String(32), default="STABLE", nullable=False)
    estimated_hours_to_failure: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    station: Mapped[Station] = relationship("Station", back_populates="sensor_health_records")

    __table_args__ = (
        Index("ix_sensor_health_station_timestamp", "station_id", "timestamp"),
    )


class ModelRun(Base):
    """Metadata, hyperparameters, and evaluation benchmark metrics for trained models."""
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_model_runs_name_version", "model_name", "version"),
    )
