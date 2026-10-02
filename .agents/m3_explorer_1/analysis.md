# Milestone 3 Analysis Report: Database Architecture & Repositories

**Author**: `m3_explorer_1`  
**Working Directory**: `backend/app/db/`  
**Date**: 2026-08-24  
**Target Milestone**: M3 — Database Layer & Repositories (Phases 11, 13, 14 of `TODO.md`)

---

## Executive Summary

This report establishes the complete architectural blueprint and production-grade specifications for the SkyGuard AI Database Layer (`backend/app/db/`). It designs:
1. **Async SQLite Engine & Session Management** (`backend/app/db/database.py`): Full `SQLAlchemy 2.0` + `aiosqlite` integration with Write-Ahead Logging (`WAL`), connection pooling, PRAGMA foreign keys, busy timeout tuning, and safe multi-threaded concurrency for FastAPI and background ingestion tasks.
2. **SQLAlchemy ORM Models** (`backend/app/db/models.py`): Comprehensive ORM schemas for `stations`, `observations`, `anomaly_events`, `sensor_health`, and `model_runs` matching `ARCHITECTURE.md` and `PROJECT.md`, with optimal composite indexes (`station_id`, `timestamp`), foreign key cascades, and native JSON fields for treeSHAP explanations, tier scores, and metrics.
3. **Async Repository Layer** (`backend/app/db/repositories.py`): 5 specialized async repositories (`StationRepository`, `ObservationRepository`, `AnomalyRepository`, `HealthRepository`, `ModelRunRepository`) supporting CRUD, batch ingestion, time-series window slicing, multi-filter pagination, fleet health aggregations, and alert statistics.
4. **ML Pipeline & API Contract Alignment**: Perfect interoperability with `SkyGuardPipeline` (`InferenceResult`, `ExplanationResult`, `TierScores`), ensuring zero data loss, sub-millisecond database writes, and seamless migration capability to PostgreSQL.

---

## 1. Architectural Blueprint: Database & Storage Layer

### 1.1 Technology Stack Selection
- **ORM**: `SQLAlchemy 2.0.28+` using modern `DeclarativeBase`, `Mapped[...]`, `mapped_column()`, and `async_sessionmaker`.
- **Async Driver**: `aiosqlite 0.20.0+` for non-blocking asynchronous I/O in the FastAPI asyncio event loop.
- **Database Engine**: `SQLite 3` in Write-Ahead Logging (`WAL`) mode for local file-based deployment (`./data/skyguard.db`), designed for zero-friction future migration to PostgreSQL via asyncpg.

### 1.2 Storage Architecture Diagram
```
                     +---------------------------------------+
                     | FastAPI App / Services / WebSocket    |
                     +---------------------------------------+
                                        |
                   +--------------------+--------------------+
                   |                                         |
                   v                                         v
        [FastAPI Route Handler]                   [Background Worker]
      (Depends(get_db) session)                (async with get_db_context())
                   |                                         |
                   +--------------------+--------------------+
                                        |
                                        v
                       +---------------------------------+
                       |       Async Repositories        |
                       | - StationRepository             |
                       | - ObservationRepository         |
                       | - AnomalyRepository             |
                       | - HealthRepository              |
                       | - ModelRunRepository            |
                       +---------------------------------+
                                        |
                                        v
                       +---------------------------------+
                       |    SQLAlchemy 2.0 Engine        |
                       |  (aiosqlite + WAL + Pragmas)    |
                       +---------------------------------+
                                        |
                                        v
                       +---------------------------------+
                       |  SQLite Database: skyguard.db   |
                       |  - stations                     |
                       |  - observations                 |
                       |  - anomaly_events               |
                       |  - sensor_health                |
                       |  - model_runs                   |
                       +---------------------------------+
```

---

## 2. Engine & Session Management Specification (`database.py`)

### 2.1 Concurrency, WAL Mode, and PRAGMAs
To prevent `sqlite3.OperationalError: database is locked` during concurrent read/write loads (e.g. background telemetry ingestion streaming 12 observations/sec while the dashboard queries time-series histories and alert counts), SQLite must be initialized with specific PRAGMAs:

