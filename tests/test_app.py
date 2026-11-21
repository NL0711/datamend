"""The application surface. The legacy temperature/pressure/humidity app was removed (spec slice 9); its service contract (stations, observations,
anomalies, data sources, simulation, /ws/live) came back as NEW code on the platform by the owner's decision of 2026-11-21 (slice S3a, tests/test_stream_api.py).
What stays gone is every other legacy path."""
import pytest
from httpx import AsyncClient

from backend.app.main import app

EXPECTED_PREFIXES = ("/api/validation", "/api/rainfall", "/api/places", "/api/settings", "/api/auth", "/api/pipeline", "/api/mcp", "/api/agent",
                     "/api/stations", "/api/observations", "/api/anomalies", "/api/data-sources", "/api/simulation", "/api/simulate")
LEGACY_PATHS = ["/api/health", "/api/locations", "/api/sources", "/ws/telemetry", "/api/health/fleet", "/api/metrics", "/api/inference"]


@pytest.mark.asyncio
async def test_root_describes_the_service(async_client: AsyncClient):
    body = (await async_client.get("/")).json()
    assert body["status"] == "online" and body["project"] == "DataMend" and body["docs_url"] == "/docs"


def test_only_the_platform_routes_exist():
    paths = list(app.openapi()["paths"])            # included routers are wrapped lazily, so read the schema rather than app.routes
    extra = [p for p in paths if p != "/" and not p.startswith(EXPECTED_PREFIXES)]
    assert extra == []
    assert any(p.startswith("/api/validation/runs") for p in paths) and "/api/places/locate" in paths
    assert {"/api/stations", "/api/observations", "/api/anomalies", "/api/data-sources", "/api/simulation/start", "/api/simulate/inject"} <= set(paths)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", LEGACY_PATHS)
async def test_legacy_endpoints_are_gone(async_client: AsyncClient, path):
    assert (await async_client.get(path)).status_code == 404


def test_backend_imports_no_legacy_package_or_dependency():
    import subprocess, sys
    code = ("import sys, backend.app.main; "
            "bad=[m for m in sys.modules if m.split('.')[0] in ('torch','shap','pyod','paho','statsmodels','sklearn')]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "[]"
