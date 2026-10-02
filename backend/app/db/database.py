"""
backend/app/db/database.py
DataMend — Async Database Engine, Sessionmaker, and Lifecycle Management.
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

is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Ensure data directory exists if a relative/absolute sqlite path is used
if is_sqlite and settings.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
    db_raw_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if db_raw_path and not db_raw_path.startswith(":memory:"):
        db_file = Path(db_raw_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    """Declarative Base class for all SQLAlchemy 2.0 ORM models."""
    pass


# Dialect-specific engine configurations
engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

# Create Async Engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)

if is_sqlite:
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
        
        # Check and safely add new columns if missing
        migration_statements = [
            "ALTER TABLE observations ADD COLUMN tier0_flag VARCHAR(32) DEFAULT 'PASS';",
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

        if not is_sqlite:
            # PostgreSQL / TimescaleDB hypertable and indexing
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
                await conn.execute(text(
                    "SELECT create_hypertable('observations', 'timestamp', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_obs_station_time ON observations (station_id, timestamp DESC);"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_obs_time_station ON observations (timestamp DESC, station_id);"
                ))
            except Exception as e:
                logger.warning("TimescaleDB extension or hypertable initialization note: %s", e)
    
    # Seed default AWS and City Preset stations if not present
    async with get_db_context() as session:
        from backend.app.db.models import Station
        from sqlalchemy import select
        
        seed_stations = [
            # NOAA NEXRAD Doppler Radar Surface Network (AWS Open Data)
            {"station_id": "KTLX", "name": "NOAA NEXRAD Radar KTLX (Oklahoma City, OK)", "latitude": 35.3331, "longitude": -97.2778, "elevation": 370.0, "status": "ACTIVE"},
            {"station_id": "KOKX", "name": "NOAA NEXRAD Radar KOKX (New York / Upton, NY)", "latitude": 40.8656, "longitude": -72.8628, "elevation": 20.0, "status": "ACTIVE"},
            {"station_id": "KAMX", "name": "NOAA NEXRAD Radar KAMX (Miami, FL)", "latitude": 25.6111, "longitude": -80.4128, "elevation": 4.0, "status": "ACTIVE"},
            {"station_id": "KATX", "name": "NOAA NEXRAD Radar KATX (Seattle, WA)", "latitude": 48.1947, "longitude": -122.4944, "elevation": 151.0, "status": "ACTIVE"},
            {"station_id": "KFWS", "name": "NOAA NEXRAD Radar KFWS (Dallas-Fort Worth, TX)", "latitude": 32.5731, "longitude": -97.3031, "elevation": 207.0, "status": "ACTIVE"},
            {"station_id": "KDMX", "name": "NOAA NEXRAD Radar KDMX (Des Moines, IA)", "latitude": 41.7311, "longitude": -93.7228, "elevation": 299.0, "status": "ACTIVE"},
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
