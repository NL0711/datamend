"""Feed history: every reading the live gauge feed receives, kept across restarts and trimmed to a retention window.

A module with a small interface (append, recent, prune, state, close) and one implementation on SQLAlchemy that runs on two databases:
a local SQLite file (default, no account needed) and PostgreSQL through ``FEED_HISTORY_URL`` (Tiger Cloud, with TimescaleDB). On PostgreSQL the
table is turned into a hypertable when the TimescaleDB extension is there; otherwise it stays a plain table and the state says so.

The history has its OWN engine and its own table, apart from the runs database (Supabase when deployed). Nothing here ever raises into the feed:
a store that cannot be reached is reported by ``state()`` ("unavailable" with the reason) and the feed carries on from memory.
Times are the time the platform RECEIVED the reading (the provider gives none). Values are stored as the provider sent them, units UNCONFIRMED.
Kept per reading (owner's choice, 2026-11-20): the rain fields only, no raw response and no verdict. Retention is 90 days by the owner's
choice, a setting (``FEED_HISTORY_RETENTION_DAYS``); it is not a measured need.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, delete, select, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.app.db.database import engine_options
from backend.app.rainfall.weather_union import RainObservation

logger = logging.getLogger(__name__)

PRUNE_EVERY = timedelta(hours=6)
_metadata = MetaData()
feed_readings = Table(
    "feed_readings", _metadata,
    Column("station_id", String(64), primary_key=True),
    Column("received_at", DateTime(timezone=True), primary_key=True),      # part of the key: a hypertable needs the time column in it
    Column("rain_intensity", Float, nullable=True),
    Column("rain_accumulation", Float, nullable=True),
    Column("status", String(16), nullable=False),
    Column("device_type", Integer, nullable=True),
)


@dataclass
class HistoryState:
    available: bool
    backend: str                          # what holds the history, in plain words
    retention_days: int
    reason: Optional[str] = None          # why it is unavailable
    hypertable: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


class SqlFeedHistory:
    """The feed history on a SQLite file or a PostgreSQL database (see the module note)."""

    def __init__(self, url: str, retention_days: int = 90) -> None:
        self.url = url
        self.retention_days = max(1, retention_days)
        self._engine: AsyncEngine = create_async_engine(url, **engine_options(url, pool_size=2, max_overflow=1))
        self._dialect = self._engine.dialect.name
        self._ready = False
        self._hypertable = False
        self._last_prune: Optional[datetime] = None
        self._state = HistoryState(False, self._label(), self.retention_days, "not connected yet")

    def _label(self) -> str:
        if self._dialect == "sqlite":
            return "local SQLite file"
        return "PostgreSQL (TimescaleDB hypertable)" if self._hypertable else "PostgreSQL (plain table, no TimescaleDB hypertable)"

    def state(self) -> HistoryState:
        return self._state

    def _ok(self) -> None:
        self._state = HistoryState(True, self._label(), self.retention_days, None, self._hypertable)

    def _fail(self, e: Exception) -> None:
        reason = f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else 'no detail'}"
        if self._state.available or self._state.reason != reason:
            logger.warning("[FEED HISTORY] store unavailable: %s", reason)
        self._state = HistoryState(False, self._label(), self.retention_days, reason, self._hypertable)

    async def _setup(self) -> None:
        if self._ready:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)
        if self._dialect == "postgresql":
            try:
                async with self._engine.begin() as conn:
                    await conn.execute(text("SELECT create_hypertable('feed_readings', 'received_at', if_not_exists => TRUE)"))
                self._hypertable = True
            except SQLAlchemyError as e:             # no TimescaleDB extension here: a plain table still works
                logger.info("[FEED HISTORY] not a hypertable: %s", str(e).splitlines()[0][:160])
        self._ready = True

    async def append(self, observations: Sequence[RainObservation]) -> None:
        """Store readings; a reading already stored (same station and time) is left alone. Never raises."""
        if not observations:
            return
        rows = [{"station_id": o.station_id, "received_at": _utc(o.observed_at), "rain_intensity": o.rain_intensity,
                 "rain_accumulation": o.rain_accumulation, "status": o.status, "device_type": o.device_type} for o in observations]
        try:
            await self._setup()
            insert = postgresql.insert if self._dialect == "postgresql" else sqlite.insert
            async with self._engine.begin() as conn:
                await conn.execute(insert(feed_readings).on_conflict_do_nothing(), rows)
            self._ok()
            now = datetime.now(timezone.utc)
            if self._last_prune is None or now - self._last_prune >= PRUNE_EVERY:
                await self.prune(now)
        except (SQLAlchemyError, OSError) as e:
            self._fail(e)

    async def recent(self, station_id: str, limit: int) -> List[RainObservation]:
        """The newest ``limit`` readings of a station, oldest first. Empty when the store cannot be read."""
        try:
            await self._setup()
            async with self._engine.connect() as conn:
                result = await conn.execute(select(feed_readings).where(feed_readings.c.station_id == station_id)
                                            .order_by(feed_readings.c.received_at.desc()).limit(limit))
                rows = result.all()
            self._ok()
        except (SQLAlchemyError, OSError) as e:
            self._fail(e)
            return []
        return [RainObservation(r.station_id, _utc(r.received_at), r.device_type, r.rain_intensity, r.rain_accumulation, r.status)
                for r in reversed(rows)]

    async def prune(self, now: Optional[datetime] = None) -> int:
        """Delete readings older than the retention window. Returns how many (0 when the store cannot be reached)."""
        now = now or datetime.now(timezone.utc)
        try:
            await self._setup()
            async with self._engine.begin() as conn:
                result = await conn.execute(delete(feed_readings).where(feed_readings.c.received_at < now - timedelta(days=self.retention_days)))
            self._last_prune = now
            self._ok()
            return int(result.rowcount or 0)
        except (SQLAlchemyError, OSError) as e:
            self._fail(e)
            return 0

    async def close(self) -> None:
        await self._engine.dispose()


def build_feed_history(url: str, retention_days: int, local_path: str) -> SqlFeedHistory:
    """The store named by ``FEED_HISTORY_URL``, or a local SQLite file when it is empty."""
    if url.strip():
        return SqlFeedHistory(url.strip(), retention_days)
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    return SqlFeedHistory("sqlite+aiosqlite:///" + Path(local_path).as_posix(), retention_days)
