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
    import time
    tok = (await login(async_client)).json()["token"]
    assert auth_api.session_valid(tok) is True and tok.startswith("v1.")
    assert auth_api.session_valid(auth_api.new_signed_token(time.time() - 5)) is False        # a signed token past its expiry
    legacy = "legacy-token-for-the-test"
    auth_api._sessions[legacy] = 0.0                                                         # a stored-style session past its expiry
    assert auth_api.session_valid(legacy) is False
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    assert (await login(async_client)).status_code == 403


@pytest.mark.asyncio
async def test_a_session_survives_a_restart_and_logout_ends_it(async_client: AsyncClient):
    tok = (await login(async_client)).json()["token"]
    h = {"X-Admin-Token": tok}
    auth_api._sessions.clear()                       # a restart: the in-memory cache is gone, the stored session is not
    assert (await async_client.get("/api/auth/me", headers=h)).json()["signed_in"] is True
    assert (await async_client.get("/api/validation/runs", headers=h)).status_code == 200
    await async_client.post("/api/auth/logout", headers=h)
    auth_api._sessions.clear()
    assert (await async_client.get("/api/auth/me", headers=h)).json()["signed_in"] is False


@pytest.mark.asyncio
async def test_a_signed_token_needs_no_database_and_cannot_be_forged_or_outlive_a_password_change(async_client: AsyncClient, monkeypatch):
    from sqlalchemy import select
    from backend.app.db.database import async_session_factory
    tok = (await login(async_client)).json()["token"]
    async with async_session_factory() as s:        # nothing about a signed session is stored
        assert (await s.execute(select(auth_api.AdminSession).where(auth_api.AdminSession.token_hash == auth_api._digest(tok)))).first() is None
    head, _, mac = tok.rpartition(".")
    assert auth_api.signed_token_valid(tok) is True
    assert auth_api.signed_token_valid(head + "." + ("0" * len(mac))) is False                # wrong signature
    parts = tok.split(".")
    assert auth_api.signed_token_valid(".".join([parts[0], str(int(parts[1]) + 10_000), parts[2], parts[3]])) is False     # a longer expiry does not verify
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "another-password")                        # the signing key is derived from the credentials
    assert auth_api.signed_token_valid(tok) is False
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", PW)
    monkeypatch.setattr(settings, "SESSION_SECRET", "a-different-secret")
    assert auth_api.signed_token_valid(tok) is False


@pytest.mark.asyncio
async def test_an_expired_stored_legacy_session_is_refused(async_client: AsyncClient):
    from backend.app.db.database import async_session_factory
    legacy = "legacy-stored-session-token"
    async with async_session_factory() as s:
        s.add(auth_api.AdminSession(token_hash=auth_api._digest(legacy), expires_at=1.0))      # long expired
        await s.commit()
    auth_api._sessions.clear()
    assert (await async_client.get("/api/auth/me", headers={"X-Admin-Token": legacy})).json()["signed_in"] is False
