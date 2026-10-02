"""
scripts/audit_tool.py
Empirical Audit Collector for SkyGuard AI.
Collects runtime evidence, database stats, model execution traces, API responses, and WebSocket frames.
"""

import os
import sys
import sqlite3
import time
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

def audit_database():
    db_path = root_dir / "skyguard.db"
    print("=" * 80)
    print("1. DATABASE AUDIT")
    print("=" * 80)
    if not db_path.exists():
        print(f"[FAIL] SQLite database not found at {db_path}")
        return
    
    print(f"Database Path: {db_path} ({db_path.stat().st_size:,} bytes)")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"Tables Detected ({len(tables)}): {tables}")
    
    for t in tables:
        if not t.startswith("sqlite_"):
            cursor.execute(f"SELECT count(*) FROM {t}")
            cnt = cursor.fetchone()[0]
            print(f"  - {t:<20}: {cnt:>6} rows")
            
    print("\n--- Latest 3 Observations ---")
    cursor.execute("SELECT id, station_id, timestamp, temperature, pressure, humidity, validation_status FROM observations ORDER BY id DESC LIMIT 3")
    for row in cursor.fetchall():
        print(" ", row)

    print("\n--- Latest 3 Anomaly Events ---")
    cursor.execute("SELECT id, station_id, timestamp, is_anomaly, anomaly_score, severity, classification, is_fault, reason FROM anomaly_events ORDER BY id DESC LIMIT 3")
    for row in cursor.fetchall():
        print(" ", row)

    print("\n--- Latest 3 Sensor Health Entries ---")
    cursor.execute("SELECT id, station_id, timestamp, health_score, health_status, anomaly_rate, drift_score FROM sensor_health ORDER BY id DESC LIMIT 3")
    for row in cursor.fetchall():
        print(" ", row)

    print("\n--- Registered Stations ---")
    cursor.execute("SELECT id, station_id, name, elevation, status FROM stations")
    for row in cursor.fetchall():
        print(" ", row)

    conn.close()

def audit_models():
    print("\n" + "=" * 80)
    print("2. ML MODELS & PIPELINE AUDIT")
    print("=" * 80)
    models_dir = root_dir / "models"
    files = list(models_dir.glob("*"))
    print(f"Model Artifacts in {models_dir} ({len(files)} files):")
    for f in files:
        print(f"  - {f.name:<28}: {f.stat().st_size:>8,} bytes")

    from backend.app.ml.pipeline import SkyGuardPipeline
    print("\nInitializing master SkyGuardPipeline...")
    t0 = time.perf_counter()
    pipeline = SkyGuardPipeline(model_dir=models_dir)
    init_ms = (time.perf_counter() - t0) * 1000.0
    print(f"Pipeline initialized in {init_ms:.2f} ms")

    # Test 1: Clean observation
    obs_clean = {
        "timestamp": "2026-08-25T00:00:00Z",
        "station_id": "AWS-001",
        "temperature": 22.5,
        "pressure": 1013.25,
        "humidity": 55.0,
        "elevation": 216.0
    }
    t0 = time.perf_counter()
    res_clean = pipeline.process_observation(obs_clean)
    lat_clean = (time.perf_counter() - t0) * 1000.0
    print(f"\n[Test 1 Clean Input]: {obs_clean['temperature']}°C, {obs_clean['pressure']}hPa, {obs_clean['humidity']}%")
    print(f"  Result: is_anomaly={res_clean.is_anomaly}, score={res_clean.anomaly_score:.4f}, confidence={res_clean.confidence:.2f}, classification={res_clean.classification}")
    print(f"  Tier Scores: {res_clean.tier_scores}")
    print(f"  Sensor Health: {res_clean.sensor_health}%, Status: {res_clean.sensor_status}")
    print(f"  Latency: {lat_clean:.2f} ms")

    # Test 2: Injected 55°C Thermal Spike
    obs_spike = {
        "timestamp": "2026-08-25T00:05:00Z",
        "station_id": "AWS-001",
        "temperature": 55.0,
        "pressure": 1013.25,
        "humidity": 55.0,
        "elevation": 216.0
    }
    t0 = time.perf_counter()
    res_spike = pipeline.process_observation(obs_spike)
    lat_spike = (time.perf_counter() - t0) * 1000.0
    print(f"\n[Test 2 Spike Input]: {obs_spike['temperature']}°C (Thermal Surge)")
    print(f"  Result: is_anomaly={res_spike.is_anomaly}, score={res_spike.anomaly_score:.4f}, severity={res_spike.severity}, classification={res_spike.classification}")
    print(f"  Tier Scores: {res_spike.tier_scores}")
    print(f"  SHAP Explanation: {res_spike.explanation.summary}")
    print(f"  Contributing Features: {[f.feature + ': ' + str(round(f.attribution, 3)) for f in res_spike.explanation.contributing_features]}")
    print(f"  Sensor Health: {res_spike.sensor_health}%, Status: {res_spike.sensor_status}")
    print(f"  Latency: {lat_spike:.2f} ms")

def audit_simulator_and_ingestion():
    print("\n" + "=" * 80)
    print("3. SIMULATOR & INGESTION TRACE AUDIT")
    print("=" * 80)
    from backend.simulator.diurnal_generator import DiurnalGenerator, StationConfig
    from backend.simulator.anomaly_injector import AnomalyInjector
    
    st = StationConfig(station_id="AWS-001", name="Test Station", elevation=216.0)
    gen = DiurnalGenerator(station_config=st, seed=42)
    df_sim = gen.generate(duration_days=0.5, sampling_interval_min=5.0)
    print(f"DiurnalGenerator produced {len(df_sim)} rows.")
    print("Sample generated telemetry head (3 rows):")
    for _, r in df_sim.head(3).iterrows():
        print(f"  {r['timestamp']} | T={r['temperature']:.2f}°C, P={r['pressure']:.2f}hPa, RH={r['humidity']:.2f}%")

if __name__ == "__main__":
    audit_database()
    audit_models()
    audit_simulator_and_ingestion()
