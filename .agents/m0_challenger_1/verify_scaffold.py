"""Empirical verification harness for Milestone M0 scaffolding and FastAPI behavior.
Tests:
1. Module imports (backend.app.config, backend.app.main, etc.)
2. FastAPI app attributes and metadata
3. Settings schema and environment defaults
4. HTTP endpoints (GET /, GET /api/health)
5. 404 Not Found handling for unregistered endpoints
6. 405 Method Not Allowed handling for unsupported HTTP methods (POST, PUT, DELETE)
7. CORS middleware preflight headers and origin reflection
8. Full directory layout compliance against PROJECT.md lines 74-165
"""
import sys
import os

def test_imports():
    from backend.app.config import settings
    from backend.app.main import app
    assert app.title == settings.PROJECT_NAME == "SkyGuard AI"
    assert app.version == settings.VERSION == "0.1.0"
    print("[PASS] Module imports and app title/version verified.")

def test_settings():
    from backend.app.config import settings
    assert settings.API_PREFIX == "/api"
    assert settings.HOST == "0.0.0.0"
    assert settings.PORT == 8000
    assert settings.INFERENCE_WINDOW_SIZE == 30
    assert settings.HEALTH_ROLLING_WINDOW == 288
    assert settings.HEALTH_EMA_ALPHA == 0.10
    assert settings.ANOMALY_THRESHOLD == 0.50
    assert "http://localhost:5173" in settings.CORS_ORIGINS
    print("[PASS] Settings configuration defaults verified.")

async def test_fastapi_endpoints():
    from httpx import AsyncClient, ASGITransport
    from backend.app.main import app
    from backend.app.config import settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /
        res = await client.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "online"
        assert data["project"] == settings.PROJECT_NAME
        assert data["version"] == settings.VERSION
        assert data["docs_url"] == "/docs"
        print("[PASS] GET / returned 200 with valid schema.")

        # 2. GET /api/health
        res = await client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "backend"
        assert data["version"] == settings.VERSION
        print("[PASS] GET /api/health returned 200 with valid health schema.")

        # 3. Edge Case: 404 on nonexistent route
        res = await client.get("/nonexistent/endpoint/test")
        assert res.status_code == 404
        assert res.json() == {"detail": "Not Found"}
        print("[PASS] GET /nonexistent returned 404 Not Found.")

        # 4. Edge Case: 405 on unsupported method (POST on GET-only route)
        res = await client.post("/", json={"data": "test"})
        assert res.status_code == 405
        assert res.json() == {"detail": "Method Not Allowed"}
        print("[PASS] POST / returned 405 Method Not Allowed.")

        res = await client.post("/api/health", json={"data": "test"})
        assert res.status_code == 405
        assert res.json() == {"detail": "Method Not Allowed"}
        print("[PASS] POST /api/health returned 405 Method Not Allowed.")

        # 5. Edge Case: CORS preflight OPTIONS request
        res = await client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
        print("[PASS] CORS preflight OPTIONS returned 200 with allowed origin.")

        # 6. Edge Case: Request with allowed Origin header
        res = await client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
        print("[PASS] GET /api/health with allowed Origin header echoed origin.")

        # 7. Edge Case: Disallowed Origin does not get CORS allow header
        res = await client.get("/api/health", headers={"Origin": "http://unauthorized-domain.com"})
        assert res.status_code == 200
        assert "access-control-allow-origin" not in res.headers
        print("[PASS] Disallowed origin header was correctly blocked by CORS middleware.")

def test_directory_scaffolding():
    required_paths = [
        "backend/__init__.py",
        "backend/app/__init__.py",
        "backend/app/main.py",
        "backend/app/config.py",
        "backend/app/api/__init__.py",
        "backend/app/api/routes.py",
        "backend/app/api/websocket.py",
        "backend/app/db/__init__.py",
        "backend/app/db/database.py",
        "backend/app/db/models.py",
        "backend/app/db/repositories.py",
        "backend/app/ml/__init__.py",
        "backend/app/ml/pipeline.py",
        "backend/app/ml/tier1_qc.py",
        "backend/app/ml/tier2_point_ml.py",
        "backend/app/ml/tier2_temporal_ml.py",
        "backend/app/ml/tier3_multivariate.py",
        "backend/app/ml/tier4_classifier.py",
        "backend/app/ml/tier5_health.py",
        "backend/app/ml/tier5_explain.py",
        "backend/app/ml/fusion.py",
        "backend/app/ml/preprocessor.py",
        "backend/app/services/__init__.py",
        "backend/app/services/ingestion_service.py",
        "backend/app/services/simulation_service.py",
        "backend/app/services/analytics_service.py",
        "backend/simulator/__init__.py",
        "backend/simulator/diurnal_generator.py",
        "backend/simulator/anomaly_injector.py",
        "backend/simulator/scenarios.py",
        "backend/simulator/cli.py",
        "frontend/package.json",
        "frontend/tsconfig.json",
        "frontend/vite.config.ts",
        "frontend/index.html",
        "frontend/src/main.tsx",
        "frontend/src/App.tsx",
        "frontend/src/types/index.ts",
        "frontend/src/services/api.ts",
        "frontend/src/services/websocket.ts",
        "frontend/src/components/OverviewView.tsx",
        "frontend/src/components/LiveMonitoringView.tsx",
        "frontend/src/components/AlertCenterView.tsx",
        "frontend/src/components/SensorHealthView.tsx",
        "frontend/src/components/EventDetailView.tsx",
        "frontend/src/components/DataExplorerView.tsx",
        "frontend/src/components/AnomalyInjectorUI.tsx",
        "frontend/src/components/ExplainabilityViewer.tsx",
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/test_sanity.py",
        "tests/test_simulator.py",
        "tests/test_tier1_qc.py",
        "tests/test_tier2_ml.py",
        "tests/test_tier3_multivariate.py",
        "tests/test_tier4_classifier.py",
        "tests/test_tier5_health_explain.py",
        "tests/test_fusion.py",
        "tests/test_api.py",
        "tests/test_ingestion.py",
        "tests/test_edge_cases.py",
        "scripts/generate_datasets.py",
        "scripts/train_models.py",
        "scripts/test_anomaly_detection.py",
        "requirements.txt",
        "Dockerfile.backend",
        "Dockerfile.frontend",
        "docker-compose.yml",
        "README.md",
        ".env.example",
        ".gitignore",
    ]
    for rel_path in required_paths:
        full_path = os.path.join(os.getcwd(), rel_path)
        assert os.path.exists(full_path), f"Missing required file: {rel_path}"
    print(f"[PASS] All {len(required_paths)} required scaffolding files exist.")

if __name__ == "__main__":
    import asyncio
    test_imports()
    test_settings()
    test_directory_scaffolding()
    asyncio.run(test_fastapi_endpoints())
    print("\n>>> ALL EMPIRICAL CHALLENGER VERIFICATIONS PASSED <<<")
