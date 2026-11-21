import json

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError

from backend.app.config import Settings
from backend.app.main import app


def test_default_settings(monkeypatch):
    """The code defaults: no environment override (conftest pins a test database) and no .env file."""
    for name in ("DATABASE_URL", "NARRATOR_URL", "NARRATOR_TOKEN", "WEATHER_UNION_API_KEY", "WEATHER_UNION_CITY"):
        monkeypatch.delenv(name, raising=False)
    cfg = Settings(_env_file=None)
    assert cfg.PROJECT_NAME == "DataMend"
    assert cfg.VERSION == "0.2.0"
    assert cfg.API_PREFIX == "/api"
    assert cfg.DEBUG is True
    assert cfg.HOST == "0.0.0.0"
    assert cfg.PORT == 8000
    assert "http://localhost:5173" in cfg.CORS_ORIGINS
    assert cfg.DATABASE_URL == "sqlite+aiosqlite:///./datamend.db"
    # the live feed and the AI narrator are OFF unless configured
    assert cfg.WEATHER_UNION_API_KEY == "" and cfg.WEATHER_UNION_CITY == ""
    assert cfg.WEATHER_UNION_DAILY_CALL_BUDGET == 900 and cfg.WEATHER_UNION_POLL_INTERVAL_SECONDS == 900.0
    assert cfg.WEATHER_UNION_ACCUMULATION_MODE == "cumulative"
    assert cfg.NARRATOR_URL == "" and cfg.NARRATOR_TOKEN == "" and cfg.NARRATOR_TIMEOUT_SECONDS == 20.0


def test_env_example_loads_and_keeps_the_feed_and_narrator_off():
    """Copying .env.example to .env must give a working configuration (the old example used a comma list that crashed the loader)."""
    from pathlib import Path
    cfg = Settings(_env_file=Path(__file__).resolve().parents[1] / ".env.example")
    assert cfg.CORS_ORIGINS[0] == "http://localhost:5173" and cfg.DATABASE_URL.startswith("sqlite+aiosqlite")
    assert cfg.WEATHER_UNION_CITY == "" and cfg.NARRATOR_URL == ""


def test_legacy_settings_are_gone():
    cfg = Settings(_env_file=None)
    for legacy in ("INFERENCE_WINDOW_SIZE", "HEALTH_ROLLING_WINDOW", "ANOMALY_THRESHOLD", "DEFAULT_DATA_SOURCE", "MQTT_BROKER_HOST",
                   "EXTERNAL_WEATHER_PROVIDER", "NOAA_ISD_DATA_PATH"):
        assert not hasattr(cfg, legacy)


def test_settings_direct_overrides():
    cfg = Settings(PROJECT_NAME="Custom DataMend", VERSION="1.0.0", API_PREFIX="/api/v1", DEBUG=False, HOST="10.0.0.1", PORT=9090,
                   CORS_ORIGINS=["http://custom.example.com"], DATABASE_URL="sqlite+aiosqlite:///./custom.db",
                   NARRATOR_URL="https://narrator.example/explain", NARRATOR_TIMEOUT_SECONDS=5.0)
    assert (cfg.PROJECT_NAME, cfg.VERSION, cfg.API_PREFIX, cfg.DEBUG, cfg.HOST, cfg.PORT) == ("Custom DataMend", "1.0.0", "/api/v1", False, "10.0.0.1", 9090)
    assert cfg.CORS_ORIGINS == ["http://custom.example.com"] and cfg.DATABASE_URL == "sqlite+aiosqlite:///./custom.db"
    assert cfg.NARRATOR_URL == "https://narrator.example/explain" and cfg.NARRATOR_TIMEOUT_SECONDS == 5.0


def test_env_var_overriding(monkeypatch):
    monkeypatch.setenv("PROJECT_NAME", "DataMend Overridden")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./override.db")
    monkeypatch.setenv("WEATHER_UNION_CITY", "Mumbai")
    monkeypatch.setenv("NARRATOR_URL", "https://narrator.example/x")
    monkeypatch.setenv("CORS_ORIGINS", json.dumps(["http://station-alpha:8080", "http://station-beta:8080"]))
    cfg = Settings()
    assert cfg.PROJECT_NAME == "DataMend Overridden" and cfg.PORT == 9999 and cfg.DEBUG is False
    assert cfg.DATABASE_URL == "sqlite+aiosqlite:///./override.db" and cfg.WEATHER_UNION_CITY == "Mumbai"
    assert cfg.NARRATOR_URL == "https://narrator.example/x"
    assert cfg.CORS_ORIGINS == ["http://station-alpha:8080", "http://station-beta:8080"]


@pytest.mark.parametrize("debug_input,expected_bool", [("1", True), ("0", False), ("true", True), ("false", False), ("yes", True), ("no", False), ("on", True), ("off", False)])
def test_debug_boolean_env_parsing(monkeypatch, debug_input, expected_bool):
    monkeypatch.setenv("DEBUG", debug_input)
    assert Settings().DEBUG is expected_bool


def test_invalid_integer_env_handling(monkeypatch):
    monkeypatch.setenv("PORT", "not_a_valid_port")
    with pytest.raises((ValidationError, SettingsError)):
        Settings()


@pytest.mark.parametrize("name", ["WEATHER_UNION_POLL_INTERVAL_SECONDS", "NARRATOR_TIMEOUT_SECONDS"])
def test_invalid_float_env_handling(monkeypatch, name):
    monkeypatch.setenv(name, "bad_float")
    with pytest.raises((ValidationError, SettingsError)):
        Settings()


def test_extra_env_ignored(monkeypatch):
    monkeypatch.setenv("UNRECOGNIZED_DATAMEND_VARIABLE", "some_value")
    assert not hasattr(Settings(), "UNRECOGNIZED_DATAMEND_VARIABLE")


@pytest.mark.asyncio
async def test_fastapi_cors_preflight_on_a_platform_route():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options("/api/validation/runs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        blocked = await client.options("/api/validation/runs", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
        assert blocked.headers.get("access-control-allow-origin") is None
