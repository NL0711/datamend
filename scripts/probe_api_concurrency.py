"""
scripts/probe_api_concurrency.py
OpenSpec task4-parity-closeout, capability perf-evidence (task 2.1).

500-concurrency API probe against the lightweight ingest path
(POST /api/telemetry/live). Reports P50/P95/P99/max latency and error
count with run context. Results belong in docs/evaluation_report.md.

Usage:
    python scripts/probe_api_concurrency.py [--total 500] [--concurrency 500]
        [--base-url http://localhost:8899] [--out reports/api_concurrency_probe.json]

Default transport is in-process ASGI (no server needed). Pass --base-url to
probe a live server instead (measures full network path).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_payload(i: int) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "station_id": f"AWS-PROBE-{i % 100:03d}",
        "temperature": 24.0 + (i % 7) * 0.1,
        "pressure": 1012.0 + (i % 5) * 0.1,
        "humidity": 55.0 + (i % 9) * 0.2,
    }


async def run_probe(total: int, concurrency: int, base_url: str | None,
                    endpoint: str = "/api/telemetry/live") -> dict:
    import httpx

    if base_url:
        client_ctx = httpx.AsyncClient(base_url=base_url, timeout=120.0)
    else:
        from httpx import ASGITransport
        from backend.app.main import app
        from backend.app.db.database import init_db

        await init_db()
        client_ctx = httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", timeout=120.0
        )

    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0
    statuses: dict[int, int] = {}

    async with client_ctx as client:
        # Warm-up (model load, DB pool, JIT) — not counted.
        if endpoint == "/api/telemetry/live":
            warm = await client.post(endpoint, json=build_payload(0))
        else:
            warm = await client.get(endpoint)
        warm.raise_for_status()

        async def one(i: int) -> None:
            nonlocal errors
            async with sem:
                t0 = time.perf_counter()
                try:
                    if endpoint == "/api/telemetry/live":
                        res = await client.post(endpoint, json=build_payload(i))
                    else:
                        res = await client.get(endpoint, params={"station_id": f"AWS-PROBE-{i % 100:03d}"} if "observations" in endpoint else None)
                    statuses[res.status_code] = statuses.get(res.status_code, 0) + 1
                    if res.status_code not in (200, 201):
                        errors += 1
                except Exception:
                    errors += 1
                latencies.append((time.perf_counter() - t0) * 1000.0)

        t_start = time.perf_counter()
        await asyncio.gather(*[one(i) for i in range(total)])
        wall_ms = (time.perf_counter() - t_start) * 1000.0

    arr = np.array(latencies)
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "transport": f"live:{base_url}" if base_url else "in-process-ASGI",
        "endpoint": f"POST {endpoint}" if endpoint == "/api/telemetry/live" else f"GET {endpoint}",
        "total_requests": total,
        "concurrency": concurrency,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "p50_ms": round(float(np.percentile(arr, 50)), 2),
        "p95_ms": round(float(np.percentile(arr, 95)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
        "max_ms": round(float(np.max(arr)), 2),
        "mean_ms": round(float(np.mean(arr)), 2),
        "wall_ms": round(wall_ms, 2),
        "throughput_rps": round(total / max(wall_ms / 1000.0, 1e-6), 2),
        "errors": errors,
        "status_counts": {str(k): v for k, v in statuses.items()},
        "budget_p99_ms": 20.0,
        "budget_met": bool(np.percentile(arr, 99) < 20.0 and errors == 0),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="500-concurrency API latency probe")
    ap.add_argument("--total", type=int, default=500)
    ap.add_argument("--concurrency", type=int, default=500)
    ap.add_argument("--base-url", type=str, default=None)
    ap.add_argument("--out", type=str, default="reports/api_concurrency_probe.json")
    ap.add_argument("--endpoint", type=str, default="/api/telemetry/live",
                    help="Endpoint to probe (default: lightweight ingest path)")
    args = ap.parse_args()

    result = asyncio.run(run_probe(args.total, args.concurrency, args.base_url, args.endpoint))
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    print(f"\nSaved to {out}")
    print(f"Budget P99 < 20 ms, 0 errors: {'PASS' if result['budget_met'] else 'MISS (tracked gap)'}")


if __name__ == "__main__":
    main()
