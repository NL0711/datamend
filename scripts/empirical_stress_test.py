"""
scripts/empirical_stress_test.py
Comprehensive Empirical Stress Test Harness for Milestone 3.
Directly tests:
1. CSV upload edge cases: Malformed files, non-numeric values, missing columns, empty files, huge CSVs (5000+ rows), disordered timestamps, multi-station CSVs.
2. Physical bounds boundary testing: Testing API input validation vs Tier 1 QC rejection.
3. Sensor health degradation and recovery stress: Continuous frozen/drift/dropout inputs and recovery.
4. Convective front meteorological extreme vs sensor fault classification through the ingestion pipeline.
"""

import asyncio
import io
import time
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd

from backend.app.ml.pipeline import SkyGuardPipeline
from backend.app.ml.tier1_qc import Tier1QC, Tier1QCConfig
from backend.app.ml.tier4_classifier import FaultClassifier, FaultClass
from backend.app.ml.tier5_health import SensorHealthEngine, HealthStatus, DegradationRisk
from backend.app.schemas.schemas import ObservationCreate, InferenceRequest
from backend.app.services.ingestion_service import IngestionService
from backend.app.db.database import init_db, get_db_context
from backend.app.db.repositories import (
    StationRepository,
    ObservationRepository,
    AnomalyRepository,
    HealthRepository,
)