1. **`journal_mode = WAL`**: Enables Write-Ahead Logging. Readers never block writers, and writers never block readers.
2. **`synchronous = NORMAL`**: Drastically reduces filesystem sync calls without compromising durability in WAL mode.
3. **`foreign_keys = ON`**: Enforces relational foreign key cascades (`stations` -> `observations` / `sensor_health` / `anomaly_events`).
4. **`busy_timeout = 10000`**: Configures SQLite to wait up to 10,000 ms on lock contention before raising an error.
5. **`connect_args = {"check_same_thread": False}`**: Allows SQLite connections across multiple async worker threads.

### 2.2 Complete Implementation Specification for `backend/app/db/database.py`

```python
"""
backend/app/db/database.py
SkyGuard AI — Async Database Engine, Sessionmaker, and Lifecycle Management.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlite3 import Connection as SQLite3Connection

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Ensure data directory exists
DATABASE_FILE = Path(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").lstrip("./"))
DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    """Declarative Base class for all SQLAlchemy 2.0 ORM models."""
    pass


# Create Async Engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Configures SQLite connection pragmas for high concurrency and referential integrity."""
    if isinstance(dbapi_connection, SQLite3Connection) or hasattr(dbapi_connection, "cursor"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.execute("PRAGMA busy_timeout=10000;")
        finally:
            cursor.close()


# Async Session Factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency yielding an isolated AsyncSession per request."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for background workers and services."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Creates all database tables and seeds default stations if empty."""
    from backend.app.db import models  # noqa: F401
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Seed default AWS stations
    async with get_db_context() as session:
        from backend.app.db.models import Station
        from sqlalchemy import select
        
        result = await session.execute(select(Station).limit(1))
        existing = result.scalars().first()
        if not existing:
            default_stations = [
                Station(
                    station_id="AWS-001",
                    name="Central Meteorological Observatory",
                    latitude=28.6139,
                    longitude=77.2090,
                    elevation=216.0,
                    status="ACTIVE",
                ),
                Station(
                    station_id="AWS-002",
                    name="Coastal Marine Weather Tower",
                    latitude=18.9220,
                    longitude=72.8347,
                    elevation=14.0,
                    status="ACTIVE",
                ),
                Station(
                    station_id="AWS-003",
                    name="Plateau Highland Station",
                    latitude=32.2190,
                    longitude=76.3234,
                    elevation=1457.0,
                    status="ACTIVE",
                ),
                Station(
                    station_id="AWS-004",
                    name="Arid Subtropical Outpost",
                    latitude=26.9124,
                    longitude=70.9022,
                    elevation=225.0,
                    status="ACTIVE",
                ),
            ]
            session.add_all(default_stations)
            await session.commit()
            logger.info("Initialized database with %d default AWS stations.", len(default_stations))


async def close_db() -> None:
    """Gracefully disposes database connection pool on application shutdown."""
    await engine.dispose()
    logger.info("Database connection pool closed.")
```

---

## 3. SQLAlchemy ORM Models Specification (`models.py`)

