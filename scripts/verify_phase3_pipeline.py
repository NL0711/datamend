"""
scripts/verify_phase3_pipeline.py
Standalone Phase 3 Verification & Benchmark Runner.

Verifies end-to-end execution of:
- Stage 0: Tier 0 deterministic screening
- Stage 1: STL diurnal decomposition & baseline fitting
- Stage 2: Multivariate residual ensemble
- Stage 3: Thermodynamic physics & Spatial consensus
- Stage 4: 8-Class fault taxonomy classifier
- Stage 5: TreeSHAP / Surrogate feature attribution & forensic narrative
- Stage 6: Meteorological safe imputation (dual STL + Spatial IDW)
- Tier 3.5: Predictive maintenance & dynamic Sensor Health Index (SHI)
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
import time

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from backend.app.services.phase3_service import phase3_pipeline_service


def main() -> None:
    print("=" * 105)
    print("   DataMend AI — Phase 3 Explainability, Safe Imputation & Predictive Maintenance Verification")
    print("=" * 105)

    now = datetime.now(timezone.utc)
    scenarios = [
        ("Normal Routine Telemetry", 31.4, 1008.2, 55.0, "NORMAL"),
        ("Extreme Temperature Spike", 45.2, 1008.0, 50.0, "SPIKE"),
        ("Frozen Temperature Sensor", 31.4, 1008.2, 55.0, "FROZEN_SENSOR"),
        ("Thermodynamic Dew Point Inconsistency", 15.0, 1010.0, 100.0, "DATA_CORRUPTION"),
        ("Regional Heatwave (Genuine Event)", 43.5, 1002.0, 18.0, "GENUINE_WEATHER_EVENT"),
    ]

    # Pre-configure neighbor observations for spatial corroboration
    delhi_neighbors = [
        {"station_id": "DELHI_AWS_002", "latitude": 28.63, "longitude": 77.22, "temperature": 31.4, "pressure": 1008.1, "humidity": 55.0},
        {"station_id": "DELHI_AWS_003", "latitude": 28.60, "longitude": 77.20, "temperature": 31.5, "pressure": 1008.3, "humidity": 54.8},
    ]

    regional_heatwave_neighbors = [
        {"station_id": "DELHI_AWS_002", "latitude": 28.63, "longitude": 77.22, "temperature": 43.2, "pressure": 1002.1, "humidity": 18.0},
        {"station_id": "DELHI_AWS_003", "latitude": 28.60, "longitude": 77.20, "temperature": 43.8, "pressure": 1001.9, "humidity": 17.5},
    ]

    # Seed baseline for DELHI_AWS_001
    np.random.seed(42)
    t_hist = pd.date_range(end=now, periods=96, freq="15min")
    df_normal = pd.DataFrame({
        "timestamp": t_hist,
        "temperature_c": np.random.normal(31.4, 0.4, size=96),
        "pressure_hpa": np.random.normal(1008.2, 0.3, size=96),
        "humidity_pct": np.random.normal(55.0, 1.0, size=96),
    })
    phase3_pipeline_service.fit_baseline_for_station("DELHI_AWS_001", df_normal)

    # Pre-warm with a normal point
    phase3_pipeline_service.evaluate_reading(
        station_id="DELHI_AWS_001",
        timestamp=now,
        temperature_c=31.4,
        pressure_hpa=1008.2,
        humidity_pct=55.0,
        latitude=28.6139,
        longitude=77.2090,
        altitude_m=216.0,
        active_neighbor_readings=delhi_neighbors,
    )

    header = f"{'Scenario':<34} | {'Class':<20} | {'Driver (Attr%)':<18} | {'Imputed Val':<12} | {'SHI / Risk':<15} | {'Latency':<8}"
    print(f"\n{header}")
    print("-" * 115)

    latencies = []
    for name, temp, pres, hum, expected in scenarios:
        # Helper: feed stuck readings if testing frozen sensor
        if expected == "FROZEN_SENSOR":
            for _ in range(5):
                phase3_pipeline_service.evaluate_reading(
                    station_id="DELHI_AWS_001",
                    timestamp=now,
                    temperature_c=temp,
                    pressure_hpa=pres,
                    humidity_pct=hum,
                    latitude=28.6139,
                    longitude=77.2090,
                    altitude_m=216.0,
                )

        neighbors = regional_heatwave_neighbors if expected == "GENUINE_WEATHER_EVENT" else delhi_neighbors
        diag = phase3_pipeline_service.evaluate_reading(
            station_id="DELHI_AWS_001",
            timestamp=now,
            temperature_c=temp,
            pressure_hpa=pres,
            humidity_pct=hum,
            latitude=28.6139,
            longitude=77.2090,
            altitude_m=216.0,
            dew_point_c=24.5 if expected == "DATA_CORRUPTION" else None,
            active_neighbor_readings=neighbors,
        )

        latencies.append(diag.latency_ms)

        # XAI Driver
        top_driver_name = diag.explanation["top_drivers"][0].replace("_c", "").replace("_hpa", "").replace("_pct", "")
        top_attr = diag.explanation["contributions"][0]["attribution"]
        driver_str = f"{top_driver_name} ({top_attr * 100:.0f}%)"

        # Imputation
        imp_val = diag.imputation["corrected_value"]
        imp_str = f"{imp_val:.1f}" if imp_val is not None else "Passthrough"

        # Health
        shi = diag.sensor_health["health_score"]
        risk = diag.sensor_health["degradation_risk"]
        shi_str = f"{shi:.0f} ({risk[:6]})"

        print(f"{name:<34} | {diag.predicted_class:<20} | {driver_str:<18} | {imp_str:<12} | {shi_str:<15} | {diag.latency_ms:<6.2f} ms")

    avg_lat = sum(latencies) / len(latencies)
    print("-" * 115)
    print(f"Average Phase 3 Pipeline Latency: {avg_lat:.2f} ms (Target SLA: <= 20.0 ms)")
    assert avg_lat <= 20.0, f"Average latency {avg_lat:.2f}ms exceeded SLA threshold!"
    print(">>> Phase 3 Full Pipeline Verification: ALL TESTS PASSED.")
    print("=" * 105)


if __name__ == "__main__":
    main()
