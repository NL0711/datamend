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

# Ensure data directory exists if a relative/absolute sqlite path is used
if settings.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
    db_raw_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if db_raw_path and not db_raw_path.startswith(":memory:"):
        db_file = Path(db_raw_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)


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
    """Configures SQLite connection pragmas for high concurrency, durability, and referential integrity."""
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
    """Async context manager for background workers, services, and simulation loops."""
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
    """Creates all database tables, applies non-breaking schema migrations, and seeds default stations if empty."""
    from backend.app.db import models  # noqa: F401
    from sqlalchemy import text
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Check and safely add new columns to existing SQLite tables if missing
        migration_statements = [
            "ALTER TABLE observations ADD COLUMN source_type VARCHAR(32) DEFAULT 'SIMULATED';",
            "ALTER TABLE observations ADD COLUMN source_id VARCHAR(64);",
            "ALTER TABLE observations ADD COLUMN provider VARCHAR(64);",
            "ALTER TABLE observations ADD COLUMN device_id VARCHAR(64);",
            "ALTER TABLE anomaly_events ADD COLUMN source_type VARCHAR(32) DEFAULT 'SIMULATED';",
            "ALTER TABLE anomaly_events ADD COLUMN source_id VARCHAR(64);",
        ]
        for stmt in migration_statements:
            try:
                await conn.execute(text(stmt))
            except Exception:
                # Column already exists
                pass
    
    # Seed default AWS and City Preset stations if not present
    async with get_db_context() as session:
        from backend.app.db.models import Station
        from sqlalchemy import select
        
        seed_stations = [
            # Standard Regional Cluster
            {"station_id": "AWS-001", "name": "Central Meteorological Observatory (New Delhi)", "latitude": 28.6139, "longitude": 77.2090, "elevation": 216.0, "status": "ACTIVE"},
            {"station_id": "AWS-002", "name": "Coastal Marine Weather Tower (Mumbai)", "latitude": 18.9220, "longitude": 72.8347, "elevation": 14.0, "status": "ACTIVE"},
            {"station_id": "AWS-003", "name": "Plateau Highland Station (Dharamshala)", "latitude": 32.2190, "longitude": 76.3234, "elevation": 1457.0, "status": "ACTIVE"},
            {"station_id": "AWS-004", "name": "Arid Subtropical Outpost (Jaisalmer)", "latitude": 26.9124, "longitude": 70.9022, "elevation": 225.0, "status": "ACTIVE"},
            # Global & Regional Synoptic Reference Stations
            {"station_id": "PUNE-EXT-001", "name": "Pune Weather Observatory", "latitude": 18.5204, "longitude": 73.8567, "elevation": 560.0, "status": "ACTIVE"},
            {"station_id": "DELHI-EXT-001", "name": "New Delhi Safdarjung Synoptic Site", "latitude": 28.6139, "longitude": 77.2090, "elevation": 216.0, "status": "ACTIVE"},
            {"station_id": "LONDON-EXT-001", "name": "London Heathrow Synoptic Station", "latitude": 51.5074, "longitude": -0.1278, "elevation": 35.0, "status": "ACTIVE"},
            {"station_id": "TOKYO-EXT-001", "name": "Tokyo JMA Observation Station", "latitude": 35.6762, "longitude": 139.6503, "elevation": 40.0, "status": "ACTIVE"},
            {"station_id": "DV-EXT-001", "name": "Death Valley Furnace Creek Station", "latitude": 36.5323, "longitude": -116.9325, "elevation": -86.0, "status": "ACTIVE"},
        ]

        for s_data in seed_stations:
            result = await session.execute(select(Station).where(Station.station_id == s_data["station_id"]))
            existing = result.scalars().first()
            if not existing:
                st_obj = Station(**s_data)
                session.add(st_obj)
        
        await session.commit()
        logger.info("Validated and synchronized all AWS and Synoptic stations in database.")


async def close_db() -> None:
    """Gracefully disposes database connection pool on application shutdown."""
    await engine.dispose()
    logger.info("Database connection pool closed.")
