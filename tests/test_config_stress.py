import os
import json
import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError
from backend.app.config import Settings
from backend.app.main import app


def test_default_settings():
    """Validate default configuration parameters according to project specifications."""
    cfg = Settings()
    assert cfg.PROJECT_NAME == "SkyGuard AI"
    assert cfg.VERSION == "0.1.0"
    assert cfg.API_PREFIX == "/api"
    assert cfg.DEBUG is True
    assert cfg.HOST == "0.0.0.0"
    assert cfg.PORT == 8000
    assert "http://localhost:5173" in cfg.CORS_ORIGINS
    assert cfg.DATABASE_URL == "sqlite+aiosqlite:///./skyguard.db"
    assert cfg.INFERENCE_WINDOW_SIZE == 30
    assert cfg.HEALTH_ROLLING_WINDOW == 288
    assert cfg.HEALTH_EMA_ALPHA == 0.10
    assert cfg.ANOMALY_THRESHOLD == 0.50


def test_settings_direct_overrides():
    """Validate direct constructor overrides for all parameters."""
    cfg = Settings(
        PROJECT_NAME="Custom SkyGuard",
        VERSION="1.0.0",
        API_PREFIX="/api/v1",
        DEBUG=False,
        HOST="10.0.0.1",
        PORT=9090,
        CORS_ORIGINS=["http://custom.example.com"],
        DATABASE_URL="sqlite+aiosqlite:///./custom.db",
        INFERENCE_WINDOW_SIZE=60,
        HEALTH_ROLLING_WINDOW=144,
        HEALTH_EMA_ALPHA=0.05,
        ANOMALY_THRESHOLD=0.75,
    )
    assert cfg.PROJECT_NAME == "Custom SkyGuard"
    assert cfg.VERSION == "1.0.0"
    assert cfg.API_PREFIX == "/api/v1"
    assert cfg.DEBUG is False
    assert cfg.HOST == "10.0.0.1"
    assert cfg.PORT == 9090
    assert cfg.CORS_ORIGINS == ["http://custom.example.com"]
    assert cfg.DATABASE_URL == "sqlite+aiosqlite:///./custom.db"
    assert cfg.INFERENCE_WINDOW_SIZE == 60
    assert cfg.HEALTH_ROLLING_WINDOW == 144
    assert cfg.HEALTH_EMA_ALPHA == 0.05
    assert cfg.ANOMALY_THRESHOLD == 0.75


def test_env_var_overriding(monkeypatch):
    """Validate full environment variable overriding via OS environment."""
    monkeypatch.setenv("PROJECT_NAME", "SkyGuard Overridden")
    monkeypatch.setenv("VERSION", "2.0.0-beta")
    monkeypatch.setenv("API_PREFIX", "/api/v2")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./override.db")
    monkeypatch.setenv("INFERENCE_WINDOW_SIZE", "45")
    monkeypatch.setenv("HEALTH_ROLLING_WINDOW", "200")
    monkeypatch.setenv("HEALTH_EMA_ALPHA", "0.15")
    monkeypatch.setenv("ANOMALY_THRESHOLD", "0.65")
    monkeypatch.setenv("CORS_ORIGINS", json.dumps(["http://station-alpha:8080", "http://station-beta:8080"]))

    cfg = Settings()
    assert cfg.PROJECT_NAME == "SkyGuard Overridden"
    assert cfg.VERSION == "2.0.0-beta"
    assert cfg.API_PREFIX == "/api/v2"
    assert cfg.DEBUG is False
    assert cfg.HOST == "127.0.0.1"
    assert cfg.PORT == 9999
    assert cfg.DATABASE_URL == "sqlite+aiosqlite:///./override.db"
    assert cfg.INFERENCE_WINDOW_SIZE == 45
    assert cfg.HEALTH_ROLLING_WINDOW == 200
    assert cfg.HEALTH_EMA_ALPHA == 0.15
    assert cfg.ANOMALY_THRESHOLD == 0.65
    assert cfg.CORS_ORIGINS == ["http://station-alpha:8080", "http://station-beta:8080"]


@pytest.mark.parametrize("debug_input,expected_bool", [
    ("1", True),
    ("0", False),
    ("true", True),
    ("false", False),
    ("True", True),
    ("False", False),
    ("yes", True),
    ("no", False),
    ("on", True),
    ("off", False),
])
def test_debug_boolean_env_parsing(monkeypatch, debug_input, expected_bool):
    """Stress test boolean parsing variations from environment variables."""
    monkeypatch.setenv("DEBUG", debug_input)
    cfg = Settings()
    assert cfg.DEBUG is expected_bool


def test_invalid_integer_env_handling(monkeypatch):
    """Stress test type error when non-numeric string is passed to integer fields."""
    monkeypatch.setenv("PORT", "not_a_valid_port")
    with pytest.raises((ValidationError, SettingsError)):
        Settings()


def test_invalid_float_env_handling(monkeypatch):
    """Stress test type error when non-numeric string is passed to float fields."""
    monkeypatch.setenv("HEALTH_EMA_ALPHA", "bad_float")
    with pytest.raises((ValidationError, SettingsError)):
        Settings()


def test_cors_origins_json_env(monkeypatch):
    """Test valid JSON array parsing for CORS_ORIGINS."""
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:8080", "http://remote:3000"]')
    cfg = Settings()
    assert cfg.CORS_ORIGINS == ["http://localhost:8080", "http://remote:3000"]


def test_extra_env_ignored(monkeypatch):
    """Ensure undefined extra environment variables are safely ignored without error."""
    monkeypatch.setenv("UNRECOGNIZED_SKYGUARD_VARIABLE", "some_value")
    cfg = Settings()
    assert not hasattr(cfg, "UNRECOGNIZED_SKYGUARD_VARIABLE")


@pytest.mark.asyncio
async def test_fastapi_cors_headers():
    """Verify CORS preflight headers on FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
