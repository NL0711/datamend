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
async def test_with_require_login_nothing_can_be_read_without_a_session(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    for url in ("/api/validation/runs", "/api/validation/overview", "/api/places/stations", "/api/settings", "/api/pipeline/import/sources"):
        r = await async_client.get(url)
        assert r.status_code == 401, url
    assert (await async_client.get("/api/auth/me")).status_code == 200          # the sign-in itself stays reachable
    assert (await async_client.get("/", headers={})).status_code == 200         # the health check is not under /api
    tok = (await login(async_client)).json()["token"]
    h = {"X-Admin-Token": tok}
    assert (await async_client.get("/api/validation/overview", headers=h)).status_code == 200
    await async_client.post("/api/auth/logout", headers=h)
    assert (await async_client.get("/api/validation/overview", headers=h)).status_code == 401


@pytest.mark.asyncio
async def test_me_accepts_the_script_token_like_every_other_route(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "s" * 32)
    assert (await async_client.get("/api/auth/me", headers={"X-Admin-Token": "s" * 32})).json()["signed_in"] is True
    assert (await async_client.get("/api/auth/me", headers={"X-Admin-Token": "w" * 32})).json()["signed_in"] is False
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    assert (await async_client.get("/api/auth/me", headers={"X-Admin-Token": ""})).json()["signed_in"] is False


@pytest.mark.asyncio
async def test_sessions_expire_and_an_empty_password_switches_login_off(async_client: AsyncClient, monkeypatch):
    tok = (await login(async_client)).json()["token"]
    auth_api._sessions[tok] = 0.0
    assert auth_api.session_valid(tok) is False
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    assert (await login(async_client)).status_code == 403
