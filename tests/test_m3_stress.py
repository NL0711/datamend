"""
tests/test_m3_stress.py
SkyGuard AI — Empirical Stress Test Suite for Milestone 3:
- High concurrency bursts across multiple AWS stations (detecting deadlocks, race conditions, DB lock errors)
- High-volume latency profiling over 100+ observations (validating p50, p95 < 500ms)
- Multi-client WebSocket broadcast stress (subscribers, broadcast isolation, slow client handling)
- Ad-hoc inference route verification (both sync & async modes)
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import List
import numpy as np
import pytest
from httpx import AsyncClient

from backend.app.api.websocket import ConnectionManager, ws_manager
from backend.app.services.ingestion_service import ingestion_service


@pytest.mark.asyncio
async def test_m3_high_concurrency_multi_station_burst(async_client: AsyncClient):
    """
    Stress Test 1: Concurrency Burst
    Send 50 simultaneous observation requests across 5 distinct stations (including new stations).
    Verify that all 50 requests succeed with HTTP 201 and no SQLite locking errors / deadlocks occur.
    """
    stations = ["AWS-001", "AWS-002", "AWS-003", "AWS-STRESS-A", "AWS-STRESS-B"]
    base_time = datetime.now(timezone.utc)

    async def _send_observation(index: int):
        station_id = stations[index % len(stations)]
        t_stamp = (base_time + timedelta(seconds=index)).isoformat()
        payload = {
            "timestamp": t_stamp,
            "station_id": station_id,
            "temperature": 20.0 + (index % 15) * 0.4,
            "pressure": 1013.25 - (index % 10) * 0.3,
            "humidity": 50.0 + (index % 20) * 1.2,
        }
        res = await async_client.post("/api/observations", json=payload)
        return res.status_code, res.json()

    # Launch 50 simultaneous tasks
    tasks = [_send_observation(i) for i in range(50)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Check results
    success_count = 0
    errors = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r))
        elif isinstance(r, tuple):
            status_code, data = r
            if status_code == 201 and data.get("persisted") is True:
                success_count += 1
            else:
                errors.append(f"Status {status_code}: {data}")

    assert len(errors) == 0, f"Errors during concurrency burst: {errors[:5]}"
    assert success_count == 50, f"Expected 50 successful ingestions, got {success_count}"


@pytest.mark.asyncio
async def test_m3_end_to_end_latency_profiling_100_obs(async_client: AsyncClient):
    """
    Stress Test 2: Latency Profiling
    Profile end-to-end processing latency over 100 sequential observations.
    Verify average and 95th percentile are well under the 500ms budget.
    """
    station_id = "AWS-LATENCY-TEST"
    base_time = datetime.now(timezone.utc)
    latencies: List[float] = []

    for i in range(100):
        t_stamp = (base_time + timedelta(minutes=5 * i)).isoformat()
        payload = {
            "timestamp": t_stamp,
            "station_id": station_id,
            "temperature": 22.0 + 5.0 * np.sin(i / 10.0),
            "pressure": 1013.0 + 2.0 * np.cos(i / 15.0),
            "humidity": 60.0 - 10.0 * np.sin(i / 10.0),
        }
        t0 = time.perf_counter()
        res = await async_client.post("/api/observations", json=payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)
        assert res.status_code == 201

    lat_arr = np.array(latencies)
    avg_latency = float(np.mean(lat_arr))
    p50_latency = float(np.percentile(lat_arr, 50))
    p95_latency = float(np.percentile(lat_arr, 95))
    p99_latency = float(np.percentile(lat_arr, 99))
    max_latency = float(np.max(lat_arr))

    # Assert budget compliance
    assert avg_latency < 500.0, f"Average latency {avg_latency:.2f}ms exceeds 500ms"
    assert p95_latency < 500.0, f"p95 latency {p95_latency:.2f}ms exceeds 500ms"
    assert p99_latency < 1000.0, f"p99 latency {p99_latency:.2f}ms exceeds 1000ms"


@pytest.mark.asyncio
async def test_m3_websocket_multi_client_broadcast_stress():
    """
    Stress Test 3: WebSocket Multi-Client Broadcast
    Simulate 20 concurrent WebSocket subscribers receiving rapid broadcast bursts.
    Verify no broadcast dropouts, no deadlock, and proper station filtering.
    """
    manager = ConnectionManager()

    class MockWebSocket:
        def __init__(self, client_id: str, slow: bool = False):
            self.client_id = client_id
            self.client = f"client_{client_id}"
            self.received_messages = []
            self.is_closed = False
            self.slow = slow

        async def accept(self):
            pass

        async def send_text(self, text: str):
            if self.slow:
                await asyncio.sleep(0.05)
            self.received_messages.append(text)

    # Create 20 mock subscribers: 10 subscribing to "AWS-001", 5 to "AWS-002", 5 to ALL ("*")
    clients = []
    for i in range(10):
        ws = MockWebSocket(f"c_aws1_{i}")
        await manager.connect(ws, initial_stations=["AWS-001"])
        clients.append((ws, "AWS-001"))

    for i in range(5):
        ws = MockWebSocket(f"c_aws2_{i}")
        await manager.connect(ws, initial_stations=["AWS-002"])
        clients.append((ws, "AWS-002"))

    for i in range(5):
        ws = MockWebSocket(f"c_all_{i}", slow=True)
        await manager.connect(ws, initial_stations=["*"])
        clients.append((ws, "*"))

    assert manager.get_active_count() == 20

    # Broadcast 10 messages for AWS-001
    for msg_idx in range(10):
        await manager.broadcast_observation("AWS-001", {
            "temperature": 25.0 + msg_idx,
            "pressure": 1013.0,
            "humidity": 55.0,
            "is_anomaly": False,
        })

    # Broadcast 5 messages for AWS-002
    for msg_idx in range(5):
        await manager.broadcast_observation("AWS-002", {
            "temperature": 18.0 + msg_idx,
            "pressure": 1015.0,
            "humidity": 70.0,
            "is_anomaly": False,
        })

    # Verify counts:
    # AWS-001 clients should have received exactly 10 messages
    for ws, target in clients[:10]:
        assert len(ws.received_messages) == 10

    # AWS-002 clients should have received exactly 5 messages
    for ws, target in clients[10:15]:
        assert len(ws.received_messages) == 5

    # ALL clients should have received exactly 15 messages (10 + 5)
    for ws, target in clients[15:]:
        assert len(ws.received_messages) == 15


@pytest.mark.asyncio
async def test_m3_adhoc_infer_route(async_client: AsyncClient):
    """
    Stress Test 4: Ad-Hoc Inference Endpoint Verification
    Tests both persist=False and persist=True modes for /api/infer.
    """
    payload_no_persist = {
        "timestamp": "2026-08-24T16:00:00Z",
        "station_id": "AWS-001",
        "temperature": 23.5,
        "pressure": 1012.8,
        "humidity": 64.0,
        "persist": False,
    }
    res1 = await async_client.post("/api/infer", json=payload_no_persist)
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["station_id"] == "AWS-001"
    assert "anomaly_score" in d1
    assert "explanation" in d1

    payload_persist = {
        "timestamp": "2026-08-24T16:05:00Z",
        "station_id": "AWS-001",
        "temperature": 23.8,
        "pressure": 1012.7,
        "humidity": 63.5,
        "persist": True,
    }
    res2 = await async_client.post("/api/infer", json=payload_persist)
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["station_id"] == "AWS-001"
    assert "sensor_health" in d2