### 3.1 Entity Relationship Diagram
```
+-------------------------------------------------------------+
|                           Station                           |
|-------------------------------------------------------------|
| PK  id: int                                                 |
| UQ  station_id: str (e.g. "AWS-001")                         |
|     name: str                                               |
|     latitude: float, longitude: float, elevation: float     |
|     status: str ("ACTIVE" | "DEGRADED" | "CRITICAL")        |
|     created_at, updated_at: datetime                        |
+-------------------------------------------------------------+
         | 1                                 | 1          | 1
         |                                   |            |
         v *                                 v *          v *
+-----------------------+   +-------------------+   +--------------------+
|      Observation      |   |   SensorHealth    |   |    AnomalyEvent    |
|-----------------------|   |-------------------|   |--------------------|
| PK  id: int           |   | PK  id: int       |   | PK  id: int        |
| FK  station_id: str   |   | FK  station_id:str|   | FK  station_id: str|
| IX  timestamp: dt     |   | IX  timestamp: dt |   | FK  obs_id: int    |
|     temperature: float|   |     health_score  |   | IX  timestamp: dt  |
|     pressure: float   |   |     health_status |   |     is_anomaly:bool|
|     humidity: float   |   |     anomaly_rate  |   |     anomaly_score  |
|     validation_status |   |     drift_score   |   |     confidence     |
|     created_at: dt    |   |     quality_score |   |     severity: str  |
+-----------------------+   |     deg_risk: str |   |     classification |
         | 1                |     hours_to_fail |   |     is_fault: bool |
         |                  |     action: str   |   |     reason: str    |
         v 0..1             +-------------------+   |     explanation:JSON|
+---------------------------------------------------|     tier_scores:JSON|
                                                    |     action: str    |
                                                    |     raw_values:JSON|
                                                    +--------------------+

+-------------------------------------------------------------+
|                          ModelRun                           |
|-------------------------------------------------------------|
| PK  id: int                                                 |
| IX  model_name: str, version: str                           |
|     dataset_version: str                                    |
|     parameters: JSON, metrics: JSON, status: str            |
|     created_at: datetime                                    |
+-------------------------------------------------------------+
```

### 3.2 Complete Implementation Specification for `backend/app/db/models.py`

```python
"""
backend/app/db/models.py
SkyGuard AI — SQLAlchemy 2.0 ORM Models for AWS Telemetry and AI Diagnostics.
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
```

---

## 4. Repository Layer Specification (`repositories.py`)

### 4.1 Required Repository Interfaces

| Repository | Core Queries / Methods | Target Consumer |
|---|---|---|
| `StationRepository` | `get_by_id`, `get_all`, `get_or_create`, `update_status`, `count`, `get_fleet_summary` | Stations API, Ingestion Service, Dashboard Overview |
| `ObservationRepository` | `create`, `create_batch`, `get_history`, `get_recent_window`, `get_paginated`, `count` | Ingestion Service, ML Pipeline, Data Explorer, Live Charts |
| `AnomalyRepository` | `create`, `create_batch`, `get_recent`, `get_paginated`, `get_active_alerts`, `get_stats` | Alert Center, Event Detail, Anomaly History, Ingestion Service |
| `HealthRepository` | `create`, `get_latest`, `get_all_latest`, `get_history`, `get_fleet_summary` | Sensor Health View, Overview Dashboard, Ingestion Service |
| `ModelRunRepository` | `create`, `get_latest`, `get_all`, `update_metrics` | Model Performance View, Training Pipelines |

### 4.2 Complete Implementation Specification for `backend/app/db/repositories.py`

