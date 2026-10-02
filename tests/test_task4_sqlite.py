"""
tests/test_task4_sqlite.py
OpenSpec task4-parity-closeout, capability sqlite-truth (tasks 4.1-4.3).

Proves SQLite is the working default: no server required, full default
path runs on it, and Timescale-specific DDL stays fenced to the
PostgreSQL path.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient

from backend.app.config import settings
from backend.app.db import database as db_module
from backend.app.db.database import init_db


def test_default_database_url_is_sqlite():
    """4.2: default configuration resolves to SQLite with no server."""
    assert settings.DATABASE_URL.startswith("sqlite"), (
        f"default DATABASE_URL must be SQLite, got {settings.DATABASE_URL!r}"
    )
    assert db_module.is_sqlite is True


@pytest.mark.asyncio
async def test_init_db_idempotent_without_server():
    """4.1/4.3: schema init runs with no database server, twice in a row."""
    await init_db()
    await init_db()


@pytest.mark.asyncio
async def test_default_path_end_to_end_on_sqlite(async_client: AsyncClient):
    """4.1: fresh-clone default flow (stations, ingest, query, health) on SQLite."""
    stations = await async_client.get("/api/stations")
    assert stations.status_code == 200
    assert stations.json()["total"] >= 1

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "station_id": "AWS-SQLITE-001",
        "temperature": 23.5,
        "pressure": 1011.0,
        "humidity": 62.0,
    }
    ingested = await async_client.post("/api/telemetry/live", json=payload)
    assert ingested.status_code == 201

    obs = await async_client.get(
        "/api/observations", params={"station_id": "AWS-SQLITE-001", "page_size": 5}
    )
    assert obs.status_code == 200
    assert obs.json()["total"] >= 1

    anomalies = await async_client.get("/api/anomalies", params={"page_size": 5})
    assert anomalies.status_code == 200

    health = await async_client.get("/api/health")
    assert health.status_code == 200

    alerts = await async_client.get("/api/alerts", params={"limit": 5})
    assert alerts.status_code == 200


def test_timescale_ddl_fenced_to_postgres_path():
    """4.3: hypertable/extension DDL only executes when not on SQLite."""
    source = Path("backend/app/db/database.py").read_text(encoding="utf-8")
    fence = source.index("if not is_sqlite:")
    for marker in ("create_hypertable", "CREATE EXTENSION", "timescaledb"):
        assert source.index(marker) > fence, (
            f"{marker!r} must stay inside the non-SQLite fence"
        )

    backend_refs = [
        p for p in Path("backend").rglob("*.py")
        if "init_timescaledb" in p.read_text(encoding="utf-8")
    ]
    assert backend_refs == [], (
        "init_timescaledb.sql must only run via docker entrypoint, "
        f"never imported by backend code: {backend_refs}"
    )