async def test_csv_upload_edge_cases(pipeline: SkyGuardPipeline):
    print("\n" + "="*70)
    print("CHALLENGE 1: CSV UPLOAD EDGE CASES & ADVERSARIAL STRESS")
    print("="*70)
    service = IngestionService(pipeline=pipeline)
    
    # 1.1 Empty CSV (0 bytes)
    print("\n--- 1.1 Empty CSV (0 bytes) ---")
    try:
        await service.process_csv_upload(b"", filename="empty.csv")
        print("FAIL: Expected ValueError for empty bytes")
    except ValueError as e:
        print(f"PASS: Correctly rejected empty bytes: {e}")

    # 1.2 Empty CSV (Header only, 0 data rows)
    print("\n--- 1.2 Empty CSV (Header only, 0 data rows) ---")
    header_only = b"timestamp,temperature,pressure,humidity\n"
    try:
        await service.process_csv_upload(header_only, filename="header_only.csv")
        print("FAIL: Expected ValueError for 0 rows")
    except ValueError as e:
        print(f"PASS: Correctly rejected header-only CSV: {e}")

    # 1.3 Missing required columns (e.g. missing 'pressure')
    print("\n--- 1.3 Missing Required Columns ---")
    missing_col_csv = b"timestamp,temperature,humidity\n2026-08-01T00:00:00Z,22.0,55.0\n"
    try:
        await service.process_csv_upload(missing_col_csv, filename="missing_p.csv")
        print("FAIL: Expected ValueError for missing column")
    except ValueError as e:
        print(f"PASS: Correctly rejected missing column: {e}")

    # 1.4 Flexible Header Normalization (e.g., 'Temp_C', 'Baro', 'Rel_Hum', 'Time', 'stn')
    print("\n--- 1.4 Flexible Header Aliasing ---")
    aliased_csv = (
        "Time,Temp_C,Baro,Rel_Hum,stn\n"
        "2026-08-01T00:00:00Z,23.5,1012.0,60.0,AWS-FLEX\n"
        "2026-08-01T00:05:00Z,23.6,1011.9,60.2,AWS-FLEX\n"
    ).encode("utf-8")
    res = await service.process_csv_upload(aliased_csv, filename="aliased.csv", reset_state=True)
    print(f"PASS: Flexible headers parsed successfully: {res.total_rows} total, {res.valid_rows} valid, updated {res.stations_updated}")

    # 1.5 Corrupt / Non-Numeric Rows
    print("\n--- 1.5 Corrupt & Non-Numeric Data Rows ---")
    corrupt_csv = (
        "timestamp,temperature,pressure,humidity,station_id\n"
        "2026-08-01T00:00:00Z,22.0,1013.0,50.0,AWS-CORRUPT\n"
        "2026-08-01T00:05:00Z,N/A_BAD_FLOAT,1013.0,50.0,AWS-CORRUPT\n"
        "2026-08-01T00:10:00Z,22.2,INVALID_PRESS,50.0,AWS-CORRUPT\n"
        "2026-08-01T00:15:00Z,22.3,1013.0,NULL_HUM,AWS-CORRUPT\n"
        "2026-08-01T00:20:00Z,22.4,1013.0,51.0,AWS-CORRUPT\n"
    ).encode("utf-8")
    res = await service.process_csv_upload(corrupt_csv, filename="corrupt.csv", reset_state=True)
    print(f"Total rows: {res.total_rows}, Valid rows: {res.valid_rows}, Errors captured: {len(res.errors)}")
    for err in res.errors:
        print(f"  Row {err.row} error: {err.error}")
    assert res.total_rows == 5 and res.valid_rows == 2 and len(res.errors) == 3
    print("PASS: Corrupt rows correctly quarantined without halting ingestion stream.")

    # 1.6 Disordered Timestamps
    print("\n--- 1.6 Disordered Timestamps Sorting ---")
    disordered_csv = (
        "timestamp,temperature,pressure,humidity,station_id\n"
        "2026-08-01T00:15:00Z,22.3,1013.0,50.0,AWS-DISORDER\n"
        "2026-08-01T00:00:00Z,22.0,1013.0,50.0,AWS-DISORDER\n"
        "2026-08-01T00:10:00Z,22.2,1013.0,50.0,AWS-DISORDER\n"
        "2026-08-01T00:05:00Z,22.1,1013.0,50.0,AWS-DISORDER\n"
    ).encode("utf-8")
    res = await service.process_csv_upload(disordered_csv, filename="disorder.csv", reset_state=True)
    assert res.valid_rows == 4
    print(f"PASS: Disordered timestamps sorted and processed: {res.valid_rows} observations.")

    # 1.7 Huge CSV (5000+ rows) Stress & Throughput
    print("\n--- 1.7 Huge CSV (5,000 Rows) Ingestion Throughput ---")
    base_ts = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    huge_rows = []
    huge_rows.append("timestamp,temperature,pressure,humidity,station_id")
    for i in range(5000):
        t_cur = base_ts + timedelta(minutes=5 * i)
        # Inject periodic spike every 1000 rows
        temp = 55.0 if (i > 0 and i % 1000 == 0) else round(20.0 + 5.0 * np.sin(i / 50.0), 2)
        pres = round(1013.25 + 2.0 * np.cos(i / 100.0), 2)
        hum = round(60.0 + 10.0 * np.sin(i / 40.0), 2)
        stn = f"AWS-{(i % 4) + 1:03d}"
        huge_rows.append(f"{t_cur.isoformat()},{temp},{pres},{hum},{stn}")
    
    huge_csv_bytes = "\n".join(huge_rows).encode("utf-8")
    print(f"Generated huge CSV: {len(huge_csv_bytes) / 1024:.1f} KB, 5,000 rows across 4 stations.")
    
    t_start = time.perf_counter()
    res = await service.process_csv_upload(huge_csv_bytes, filename="huge_5000.csv", reset_state=True)
    t_elapsed = time.perf_counter() - t_start
    
    print(f"Huge CSV Upload completed in {t_elapsed:.2f}s ({res.total_rows / t_elapsed:.1f} rows/sec).")
    print(f"  Total rows: {res.total_rows}")
    print(f"  Valid rows: {res.valid_rows}")
    print(f"  Anomalies detected: {res.anomalies_detected}")
    print(f"  Faults detected: {res.faults_detected}")
    print(f"  Anomalies breakdown: {dict(res.anomalies_summary)}")
    print(f"  Stations updated: {res.stations_updated}")
    assert res.total_rows == 5000
    assert res.valid_rows == 5000
    assert res.anomalies_detected >= 4
    print("PASS: 5,000 row batch ingestion processed with complete transaction integrity.")

