"""Writing the raw store: idempotent bulk inserts, and the Timescale set-up on PostgreSQL.

Re-ingesting a file is safe: a row with the same source, station and hour is skipped (never updated), so raw data is never overwritten.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.app.pipeline.models import Observation, PipelineStation

logger = logging.getLogger(__name__)

PG_CHUNK = 2000        # asyncpg allows 32,767 bound parameters per statement; 2,000 rows x 5 columns stays far below it


def _insert(session: AsyncSession, model):
    name = session.bind.dialect.name if session.bind is not None else "sqlite"
    if name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


async def insert_observations(session: AsyncSession, rows: Sequence[Dict[str, Any]]) -> None:
    """Insert hourly observations, skipping any (source, station_key, observed_at) already stored."""
    for start in range(0, len(rows), PG_CHUNK):
        chunk = list(rows[start:start + PG_CHUNK])
        if chunk:
            await session.execute(_insert(session, Observation).values(chunk).on_conflict_do_nothing())


async def upsert_stations(session: AsyncSession, stations: Sequence[Dict[str, Any]]) -> None:
    """Station metadata: the first sighting wins (a later file never moves a station)."""
    for start in range(0, len(stations), PG_CHUNK):
        chunk = list(stations[start:start + PG_CHUNK])
        if chunk:
            await session.execute(_insert(session, PipelineStation).values(chunk).on_conflict_do_nothing())


async def ensure_timescale(engine: AsyncEngine) -> List[str]:
    """On PostgreSQL with the TimescaleDB extension: make the observation table a hypertable and turn on compression. Best effort and
    safe to repeat; on SQLite or plain PostgreSQL it does nothing. Returns what it did (for the log). UNTESTED against a live Tiger service
    until the owner approves test tables (map ticket "Measure row size and compression")."""
    done: List[str] = []
    if engine.dialect.name != "postgresql":
        return done
    steps = [
        ("extension", "CREATE EXTENSION IF NOT EXISTS timescaledb"),
        ("hypertable", "SELECT create_hypertable('pipeline_observations', 'observed_at', if_not_exists => TRUE, migrate_data => TRUE)"),
        ("compression", "ALTER TABLE pipeline_observations SET (timescaledb.compress, timescaledb.compress_segmentby = 'source, station_key')"),
        ("compression_policy", "SELECT add_compression_policy('pipeline_observations', INTERVAL '7 days', if_not_exists => TRUE)"),
    ]
    for name, sql in steps:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
            done.append(name)
        except Exception as exc:                                   # not Timescale, no permission, or already set: never block start-up
            logger.warning("Timescale step %s skipped: %s", name, str(exc).splitlines()[0][:160])
            break
    return done
