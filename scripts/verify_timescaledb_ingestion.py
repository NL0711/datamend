"""
scripts/verify_timescaledb_ingestion.py
Verification script: Replays sample historical records into TimescaleDB and verifies persistence.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root directory to sys.path so 'backend' is resolved without PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure DATABASE_URL points to the dockerized TimescaleDB
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/datamend"

from backend.app.db.database import get_db, init_db
from backend.app.db.models import Observation, Station
from backend.app.ml.tier0_screener import tier0_screener
from sqlalchemy import select, func


async def test_timescaledb_pipeline():
    print("[1/4] Initializing TimescaleDB connection...")
    await init_db()

    async for session in get_db():
        # Verify seeded stations
        res = await session.execute(select(Station.station_id))
        stations = [r[0] for r in res.fetchall()]
        print(f"[2/4] Found {len(stations)} pre-seeded stations: {stations}")
        assert "AWS-001" in stations, "AWS-001 must be pre-seeded in database."

        # Simulate screening and saving an observation with Tier 0 flag
        print("[3/4] Screening and inserting test observation into observations hypertable...")
        raw_telemetry = {
            "temperature": 28.5,
            "pressure": 1012.3,
            "humidity": 65.0,
            "latitude": 28.6139,
            "longitude": 77.2090,
            "elevation": 216.0,
        }
        t0_res = tier0_screener.screen("AWS-001", raw_telemetry)

        now = datetime.now(timezone.utc)
        obs = Observation(
            station_id="AWS-001",
            timestamp=now,
            temperature=raw_telemetry["temperature"],
            pressure=raw_telemetry["pressure"],
            humidity=raw_telemetry["humidity"],
            validation_status="VALID" if t0_res.status != "REJECTED" else "INVALID",
            tier0_flag=t0_res.flag,
            source_type="HISTORICAL_REPLAY",
            source_id="historical_replay",
            provider="historical_timescale_replay",
        )
        session.add(obs)
        await session.commit()

        # Query back observation
        print("[4/4] Querying persisted observation back from TimescaleDB...")
        stmt = select(Observation).where(Observation.station_id == "AWS-001").order_by(Observation.timestamp.desc()).limit(1)
        res = await session.execute(stmt)
        saved = res.scalar_one_or_none()
        assert saved is not None, "Observation was not found in TimescaleDB."
        print(f"SUCCESS: Persisted observation retrieved: station={saved.station_id}, temp={saved.temperature}, tier0_flag={saved.tier0_flag}, timestamp={saved.timestamp}")
        break


if __name__ == "__main__":
    asyncio.run(test_timescaledb_pipeline())
