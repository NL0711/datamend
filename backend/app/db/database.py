"""
backend/app/db/database.py
DataMend — async database engine, sessionmaker and lifecycle for the rainfall validation platform.

Written for SQLite now and PostgreSQL later (generic column types only). On the Render free tier SQLite resets on restart.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from sqlite3 import Connection as SQLite3Connection
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.app.config import settings

logger = logging.getLogger(__name__)

is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Ensure the data directory exists if a relative/absolute sqlite path is used
if is_sqlite and settings.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
    db_raw_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if db_raw_path and not db_raw_path.startswith(":memory:"):
        Path(db_raw_path).parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy 2.0 ORM models."""
    pass


engine_kwargs = {"echo": False, "pool_pre_ping": True}
if is_sqlite:
    # timeout (s) is honoured by aiosqlite for the underlying sqlite3 connect; with WAL + busy_timeout it reduces "database is locked".
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
        """SQLite pragmas for concurrency, durability and referential integrity."""
        if isinstance(dbapi_connection, SQLite3Connection) or hasattr(dbapi_connection, "cursor"):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.execute("PRAGMA busy_timeout=30000;")
            finally:
                cursor.close()


async_session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an isolated AsyncSession per request."""
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


def _add_missing_nullable_columns(sync_conn) -> list:
    """``create_all`` creates missing tables but never alters one, so an existing database would break on a model that gained a column. Add
    each missing NULLABLE column with ALTER TABLE ... ADD COLUMN (safe on SQLite and PostgreSQL, no data touched). A non-nullable column, a
    rename or a type change needs a real migration (``alembic upgrade head``) and is left alone. Returns the 'table.column' names added."""
    from sqlalchemy import inspect, text
    insp = inspect(sync_conn)
    existing = set(insp.get_table_names())
    added = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have or not col.nullable or col.primary_key:
                continue
            ddl = col.type.compile(dialect=sync_conn.dialect)
            sync_conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
            added.append(f"{table.name}.{col.name}")
    return added


async def init_db() -> None:
    """Creates the validation platform tables (validation_runs, validation_results, validation_check_hits, explanations) if missing.
    No data is seeded: the platform stores only what a user uploads or the live feed polls."""
    from backend.app.validation import models as _validation_models  # noqa: F401  (registers the tables)
    from backend.app.pipeline import models as _pipeline_models  # noqa: F401  (raw store, jobs, proposals, labels, registry)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        added = await conn.run_sync(_add_missing_nullable_columns)
    if added:
        logger.info("Added missing nullable columns to existing tables: %s (alembic upgrade head is the full migration path)", ", ".join(added))
    if not is_sqlite:
        from backend.app.pipeline.store import ensure_timescale
        done = await ensure_timescale(engine)
        if done:
            logger.info("Timescale set up: %s", ", ".join(done))
    logger.info("Validation platform tables are ready.")


async def close_db() -> None:
    """Disposes the database connection pool on application shutdown."""
    await engine.dispose()
    logger.info("Database connection pool closed.")
