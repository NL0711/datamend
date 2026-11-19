"""Admin sign-in: a session token opens the same write endpoints as ADMIN_TOKEN; wrong attempts are refused and rate limited."""
import pytest
from httpx import AsyncClient

from backend.app.api import auth as auth_api
from backend.app.config import settings

EMAIL, PW = "admin@admin.com", "admin"


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "rt.json"))
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    monkeypatch.setattr(settings, "ADMIN_EMAIL", EMAIL)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", PW)
    auth_api._sessions.clear()
    auth_api._failures.clear()


async def login(c: AsyncClient, email=EMAIL, pw=PW):
    return await c.post("/api/auth/login", json={"email": email, "password": pw})


@pytest.mark.asyncio
async def test_login_gives_a_session_that_opens_writes(async_client: AsyncClient):
    r = await login(async_client)
    assert r.status_code == 200 and r.json()["email"] == EMAIL
    h = {"X-Admin-Token": r.json()["token"]}
    assert (await async_client.get("/api/auth/me", headers=h)).json()["signed_in"] is True
    assert (await async_client.put("/api/settings", json={"weather_union_city": "Mumbai"}, headers=h)).status_code == 200
    assert (await async_client.post("/api/auth/logout", headers=h)).json()["signed_in"] is False
    assert (await async_client.put("/api/settings", json={"weather_union_city": "Mumbai"}, headers=h)).status_code == 401


@pytest.mark.asyncio
async def test_wrong_credentials_and_no_session_are_refused(async_client: AsyncClient):
    assert (await login(async_client, pw="nope")).status_code == 401
    assert (await login(async_client, email="x@y.com")).status_code == 401
    assert (await async_client.put("/api/settings", json={"weather_union_city": "Mumbai"})).status_code == 401
    assert (await async_client.get("/api/auth/me")).json()["signed_in"] is False


@pytest.mark.asyncio
async def test_email_is_case_insensitive_and_attempts_are_limited(async_client: AsyncClient):
    assert (await login(async_client, email="  ADMIN@Admin.com ")).status_code == 200
    for _ in range(auth_api.MAX_FAILURES):
        assert (await login(async_client, pw="bad")).status_code == 401
    assert (await login(async_client)).status_code == 429


@pytest.mark.asyncio
async def test_sessions_expire_and_an_empty_password_switches_login_off(async_client: AsyncClient, monkeypatch):
    tok = (await login(async_client)).json()["token"]
    auth_api._sessions[tok] = 0.0
    assert auth_api.session_valid(tok) is False
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    assert (await login(async_client)).status_code == 403
