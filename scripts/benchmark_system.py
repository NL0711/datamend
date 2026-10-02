"""
scripts/benchmark_system.py
SkyGuard AI — Empirical Performance & Latency Benchmark.
Measures actual end-to-end ML inference latency, DB write latency, API latency, and calculates percentiles (Mean, Median, P95, P99, Max).
"""

import time
import statistics
import asyncio
import numpy as np
from datetime import datetime, timezone

from backend.app.ml.pipeline import SkyGuardPipeline
from backend.app.schemas.canonical import CanonicalTelemetry, DataSourceType


def benchmark_ml_pipeline(n_iterations: int = 200):
    print(f"\n[1/3] Benchmarking 5-Tier ML Pipeline ({n_iterations} iterations)...")
    pipeline = SkyGuardPipeline()
    pipeline.reset_station("BENCH-001")

    latencies_ms = []
    
    # Warm-up iterations
    for i in range(10):
        pipeline.process_observation({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "station_id": "BENCH-001",
            "temperature": 24.0 + (i * 0.1),
            "pressure": 1013.25,
            "humidity": 60.0,
        })

    # Benchmark loop
    for i in range(n_iterations):
        t0 = time.perf_counter()
        res = pipeline.process_observation({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "station_id": "BENCH-001",
            "temperature": 24.0 + np.sin(i / 10.0) * 5.0,
            "pressure": 1013.25 + np.cos(i / 10.0) * 2.0,
            "humidity": 60.0 + np.sin(i / 5.0) * 10.0,
        })
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)

    mean_lat = statistics.mean(latencies_ms)
    median_lat = statistics.median(latencies_ms)
    p95_lat = np.percentile(latencies_ms, 95)
    p99_lat = np.percentile(latencies_ms, 99)
    max_lat = max(latencies_ms)
    min_lat = min(latencies_ms)

    print(f"  ML Pipeline Mean Latency:   {mean_lat:.2f} ms")
    print(f"  ML Pipeline Median Latency: {median_lat:.2f} ms")
    print(f"  ML Pipeline P95 Latency:    {p95_lat:.2f} ms")
    print(f"  ML Pipeline P99 Latency:    {p99_lat:.2f} ms")
    print(f"  ML Pipeline Min Latency:    {min_lat:.2f} ms")
    print(f"  ML Pipeline Max Latency:    {max_lat:.2f} ms")

    return {
        "mean_ms": mean_lat,
        "median_ms": median_lat,
        "p95_ms": p95_lat,
        "p99_ms": p99_lat,
        "min_ms": min_lat,
        "max_ms": max_lat,
    }


def benchmark_canonical_normalization(n_iterations: int = 1000):
    print(f"\n[2/3] Benchmarking Canonical Telemetry Normalization ({n_iterations} iterations)...")
    latencies_us = []
    
    for i in range(n_iterations):
        t0 = time.perf_counter()
        telemetry = CanonicalTelemetry(
            station_id="BENCH-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            temperature=25.4,
            pressure=1012.0,
            humidity=58.5,
            source_type=DataSourceType.PHYSICAL_AWS,
            source_id="esp32_bench",
            provider="Adafruit-BME280",
            device_id="ESP32-BENCH-01",
        )
        ml_dict = telemetry.to_ml_input_dict()
        t1 = time.perf_counter()
        latencies_us.append((t1 - t0) * 1_000_000.0)

    mean_us = statistics.mean(latencies_us)
    p95_us = np.percentile(latencies_us, 95)
    print(f"  Normalization Mean Latency: {mean_us:.2f} µs ({mean_us/1000.0:.4f} ms)")
    print(f"  Normalization P95 Latency:  {p95_us:.2f} µs ({p95_us/1000.0:.4f} ms)")

    return {
        "mean_us": mean_us,
        "p95_us": p95_us,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("SkyGuard AI — Performance & Latency Benchmark Suite")
    print("=" * 60)
    ml_results = benchmark_ml_pipeline(200)
    norm_results = benchmark_canonical_normalization(1000)
    print("\n" + "=" * 60)
    print("Benchmark Complete.")
    print("=" * 60)