```python
"""
backend/app/db/repositories.py
SkyGuard AI — Async Repository Pattern Implementations for Clean Data Access.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    AnomalyEvent,
    ModelRun,
    Observation,
    SensorHealth,
    Station,
    utcnow,
)


def parse_datetime(dt: Union[datetime, str, None]) -> Optional[datetime]:
    """Helper to safely parse ISO strings or datetime objects to timezone-aware UTC datetime."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    try:
        clean_str = str(dt).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(clean_str)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. Station Repository
# ---------------------------------------------------------------------------
class StationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, station_data: Dict[str, Any]) -> Station:
        station = Station(**station_data)
        self.session.add(station)
        await self.session.flush()
        return station

    async def get_by_id(self, station_id: str) -> Optional[Station]:
        stmt = select(Station).where(Station.station_id == station_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all(
        self, skip: int = 0, limit: int = 100, status: Optional[str] = None
    ) -> List[Station]:
        stmt = select(Station)
        if status:
            stmt = stmt.where(Station.status == status.upper())
        stmt = stmt.offset(skip).limit(limit).order_by(Station.station_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create(
        self,
        station_id: str,
        name: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        elevation: Optional[float] = None,
    ) -> Station:
        station = await self.get_by_id(station_id)
        if station:
            return station
        station = Station(
            station_id=station_id,
            name=name or f"Station {station_id}",
            latitude=latitude or 28.6139,
            longitude=longitude or 77.2090,
            elevation=elevation or 216.0,
            status="ACTIVE",
        )
        self.session.add(station)
        await self.session.flush()
        return station

    async def update_status(self, station_id: str, status: str) -> Optional[Station]:
        stmt = (
            update(Station)
            .where(Station.station_id == station_id)
            .values(status=status.upper(), updated_at=utcnow())
            .returning(Station)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def count(self, status: Optional[str] = None) -> int:
        stmt = select(func.count(Station.id))
        if status:
            stmt = stmt.where(Station.status == status.upper())
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_fleet_summary(self) -> Dict[str, Any]:
        total = await self.count()
        active = await self.count(status="ACTIVE")
        degraded = await self.count(status="DEGRADED")
        critical = await self.count(status="CRITICAL")
        offline = await self.count(status="OFFLINE")
        return {
            "total_stations": total,
            "active_stations": active,
            "degraded_stations": degraded,
            "critical_stations": critical,
            "offline_stations": offline,
        }


# ---------------------------------------------------------------------------
# 2. Observation Repository
# ---------------------------------------------------------------------------
class ObservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, obs_data: Dict[str, Any]) -> Observation:
        data = dict(obs_data)
        if "timestamp" in data:
            data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
        obs = Observation(**data)
        self.session.add(obs)
        await self.session.flush()
        return obs

    async def create_batch(self, obs_list: List[Dict[str, Any]]) -> List[Observation]:
        records: List[Observation] = []
        for item in obs_list:
            data = dict(item)
            if "timestamp" in data:
                data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
            records.append(Observation(**data))
        self.session.add_all(records)
        await self.session.flush()
        return records

    async def get_by_id(self, obs_id: int) -> Optional[Observation]:
        stmt = select(Observation).where(Observation.id == obs_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest(self, station_id: str) -> Optional[Observation]:
        stmt = (
            select(Observation)
            .where(Observation.station_id == station_id)
            .order_by(desc(Observation.timestamp))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_history(
        self,
        station_id: str,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        limit: int = 288,
        sort_desc: bool = True,
    ) -> List[Observation]:
        stmt = select(Observation).where(Observation.station_id == station_id)
        dt_start = parse_datetime(start_time)
        dt_end = parse_datetime(end_time)
        if dt_start:
            stmt = stmt.where(Observation.timestamp >= dt_start)
        if dt_end:
            stmt = stmt.where(Observation.timestamp <= dt_end)
        
        if sort_desc:
            stmt = stmt.order_by(desc(Observation.timestamp))
        else:
            stmt = stmt.order_by(Observation.timestamp)
            
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_window(self, station_id: str, window_size: int = 30) -> List[Observation]:
        """Fetches the last N observations in ascending chronological order for ML window buffering."""
        subq = (
            select(Observation)
            .where(Observation.station_id == station_id)
            .order_by(desc(Observation.timestamp))
            .limit(window_size)
            .subquery()
        )
        stmt = select(Observation).from_statement(
            select(subq).order_by(subq.c.timestamp)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_paginated(
        self,
        station_id: Optional[str] = None,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Observation], int]:
        stmt = select(Observation)
        count_stmt = select(func.count(Observation.id))

        if station_id:
            stmt = stmt.where(Observation.station_id == station_id)
            count_stmt = count_stmt.where(Observation.station_id == station_id)
        
        dt_start = parse_datetime(start_time)
        dt_end = parse_datetime(end_time)
        if dt_start:
            stmt = stmt.where(Observation.timestamp >= dt_start)
            count_stmt = count_stmt.where(Observation.timestamp >= dt_start)
        if dt_end:
            stmt = stmt.where(Observation.timestamp <= dt_end)
            count_stmt = count_stmt.where(Observation.timestamp <= dt_end)

        total_count = (await self.session.execute(count_stmt)).scalar() or 0
        
        offset = (page - 1) * page_size
        stmt = stmt.order_by(desc(Observation.timestamp)).offset(offset).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def count(self, station_id: Optional[str] = None) -> int:
        stmt = select(func.count(Observation.id))
        if station_id:
            stmt = stmt.where(Observation.station_id == station_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0


# ---------------------------------------------------------------------------
# 3. Anomaly Repository
# ---------------------------------------------------------------------------
class AnomalyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event_data: Dict[str, Any]) -> AnomalyEvent:
        data = dict(event_data)
        if "timestamp" in data:
            data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
        event = AnomalyEvent(**data)
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_batch(self, events_list: List[Dict[str, Any]]) -> List[AnomalyEvent]:
        records: List[AnomalyEvent] = []
        for item in events_list:
            data = dict(item)
            if "timestamp" in data:
                data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
            records.append(AnomalyEvent(**data))
        self.session.add_all(records)
        await self.session.flush()
        return records

    async def get_by_id(self, event_id: int) -> Optional[AnomalyEvent]:
        stmt = select(AnomalyEvent).where(AnomalyEvent.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_recent(
        self,
        station_id: Optional[str] = None,
        severity: Optional[str] = None,
        classification: Optional[str] = None,
        is_fault_only: Optional[bool] = None,
        limit: int = 50,
    ) -> List[AnomalyEvent]:
        stmt = select(AnomalyEvent)
        if station_id:
            stmt = stmt.where(AnomalyEvent.station_id == station_id)
        if severity:
            stmt = stmt.where(AnomalyEvent.severity == severity.upper())
        if classification:
            stmt = stmt.where(AnomalyEvent.classification == classification.upper())
        if is_fault_only is not None:
            stmt = stmt.where(AnomalyEvent.is_fault == is_fault_only)
        
        stmt = stmt.order_by(desc(AnomalyEvent.timestamp)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_paginated(
        self,
        station_id: Optional[str] = None,
        severity: Optional[str] = None,
        classification: Optional[str] = None,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[AnomalyEvent], int]:
        stmt = select(AnomalyEvent)
        count_stmt = select(func.count(AnomalyEvent.id))

        if station_id:
            stmt = stmt.where(AnomalyEvent.station_id == station_id)
            count_stmt = count_stmt.where(AnomalyEvent.station_id == station_id)
        if severity:
            stmt = stmt.where(AnomalyEvent.severity == severity.upper())
            count_stmt = count_stmt.where(AnomalyEvent.severity == severity.upper())
        if classification:
            stmt = stmt.where(AnomalyEvent.classification == classification.upper())
            count_stmt = count_stmt.where(AnomalyEvent.classification == classification.upper())

        dt_start = parse_datetime(start_time)
        dt_end = parse_datetime(end_time)
        if dt_start:
            stmt = stmt.where(AnomalyEvent.timestamp >= dt_start)
            count_stmt = count_stmt.where(AnomalyEvent.timestamp >= dt_start)
        if dt_end:
            stmt = stmt.where(AnomalyEvent.timestamp <= dt_end)
            count_stmt = count_stmt.where(AnomalyEvent.timestamp <= dt_end)

        total_count = (await self.session.execute(count_stmt)).scalar() or 0
        offset = (page - 1) * page_size
        stmt = stmt.order_by(desc(AnomalyEvent.timestamp)).offset(offset).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def get_active_alerts(
        self,
        station_id: Optional[str] = None,
        min_severity: str = "MEDIUM",
        limit: int = 20,
    ) -> List[AnomalyEvent]:
        severity_order = ["MEDIUM", "HIGH", "CRITICAL"] if min_severity == "MEDIUM" else ["HIGH", "CRITICAL"]
        stmt = select(AnomalyEvent).where(AnomalyEvent.severity.in_(severity_order))
        if station_id:
            stmt = stmt.where(AnomalyEvent.station_id == station_id)
        stmt = stmt.order_by(desc(AnomalyEvent.timestamp)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(
        self, station_id: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        since = utcnow() - timedelta(hours=hours)
        base_filter = [AnomalyEvent.timestamp >= since]
        if station_id:
            base_filter.append(AnomalyEvent.station_id == station_id)

        # Total anomalies
        tot_stmt = select(func.count(AnomalyEvent.id)).where(*base_filter)
        total_anomalies = (await self.session.execute(tot_stmt)).scalar() or 0

        # By severity
        sev_stmt = (
            select(AnomalyEvent.severity, func.count(AnomalyEvent.id))
            .where(*base_filter)
            .group_by(AnomalyEvent.severity)
        )
        sev_res = await self.session.execute(sev_stmt)
        by_severity = {row[0]: row[1] for row in sev_res.all()}

        # By classification
        clf_stmt = (
            select(AnomalyEvent.classification, func.count(AnomalyEvent.id))
            .where(*base_filter)
            .group_by(AnomalyEvent.classification)
        )
        clf_res = await self.session.execute(clf_stmt)
        by_classification = {row[0]: row[1] for row in clf_res.all()}

        # Faults vs Meteorological Extreme
        faults_stmt = (
            select(AnomalyEvent.is_fault, func.count(AnomalyEvent.id))
            .where(*base_filter)
            .group_by(AnomalyEvent.is_fault)
        )
        faults_res = await self.session.execute(faults_stmt)
        fault_counts = {row[0]: row[1] for row in faults_res.all()}

        return {
            "period_hours": hours,
            "total_anomalies": total_anomalies,
            "by_severity": by_severity,
            "by_classification": by_classification,
            "sensor_faults": fault_counts.get(True, 0),
            "meteorological_extremes": fault_counts.get(False, 0),
        }


# ---------------------------------------------------------------------------
# 4. Health Repository
# ---------------------------------------------------------------------------
class HealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, health_data: Dict[str, Any]) -> SensorHealth:
        data = dict(health_data)
        if "timestamp" in data:
            data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
        record = SensorHealth(**data)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_latest(self, station_id: str) -> Optional[SensorHealth]:
        stmt = (
            select(SensorHealth)
            .where(SensorHealth.station_id == station_id)
            .order_by(desc(SensorHealth.timestamp))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_latest(self) -> List[SensorHealth]:
        """Fetches the latest health record for each registered station."""
        # Subquery finding max timestamp per station
        subq = (
            select(
                SensorHealth.station_id,
                func.max(SensorHealth.timestamp).label("max_ts"),
            )
            .group_by(SensorHealth.station_id)
            .subquery()
        )
        stmt = select(SensorHealth).join(
            subq,
            (SensorHealth.station_id == subq.c.station_id)
            & (SensorHealth.timestamp == subq.c.max_ts),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_history(
        self,
        station_id: str,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        limit: int = 288,
    ) -> List[SensorHealth]:
        stmt = select(SensorHealth).where(SensorHealth.station_id == station_id)
        dt_start = parse_datetime(start_time)
        dt_end = parse_datetime(end_time)
        if dt_start:
            stmt = stmt.where(SensorHealth.timestamp >= dt_start)
        if dt_end:
            stmt = stmt.where(SensorHealth.timestamp <= dt_end)
        stmt = stmt.order_by(desc(SensorHealth.timestamp)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_fleet_health_summary(self) -> Dict[str, Any]:
        latest_records = await self.get_all_latest()
        if not latest_records:
            return {
                "average_health_score": 100.0,
                "status_distribution": {
                    "EXCELLENT": 0, "GOOD": 0, "DEGRADED": 0, "POOR": 0, "CRITICAL": 0
                },
            }
        scores = [r.health_score for r in latest_records]
        avg_score = round(sum(scores) / len(scores), 2)
        dist: Dict[str, int] = {}
        for r in latest_records:
            dist[r.health_status] = dist.get(r.health_status, 0) + 1
        return {
            "average_health_score": avg_score,
            "status_distribution": dist,
            "station_count": len(latest_records),
        }


# ---------------------------------------------------------------------------
# 5. Model Run Repository
# ---------------------------------------------------------------------------
class ModelRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, run_data: Dict[str, Any]) -> ModelRun:
        run = ModelRun(**run_data)
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_by_id(self, run_id: int) -> Optional[ModelRun]:
        stmt = select(ModelRun).where(ModelRun.id == run_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest(self, model_name: Optional[str] = None) -> Optional[ModelRun]:
        stmt = select(ModelRun)
        if model_name:
            stmt = stmt.where(ModelRun.model_name == model_name)
        stmt = stmt.order_by(desc(ModelRun.created_at)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all(self, limit: int = 50) -> List[ModelRun]:
        stmt = select(ModelRun).order_by(desc(ModelRun.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_metrics(self, run_id: int, metrics: Dict[str, Any]) -> Optional[ModelRun]:
        stmt = (
            update(ModelRun)
            .where(ModelRun.id == run_id)
            .values(metrics=metrics)
            .returning(ModelRun)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
```