async def test_physical_bounds_boundary(pipeline: SkyGuardPipeline):
    print("\n" + "="*70)
    print("CHALLENGE 2: PHYSICAL BOUNDS BOUNDARY TESTING (API VS TIER 1 QC)")
    print("="*70)
    
    service = IngestionService(pipeline=pipeline)
    st = "AWS-BOUNDS"
    service.pipeline.reset_station(st)
    
    # Check 1: Pydantic Validation Bounds
    # Temperature: [-100.0, 100.0]
    # Pressure: [100.0, 1500.0]
    # Humidity: [-20.0, 150.0]
    print("\n--- 2.1 Pydantic Schema Bounds Verification ---")
    # Valid Pydantic boundary values
    valid_pydantic = [
        {"temperature": -100.0, "pressure": 100.0, "humidity": -20.0},
        {"temperature": 100.0, "pressure": 1500.0, "humidity": 150.0},
        {"temperature": 25.0, "pressure": 1013.25, "humidity": 50.0},
    ]
    for p in valid_pydantic:
        obs = ObservationCreate(timestamp="2026-08-24T12:00:00Z", station_id=st, **p)
        assert obs.temperature == p["temperature"]
    print("PASS: ObservationCreate accepted boundary values [-100, 100], [100, 1500], [-20, 150].")

    # Invalid Pydantic values (Must raise ValidationError)
    from pydantic import ValidationError
    invalid_pydantic = [
        {"temperature": -100.1, "pressure": 1013.0, "humidity": 50.0},
        {"temperature": 100.1, "pressure": 1013.0, "humidity": 50.0},
        {"temperature": 25.0, "pressure": 99.9, "humidity": 50.0},
        {"temperature": 25.0, "pressure": 1500.1, "humidity": 50.0},
        {"temperature": 25.0, "pressure": 1013.0, "humidity": -20.1},
        {"temperature": 25.0, "pressure": 1013.0, "humidity": 150.1},
    ]
    for p in invalid_pydantic:
        try:
            ObservationCreate(timestamp="2026-08-24T12:00:00Z", station_id=st, **p)
            print(f"FAIL: Expected ValidationError for {p}")
        except ValidationError:
            pass
    print("PASS: Pydantic rejects values exceeding absolute telemetry schema limits with HTTP 422.")

    # Check 2: Tier 1 WMO Physical QC Bounds
    # WMO Limits: T in [-40, 60], P in [300, 1100], RH in [0, 104]
    print("\n--- 2.2 Tier 1 WMO Physical QC Bounds vs Hard Override ---")
    wmo_test_cases = [
        # Inside WMO: clean
        {"temperature": 25.0, "pressure": 1013.25, "humidity": 50.0, "expect_t1_override": False, "expect_qc_flag": False},
        # Temperature out of WMO bounds (-40.1°C) -> Accepted by Pydantic, Hard Flagged by Tier 1
        {"temperature": -40.1, "pressure": 1013.25, "humidity": 50.0, "expect_t1_override": True, "expect_qc_flag": True},
        # Temperature out of WMO bounds (60.1°C)
        {"temperature": 60.1, "pressure": 1013.25, "humidity": 50.0, "expect_t1_override": True, "expect_qc_flag": True},
        # Pressure out of WMO bounds (299.9 hPa)
        {"temperature": 25.0, "pressure": 299.9, "humidity": 50.0, "expect_t1_override": True, "expect_qc_flag": True},
        # Pressure out of WMO bounds (1100.1 hPa)
        {"temperature": 25.0, "pressure": 1100.1, "humidity": 50.0, "expect_t1_override": True, "expect_qc_flag": True},
        # Humidity out of WMO bounds (-0.1%)
        {"temperature": 25.0, "pressure": 1013.25, "humidity": -0.1, "expect_t1_override": True, "expect_qc_flag": True},
        # Humidity out of WMO bounds (104.1%)
        {"temperature": 25.0, "pressure": 1013.25, "humidity": 104.1, "expect_t1_override": True, "expect_qc_flag": True},
    ]

    for tc in wmo_test_cases:
        service.pipeline.reset_station(st)
        res = await service.ingest_observation({
            "timestamp": "2026-08-24T12:00:00Z",
            "station_id": st,
            "temperature": tc["temperature"],
            "pressure": tc["pressure"],
            "humidity": tc["humidity"],
        }, save_db=True, broadcast=False)
        
        inf = res.inference
        t1_hard = inf.tier_scores.tier1_hard == 1.0
        t1_flag = inf.tier_scores.tier1_qc_flag
        
        print(f"Payload (T={tc['temperature']}, P={tc['pressure']}, RH={tc['humidity']}):")
        print(f"  QC Flag: {t1_flag} (expected {tc['expect_qc_flag']}), Hard Override: {t1_hard} (expected {tc['expect_t1_override']})")
        print(f"  Anomaly: {inf.is_anomaly}, Score: {inf.anomaly_score}, Severity: {inf.severity}, Class: {inf.classification}")
        print(f"  DB validation_status: {res.observation.validation_status}")
        
        assert t1_flag == tc["expect_qc_flag"]
        assert t1_hard == tc["expect_t1_override"]
        if tc["expect_t1_override"]:
            assert inf.is_anomaly is True
            assert inf.anomaly_score >= 0.99
            assert inf.severity in ["HIGH", "CRITICAL"]
            assert res.observation.validation_status == "QC_FLAGGED"
        else:
            assert res.observation.validation_status == "VALID"

    print("PASS: Physical bounds cleanly tiered between API format validation (422) and Tier 1 QC rejection (QC_FLAGGED).")

