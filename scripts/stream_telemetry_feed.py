"""
scripts/stream_telemetry_feed.py
Real-Time Telemetry Feeder & Interactive Anomaly Testing Tool for DataMend / SkyGuard AI.
Streams telemetry into TimescaleDB and populates:
1. observations (TimescaleDB Hypertable)
2. anomaly_events (Faults & Anomaly attributions)
3. sensor_health (Dynamic Sensor Health Index)
4. stations (Station health and connection states)

Usage:
    python -m scripts.stream_telemetry_feed --source replay --ticks 10 --delay 0.5
    python -m scripts.stream_telemetry_feed --source replay --continuous --delay 1.0
    python -m scripts.stream_telemetry_feed --source open-meteo --ticks 5
    python -m scripts.stream_telemetry_feed --source inject-anomaly --station AWS-001
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root directory to sys.path so 'backend' is resolved without PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Point default database URL to the local Dockerized TimescaleDB
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/datamend")

from backend.app.db.database import get_db, init_db
from backend.app.db.models import AnomalyEvent, Observation, SensorHealth, Station
from backend.app.ml.tier0_screener import tier0_screener, Tier0Result
from backend.app.sources.replay_source import HistoricalReplayDataSource
from backend.app.sources.external_source import ExternalWeatherDataSource
from backend.app.schemas.canonical import CanonicalTelemetry
from sqlalchemy import select, update


async def save_telemetry_packet(session, canonical: CanonicalTelemetry, t0_res: Tier0Result) -> Dict[str, Any]:
    """Saves a screened telemetry record across observations, anomaly_events, and sensor_health."""
    now = datetime.now(timezone.utc)
    dt_obs = datetime.fromisoformat(canonical.timestamp.replace("Z", "+00:00")) if isinstance(canonical.timestamp, str) else now

    # 1. Ensure Station Record Exists
    stmt = select(Station).where(Station.station_id == canonical.station_id)
    res = await session.execute(stmt)
    st = res.scalar_one_or_none()
    if not st:
        st = Station(
            station_id=canonical.station_id,
            name=f"Automated Station {canonical.station_id}",
            latitude=canonical.latitude or 28.6139,
            longitude=canonical.longitude or 77.2090,
            elevation=canonical.elevation or 200.0,
            status="ACTIVE",
        )
        session.add(st)
        await session.flush()

    # 2. Insert into observations hypertable
    is_rejected = t0_res.status == "REJECTED"
    is_suspicious = t0_res.status == "SUSPICIOUS"
    obs = Observation(
        station_id=canonical.station_id,
        timestamp=dt_obs,
        temperature=canonical.temperature,
        pressure=canonical.pressure,
        humidity=canonical.humidity,
        validation_status="VALID" if not (is_rejected or is_suspicious) else ("REJECTED" if is_rejected else "SUSPICIOUS"),
        tier0_flag=t0_res.flag,
        source_type=canonical.source_type.value if hasattr(canonical.source_type, "value") else str(canonical.source_type),
        source_id=canonical.source_id,
        provider=canonical.provider or "datamend",
        device_id=canonical.device_id,
    )
    session.add(obs)
    await session.flush()

    anomaly_created = False
    # 3. If Tier 0 flagged an anomaly, write to anomaly_events
    if is_rejected or is_suspicious:
        severity = "HIGH" if is_rejected else "MEDIUM"
        anom = AnomalyEvent(
            observation_id=obs.id,
            station_id=canonical.station_id,
            timestamp=dt_obs,
            is_anomaly=True,
            anomaly_score=0.95 if is_rejected else 0.70,
            confidence=0.90,
            severity=severity,
            anomaly_type=t0_res.flag,
            classification=t0_res.flag,
            is_fault=True,
            source_type=obs.source_type,
            source_id=obs.source_id,
            reason=f"Tier 0 Deterministic Trigger: {t0_res.reason}",
            explanation={"screener": "tier0_screener", "flag": t0_res.flag, "details": t0_res.reason},
            tier_scores={"tier0_score": 1.0 if is_rejected else 0.7, "flag": t0_res.flag},
            recommended_action="Inspect hardware sensor calibration and cable continuity." if is_rejected else "Monitor station for persistent sensor drift.",
            raw_values={"temperature": canonical.temperature, "pressure": canonical.pressure, "humidity": canonical.humidity},
        )
        session.add(anom)
        anomaly_created = True

    # 4. Compute & update SensorHealth record
    health_score = 100.0
    health_status = "EXCELLENT"
    degradation_risk = "STABLE"

    if is_rejected:
        health_score = 45.0
        health_status = "CRITICAL"
        degradation_risk = "HIGH"
    elif is_suspicious:
        health_score = 75.0
        health_status = "DEGRADED"
        degradation_risk = "ELEVATED"

    health = SensorHealth(
        station_id=canonical.station_id,
        timestamp=dt_obs,
        health_score=health_score,
        health_status=health_status,
        anomaly_rate=0.2 if anomaly_created else 0.0,
        drift_score=0.15 if is_suspicious else 0.0,
        data_quality_score=health_score,
        degradation_risk=degradation_risk,
        estimated_hours_to_failure=48.0 if is_rejected else None,
        recommended_action="Recalibrate / replace sensor unit" if is_rejected else "Nominal",
    )
    session.add(health)

    # 5. Update station status
    st.status = "CRITICAL" if is_rejected else ("DEGRADED" if is_suspicious else "ACTIVE")
    await session.commit()

    return {
        "station_id": canonical.station_id,
        "timestamp": dt_obs.isoformat(),
        "temperature": canonical.temperature,
        "pressure": canonical.pressure,
        "humidity": canonical.humidity,
        "tier0_flag": t0_res.flag,
        "status": t0_res.status,
        "anomaly": anomaly_created,
        "health": health_score,
    }


async def run_replay_feed(ticks: int = 10, delay: float = 0.5, continuous: bool = False):
    """Streams data from the 30-day historical benchmark into TimescaleDB."""
    csv_file = Path("data/historical_benchmark_30d.csv")
    if not csv_file.exists():
        print(f"[!] Benchmark file not found at {csv_file}. Generating now...")
        from scripts.generate_replay_dataset import generate_benchmark_dataset
        generate_benchmark_dataset(str(csv_file), days=30)

    print(f"\n[*] Starting Historical Replay Feed ({csv_file.name})...")
    print(f"[*] Target DB: {os.environ['DATABASE_URL']}")
    print("-" * 75)

    source = HistoricalReplayDataSource(
        csv_path=str(csv_file),
        replay_speed=0.0,
        loop_playback=True,
    )
    total_recs = source.load_dataset()
    print(f"[+] Loaded {total_recs} records ({len(source._sorted_timestamps)} distinct ticks).")

    tick_count = 0
    saved_total = 0
    anomalies_total = 0

    async for session in get_db():
        while True:
            if not continuous and tick_count >= ticks:
                break
            if source._current_index >= len(source._sorted_timestamps):
                source._current_index = 0

            ts = source._sorted_timestamps[source._current_index]
            readings = source._records_by_timestamp.get(ts, [])

            print(f"\n--- Tick {tick_count + 1} | Timestamp: {ts} | Emitting {len(readings)} stations ---")
            for r in readings:
                sid = r["station_id"]
                t0_res = tier0_screener.screen(sid, r)
                canonical = CanonicalTelemetry(
                    station_id=sid,
                    timestamp=ts,
                    temperature=t0_res.telemetry.get("temperature"),
                    pressure=t0_res.telemetry.get("pressure"),
                    humidity=t0_res.telemetry.get("humidity"),
                    latitude=r.get("latitude"),
                    longitude=r.get("longitude"),
                    elevation=r.get("elevation"),
                    source_type=source.source_type,
                    source_id=source.source_id,
                    provider="historical_timescale_replay",
                    tier0_flag=t0_res.flag,
                    received_at=datetime.now(timezone.utc).isoformat(),
                )
                res = await save_telemetry_packet(session, canonical, t0_res)
                saved_total += 1
                anom_marker = " [ANOMALY DETECTED -> anomaly_events]" if res["anomaly"] else ""
                print(f"  > [{res['station_id']}] T={res['temperature']:5.1f}°C | P={res['pressure']:6.1f}hPa | H={res['humidity']:4.1f}% | Tier0={res['tier0_flag']:<15} | SHI={res['health']:.0f}%{anom_marker}")
                if res["anomaly"]:
                    anomalies_total += 1

            source._current_index += 1
            tick_count += 1
            if delay > 0:
                await asyncio.sleep(delay)

        print("-" * 75)
        print(f"[+] Replay stream completed: {saved_total} observations persisted, {anomalies_total} anomaly events logged.")
        print("[+] Check pgAdmin (http://localhost:5050) -> tables: observations, anomaly_events, sensor_health.")
        break


async def run_open_meteo_feed(ticks: int = 5, delay: float = 2.0):
    """Fetches real-time observations from Open-Meteo REST API and persists into TimescaleDB."""
    print(f"\n[*] Starting Open-Meteo Live API Feed...")
    cities = [
        {"id": "PUNE-EXT-001", "name": "Pune", "lat": 18.5204, "lon": 73.8567},
        {"id": "DELHI-EXT-001", "name": "Delhi", "lat": 28.6139, "lon": 77.2090},
        {"id": "MUMBAI-EXT-001", "name": "Mumbai", "lat": 18.9220, "lon": 72.8347},
    ]

    async for session in get_db():
        for t in range(ticks):
            print(f"\n--- Open-Meteo Polling Round {t + 1}/{ticks} ---")
            for city in cities:
                adapter = ExternalWeatherDataSource(
                    latitude=city["lat"],
                    longitude=city["lon"],
                    station_id=city["id"],
                    station_name=city["name"],
                )
                try:
                    telemetry = await adapter.fetch_live_observation()
                    reading_dict = {
                        "temperature": telemetry.temperature,
                        "pressure": telemetry.pressure,
                        "humidity": telemetry.humidity,
                    }
                    t0_res = tier0_screener.screen(telemetry.station_id, reading_dict)
                    res = await save_telemetry_packet(session, telemetry, t0_res)
                    print(f"  > [{city['id']} - {city['name']}] T={res['temperature']}°C | P={res['pressure']}hPa | H={res['humidity']}% | Tier0={res['tier0_flag']} | SHI={res['health']:.0f}%")
                except Exception as e:
                    print(f"  [!] Error fetching {city['name']}: {e}")
            if delay > 0 and t < ticks - 1:
                await asyncio.sleep(delay)
        break


async def inject_synthetic_anomaly(station_id: str = "AWS-001", anomaly_type: str = "spike"):
    """Injects a high-severity test anomaly into TimescaleDB to immediately trigger anomaly_events."""
    print(f"\n[*] Injecting test {anomaly_type.upper()} anomaly into station [{station_id}]...")
    async for session in get_db():
        if anomaly_type == "spike":
            tier0_screener.screen(station_id, {"temperature": 25.0, "pressure": 1010.0, "humidity": 50.0})
            t_val, p_val, h_val = 52.0, 1010.0, 20.0  # +27 deg sudden spike -> STEP_SPIKE
        elif anomaly_type == "dropout":
            t_val, p_val, h_val = None, 1010.0, 50.0  # Null sensor dropout -> NULL_DROPOUT
        else:
            t_val, p_val, h_val = 85.0, 600.0, 120.0  # Exceeds physical bounds -> OUT_OF_RANGE

        raw_reading = {"temperature": t_val, "pressure": p_val, "humidity": h_val}
        t0_res = tier0_screener.screen(station_id, raw_reading)

        canonical = CanonicalTelemetry(
            station_id=station_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            temperature=t_val,
            pressure=p_val,
            humidity=h_val,
            source_type="SIMULATED",
            source_id="manual_test_injector",
            provider="manual_testing",
            tier0_flag=t0_res.flag,
        )
        res = await save_telemetry_packet(session, canonical, t0_res)
        print(f"[+] Injected record: station={station_id}, flag={res['tier0_flag']}, anomaly_created={res['anomaly']}, health={res['health']}%")
        print("[+] Check pgAdmin table 'anomaly_events' to see the newly logged fault record!")
        break


async def async_main(args):
    await init_db()

    if args.source == "replay":
        await run_replay_feed(ticks=args.ticks, delay=args.delay, continuous=args.continuous)
    elif args.source == "open-meteo":
        await run_open_meteo_feed(ticks=args.ticks, delay=args.delay)
    elif args.source == "inject":
        await inject_synthetic_anomaly(station_id=args.station, anomaly_type=args.type)


def main():
    parser = argparse.ArgumentParser(description="DataMend Live Telemetry Feeder & Testing Utility")
    parser.add_argument("--source", choices=["replay", "open-meteo", "inject"], default="replay", help="Telemetry source")
    parser.add_argument("--ticks", type=int, default=10, help="Number of ticks/rounds to stream")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay in seconds between ticks")
    parser.add_argument("--continuous", action="store_true", help="Run continuously until Ctrl+C")
    parser.add_argument("--station", type=str, default="AWS-001", help="Target station for injection")
    parser.add_argument("--type", choices=["spike", "dropout", "out_of_bounds"], default="spike", help="Anomaly type to inject")
    args = parser.parse_args()

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