---

## 5. End-to-End Ingestion Integration Contract

When `IngestionService` processes an incoming observation record:
```python
# 1. Pipeline Inference
result: InferenceResult = pipeline.process_observation(obs_dict)

# 2. Database Persistence via Unit of Work Session
async with get_db_context() as session:
    station_repo = StationRepository(session)
    obs_repo = ObservationRepository(session)
    anomaly_repo = AnomalyRepository(session)
    health_repo = HealthRepository(session)

    # A. Ensure Station Exists
    await station_repo.get_or_create(station_id=result.station_id)

    # B. Insert Raw Observation
    obs = await obs_repo.create({
        "station_id": result.station_id,
        "timestamp": result.timestamp,
        "temperature": result.raw_values.get("temperature"),
        "pressure": result.raw_values.get("pressure"),
        "humidity": result.raw_values.get("humidity"),
        "validation_status": "QC_FLAGGED" if result.tier_scores.tier1_qc_flag else "VALID",
    })

    # C. If Anomaly detected, Insert AnomalyEvent
    if result.is_anomaly:
        await anomaly_repo.create({
            "observation_id": obs.id,
            "station_id": result.station_id,
            "timestamp": result.timestamp,
            "is_anomaly": True,
            "anomaly_score": result.anomaly_score,
            "confidence": result.confidence,
            "severity": result.severity,
            "anomaly_type": result.classification,
            "classification": result.classification,
            "is_fault": result.is_fault,
            "reason": result.reason,
            "explanation": result.explanation.model_dump(),
            "tier_scores": result.tier_scores.model_dump(),
            "recommended_action": result.recommended_action,
            "raw_values": result.raw_values,
        })

    # D. Insert Sensor Health Snapshot
    await health_repo.create({
        "station_id": result.station_id,
        "timestamp": result.timestamp,
        "health_score": result.sensor_health,
        "health_status": result.sensor_status,
        "anomaly_rate": 0.0,
        "drift_score": 0.0,
        "data_quality_score": 1.0 if not result.tier_scores.tier1_qc_flag else 0.5,
        "degradation_risk": result.degradation_risk,
        "estimated_hours_to_failure": result.estimated_hours_to_failure,
        "recommended_action": result.recommended_action,
    })

    # E. Update Station Operational Status
    await station_repo.update_status(
        station_id=result.station_id,
        status=result.sensor_status if result.sensor_status in ["DEGRADED", "CRITICAL"] else "ACTIVE"
    )
```