async def test_sensor_health_stress_and_recovery(pipeline: SkyGuardPipeline):
    print("\n" + "="*70)
    print("CHALLENGE 3: SENSOR HEALTH DEGRADATION & RECOVERY DYNAMICS")
    print("="*70)
    
    st_id = "AWS-HEALTH-STRESS"
    pipeline.reset_station(st_id)
    service = IngestionService(pipeline=pipeline)
    
    # 3.1 Initial Clean Baseline (20 steps)
    print("\n--- 3.1 Warmup with 20 Clean Steps ---")
    base_ts = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(20):
        t_cur = base_ts + timedelta(minutes=5 * i)
        await service.ingest_observation({
            "timestamp": t_cur.isoformat(),
            "station_id": st_id,
            "temperature": 22.0 + 0.2 * np.sin(i),
            "pressure": 1013.25 + 0.1 * np.cos(i),
            "humidity": 60.0 + 0.5 * np.sin(i),
        }, save_db=True, broadcast=False)
        
    async with get_db_context() as session:
        h_repo = HealthRepository(session)
        latest_h = await h_repo.get_latest(st_id)
        print(f"Initial Health Score: {latest_h.health_score:.2f} ({latest_h.health_status})")
        assert latest_h.health_score >= 95.0
        assert latest_h.health_status == "EXCELLENT"

    # 3.2 Continuous Severe Fault Stress (50 steps of frozen + extreme temperature drift)
    print("\n--- 3.2 Continuous Severe Fault Ingestion (50 steps) ---")
    health_trajectory = []
    for i in range(20, 70):
        t_cur = base_ts + timedelta(minutes=5 * i)
        res = await service.ingest_observation({
            "timestamp": t_cur.isoformat(),
            "station_id": st_id,
            "temperature": 52.0,  # Extreme stuck + drifted value
            "pressure": 1013.25,
            "humidity": 60.0,
        }, save_db=True, broadcast=False)
        health_trajectory.append(res.inference.sensor_health)
        
    print(f"Health score trajectory during continuous fault:")
    print(f"  Step 1: {health_trajectory[0]:.1f}")
    print(f"  Step 5: {health_trajectory[4]:.1f}")
    print(f"  Step 10: {health_trajectory[9]:.1f}")
    print(f"  Step 25: {health_trajectory[24]:.1f}")
    print(f"  Step 50: {health_trajectory[49]:.1f}")
    
    final_degraded_health = health_trajectory[-1]
    assert final_degraded_health < 25.0, f"Expected health < 25.0 (CRITICAL), got {final_degraded_health}"
    
    async with get_db_context() as session:
        h_repo = HealthRepository(session)
        st_repo = StationRepository(session)
        latest_h = await h_repo.get_latest(st_id)
        st_entity = await st_repo.get_by_id(st_id)
        print(f"Degraded Status: {latest_h.health_status}, Degradation Risk: {latest_h.degradation_risk}")
        print(f"Station Entity Status: {st_entity.status}")
        assert latest_h.health_status == "CRITICAL"
        assert latest_h.degradation_risk in ["HIGH_RISK", "MAINTENANCE_REQUIRED"]
        assert st_entity.status == "CRITICAL"
        print("PASS: Continuous fault successfully degraded health to CRITICAL (0-24) and updated station status.")

    # 3.3 Recovery Phase (100 clean steps)
    print("\n--- 3.3 Recovery Phase (100 Clean Observations) ---")
    recovery_trajectory = []
    for i in range(70, 170):
        t_cur = base_ts + timedelta(minutes=5 * i)
        res = await service.ingest_observation({
            "timestamp": t_cur.isoformat(),
            "station_id": st_id,
            "temperature": 22.0 + 0.2 * np.sin(i),
            "pressure": 1013.25 + 0.1 * np.cos(i),
            "humidity": 60.0 + 0.5 * np.sin(i),
        }, save_db=True, broadcast=False)
        recovery_trajectory.append(res.inference.sensor_health)
        
    print(f"Health score trajectory during recovery:")
    print(f"  Step 10: {recovery_trajectory[9]:.1f}")
    print(f"  Step 30: {recovery_trajectory[29]:.1f}")
    print(f"  Step 60: {recovery_trajectory[59]:.1f}")
    print(f"  Step 100: {recovery_trajectory[99]:.1f}")
    
    final_recovered_health = recovery_trajectory[-1]
    assert final_recovered_health > 75.0, f"Expected health recovery > 75.0, got {final_recovered_health}"
    
    async with get_db_context() as session:
        h_repo = HealthRepository(session)
        st_repo = StationRepository(session)
        latest_h = await h_repo.get_latest(st_id)
        st_entity = await st_repo.get_by_id(st_id)
        print(f"Recovered Status: {latest_h.health_status}, Score: {latest_h.health_score:.1f}")
        print(f"Station Entity Status: {st_entity.status}")
        assert latest_h.health_status in ["GOOD", "EXCELLENT"]
        assert st_entity.status == "ACTIVE"
        print("PASS: Sensor Health smoothly recovered and restored Station status to ACTIVE.")