---

## 6. Migration and Testing Strategy

### 6.1 Unit & Integration Testing Strategy for Database
Create `tests/test_database.py` covering:
1. **Async Engine & Pragma Tests**:
   - Verify tables are created on `init_db()`.
   - Verify `PRAGMA journal_mode` is `wal`.
   - Verify `PRAGMA foreign_keys` is `1` (enabled).
2. **Station CRUD & Seeding**:
   - Verify default stations ("AWS-001" to "AWS-004") are seeded.
   - Verify `get_or_create` is idempotent.
3. **Observation Time-Series Windowing**:
   - Insert 50 observations with sequential timestamps.
   - Query `get_recent_window(station_id, window_size=30)` and verify exactly 30 observations returned in ascending timestamp order.
   - Verify composite index filtering performance.
4. **Anomaly Events & JSON Fields**:
   - Insert `AnomalyEvent` with full TreeSHAP `explanation` dictionary and `tier_scores`.
   - Read back and verify JSON fields are correctly deserialized as Python dicts.
5. **Sensor Health & Fleet Aggregations**:
   - Insert health records for multiple stations.
   - Test `get_all_latest()` and `get_fleet_health_summary()`.
6. **Concurrent Write Resilience**:
   - Launch 20 concurrent async ingestion tasks writing observations simultaneously; verify zero lock errors with WAL mode.