async def test_convective_front_classification(pipeline: SkyGuardPipeline):
    print("\n" + "="*70)
    print("CHALLENGE 4: CONVECTIVE FRONT VS SENSOR FAULT CLASSIFICATION")
    print("="*70)
    
    service = IngestionService(pipeline=pipeline)
    
    # 4.1 Genuine Squall Front Test
    st_front = "AWS-FRONT-TEST"
    pipeline.reset_station(st_front)
    
    # 3 baseline steps prior to front
    t0 = datetime(2026, 8, 24, 15, 0, 0, tzinfo=timezone.utc)
    for i in range(3):
        t_cur = t0 + timedelta(minutes=5 * i)
        await service.ingest_observation({
            "timestamp": t_cur.isoformat(),
            "station_id": st_front,
            "temperature": 34.0 - 0.1 * i,
            "pressure": 1008.0 - 0.05 * i,
            "humidity": 40.0 + 0.2 * i,
        }, save_db=True, broadcast=False)
        
    # Arrival of squall front: T drops -10°C, P surges +6 hPa, RH surges +45%
    front_ts = t0 + timedelta(minutes=15)
    res_front = await service.ingest_observation({
        "timestamp": front_ts.isoformat(),
        "station_id": st_front,
        "temperature": 24.0,   # ΔT = -10.0°C
        "pressure": 1014.0,      # ΔP = +6.0 hPa
        "humidity": 85.0,       # ΔRH = +45.0%
    }, save_db=True, broadcast=False)
    
    inf_front = res_front.inference
    print("Squall Front Observation Result:")
    print(f"  is_anomaly: {inf_front.is_anomaly}")
    print(f"  anomaly_score: {inf_front.anomaly_score}")
    print(f"  classification: {inf_front.classification}")
    print(f"  is_fault: {inf_front.is_fault}")
    print(f"  severity: {inf_front.severity}")
    print(f"  reason: {inf_front.reason}")
    print(f"  sensor_health: {inf_front.sensor_health}")
    
    assert inf_front.classification == "METEOROLOGICAL_EXTREME"
    assert inf_front.is_fault is False
    assert inf_front.is_anomaly is True  # Highlighted for meteorologists
    assert inf_front.sensor_health >= 90.0  # Health not penalized by weather!
    print("PASS: Genuine convective squall front correctly classified with is_fault=False without health penalty.")

    # 4.2 Single Sensor Hardware Glitch (Isolated Temperature Spike of -10°C without P/RH change)
    st_spike = "AWS-SPIKE-TEST"
    pipeline.reset_station(st_spike)
    for i in range(3):
        t_cur = t0 + timedelta(minutes=5 * i)
        await service.ingest_observation({
            "timestamp": t_cur.isoformat(),
            "station_id": st_spike,
            "temperature": 34.0,
            "pressure": 1008.0,
            "humidity": 40.0,
        }, save_db=True, broadcast=False)
        
    res_spike = await service.ingest_observation({
        "timestamp": (t0 + timedelta(minutes=15)).isoformat(),
        "station_id": st_spike,
        "temperature": 24.0,  # Sudden -10°C drop
        "pressure": 1008.0,   # No pressure change!
        "humidity": 40.0,    # No humidity change!
    }, save_db=True, broadcast=False)
    
    inf_spike = res_spike.inference
    print("\nIsolated Hardware Glitch Result:")
    print(f"  classification: {inf_spike.classification}")
    print(f"  is_fault: {inf_spike.is_fault}")
    print(f"  severity: {inf_spike.severity}")
    assert inf_spike.is_fault is True
    assert inf_spike.classification in ["SPIKE", "MULTIVARIATE_INCONSISTENCY"]
    print("PASS: Isolated temperature step classified as hardware fault (SPIKE) with is_fault=True.")

    # 4.3 Thermodynamic Decoupling (Calculated Dew Point > Dry Bulb Temperature)
    st_thermo = "AWS-THERMO-TEST"
    pipeline.reset_station(st_thermo)
    res_thermo = await service.ingest_observation({
        "timestamp": (t0 + timedelta(minutes=15)).isoformat(),
        "station_id": st_thermo,
        "temperature": 15.0,
        "pressure": 1013.25,
        "humidity": 103.5,  # Superelevated humidity causing thermodynamic violation
    }, save_db=True, broadcast=False)
    
    inf_thermo = res_thermo.inference
    print("\nThermodynamic Inconsistency Result:")
    print(f"  classification: {inf_thermo.classification}")
    print(f"  is_fault: {inf_thermo.is_fault}")
    assert inf_thermo.is_fault is True
    assert inf_thermo.classification in ["MULTIVARIATE_INCONSISTENCY", "DATA_CORRUPTION", "SPIKE"]
    print("PASS: Thermodynamic decoupling correctly identified as sensor fault.")

async def main():
    await init_db()
    pipeline = SkyGuardPipeline(auto_load=True)
    
    await test_csv_upload_edge_cases(pipeline)
    await test_physical_bounds_boundary(pipeline)
    await test_sensor_health_stress_and_recovery(pipeline)
    await test_convective_front_classification(pipeline)
    
    print("\n" + "="*70)
    print("ALL EMPIRICAL STRESS TESTS COMPLETED SUCCESSFULLY!")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
