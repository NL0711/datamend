"""Ideas taken from the rf pull request (Rochelle Fernandes, PR 34) and rebuilt on the platform's own evidence and explain code:
a stale-evidence guard with an audit copy, stricter narrator replies, per-decision limitations and not-run, and a read-only credential."""
import json

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.api import auth as auth_api
from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.main import app
from backend.app.validation import narrate
from backend.app.validation.evidence import digest
from backend.app.validation.explain import BaselineExplainer, NarratorExplainer, NarratorUnavailable, _Limiter
from backend.app.validation.models import Explanation
from tests.test_validation_explain import make_run

READ = "r" * 40


@pytest.fixture(autouse=True)
def _clean():
    auth_api._token_failures.clear()
    yield
    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------------------------ stale-evidence guard and audit copy
@pytest.mark.asyncio
async def test_evidence_carries_a_hash_and_a_changed_hash_is_refused_with_409(async_client: AsyncClient):
    run, rows = await make_run(async_client)
    row = next(r for r in rows if r["verdict"] != "OK")
    url = f"/api/validation/runs/{run['id']}/rows/{row['id']}"
    ev = (await async_client.get(url + "/evidence")).json()
    assert ev["evidence_hash"] == digest(ev["evidence"]) and len(ev["evidence_hash"]) == 64
    assert (await async_client.get(url + "/evidence")).json()["evidence_hash"] == ev["evidence_hash"]     # stable
    stale = await async_client.post(url + "/explain", json={"generator": "baseline", "evidence_hash": "0" * 64})
    assert stale.status_code == 409 and "changed" in stale.json()["detail"]
    async with async_session_factory() as s:
        before = len((await s.execute(select(Explanation).where(Explanation.run_id == run["id"]))).scalars().all())
    ok = await async_client.post(url + "/explain", json={"generator": "baseline", "evidence_hash": ev["evidence_hash"]})
    assert ok.status_code == 201
    out = ok.json()["explanations"][0]
    assert out["evidence_hash"] and out["evidence_hash"] in {digest(e) for e in ev["evidence"]}
    async with async_session_factory() as s:
        rows_now = (await s.execute(select(Explanation).where(Explanation.run_id == run["id"]))).scalars().all()
        assert len(rows_now) == before + len(ev["evidence"])                       # the refused request stored nothing
        saved = rows_now[-1]
        assert saved.evidence_snapshot is not None and digest(saved.evidence_snapshot) == saved.evidence_hash   # the copy matches its hash
    bad = await async_client.post(url + "/explain", json={"generator": "baseline", "evidence_hash": "not-a-hash"})
    assert bad.status_code == 422


# ------------------------------------------------------------------------------------------------ limitations and not-run in the evidence
@pytest.mark.asyncio
async def test_evidence_states_its_limits_and_the_baseline_text_repeats_them(async_client: AsyncClient):
    run, rows = await make_run(async_client)
    row = next(r for r in rows if r["verdict"] != "OK")
    evs = (await async_client.get(f"/api/validation/runs/{run['id']}/rows/{row['id']}/evidence")).json()["evidence"]
    assert evs
    for ev in evs:
        assert any("uncalibrated" in l for l in ev["limitations"]) and any("No real labelled faults" in l for l in ev["limitations"])
        assert any("synthetic" in l for l in ev["limitations"])                      # the run was made with synthetic=true
        assert isinstance(ev["not_run"], list)
    text = BaselineExplainer.text(evs[0])
    assert "No real labelled faults support an accuracy claim." in text and text.count("uncalibrated") >= 1


# ------------------------------------------------------------------------------------------------ stricter narrator replies
def narrator(handler):
    return NarratorExplainer("https://narrator.test/x", "", 5.0, httpx.MockTransport(handler), _Limiter(1000))


EV = {"check": "counter_jump", "reason": "r"}


@pytest.mark.asyncio
async def test_a_reply_naming_a_check_that_did_not_fire_is_discarded():
    def reply(check):
        return lambda r: httpx.Response(200, json={"text": "ok", "model_id": "m", "contributions": [{"check": check, "note": "n"}]})
    assert (await narrator(reply("counter_jump")).explain(EV)).contributions[0]["check"] == "counter_jump"
    with pytest.raises(NarratorUnavailable, match="did not fire"):
        await narrator(reply("made_up_check")).explain(EV)
    with pytest.raises(NarratorUnavailable, match="did not fire"):
        await narrator(reply("")).explain(EV)
    # another check fired on the same row is allowed (it arrives in the context)
    out = await narrator(reply("repeated_value")).explain(EV, context={"other_checks_on_row": ["repeated_value"]})
    assert out.contributions[0]["check"] == "repeated_value"
    # no evidence (a run-level question): nothing to hold the contributions against
    assert (await narrator(reply("anything")).explain(None, question="q", kind="chat")).text == "ok"


@pytest.mark.asyncio
async def test_a_reply_over_64_kb_is_cut_off_while_streaming():
    big = httpx.Response(200, content=b'{"text": "' + b"x" * 70000 + b'"}')
    with pytest.raises(NarratorUnavailable, match="64 KB"):
        await narrator(lambda r: big).explain(EV)


@pytest.mark.asyncio
async def test_a_non_200_reply_is_reported_without_its_body():
    with pytest.raises(NarratorUnavailable) as e:
        await narrator(lambda r: httpx.Response(500, text="secret internal detail")).explain(EV)
    assert "500" in str(e.value) and "secret" not in str(e.value)


# ------------------------------------------------------------------------------------------------ the read-only credential
@pytest.mark.asyncio
async def test_the_read_token_reads_validation_and_places_and_nothing_else(async_client: AsyncClient, monkeypatch):
    run, rows = await make_run(async_client)                                           # made with the login gate off, as in the other tests
    row = rows[0]
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "a" * 40)
    monkeypatch.setattr(settings, "EVIDENCE_API_TOKEN", READ)
    ok = {"Authorization": f"Bearer {READ}"}
    assert (await async_client.get("/api/validation/runs", headers=ok)).status_code == 200
    assert (await async_client.get(f"/api/validation/runs/{run['id']}/rows/{row['id']}/evidence", headers=ok)).status_code == 200
    assert (await async_client.get("/api/places/locate?lat=8.5&lon=77.0", headers=ok)).status_code != 401
    # never a write, even under the allowed prefix
    assert (await async_client.post(f"/api/validation/runs/{run['id']}/rows/{row['id']}/explain", json={"generator": "baseline"}, headers=ok)).status_code == 401
    # never another route
    assert (await async_client.get("/api/pipeline/jobs", headers=ok)).status_code == 401
    assert (await async_client.get("/api/auth/me", headers=ok)).status_code == 200      # open route, but it does not call the reader signed in
    assert (await async_client.get("/api/auth/me", headers=ok)).json()["signed_in"] is False
    # a wrong bearer is refused and counted
    assert (await async_client.get("/api/validation/runs", headers={"Authorization": "Bearer wrong"})).status_code == 401
    assert (await async_client.get("/api/validation/runs")).status_code == 401


@pytest.mark.asyncio
async def test_the_read_token_does_nothing_when_unset(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    monkeypatch.setattr(settings, "EVIDENCE_API_TOKEN", "")
    assert (await async_client.get("/api/validation/runs", headers={"Authorization": "Bearer "})).status_code == 401
    assert (await async_client.get("/api/validation/runs", headers={"Authorization": "Bearer anything"})).status_code == 401


@pytest.mark.asyncio
async def test_guessing_the_read_token_is_rate_limited(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    monkeypatch.setattr(settings, "EVIDENCE_API_TOKEN", READ)
    codes = [(await async_client.get("/api/validation/runs", headers={"Authorization": f"Bearer guess{i}"})).status_code
             for i in range(auth_api.TOKEN_MAX_FAILURES + 2)]
    assert codes[-1] == 429
    assert (await async_client.get("/api/validation/runs", headers={"Authorization": f"Bearer {READ}"})).status_code == 429   # the limiter is per client


# ------------------------------------------------------------------------------------------------ an existing database gains the new nullable columns
def test_missing_nullable_columns_are_added_to_an_old_table_and_nothing_else():
    import sqlalchemy as sa
    from backend.app.db import database
    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE explanations (id INTEGER PRIMARY KEY, run_id INTEGER, text TEXT)"))     # an old table: no hash, no snapshot
        added = database._add_missing_nullable_columns(c)
        cols = {r[1] for r in c.execute(sa.text("PRAGMA table_info(explanations)"))}
        again = database._add_missing_nullable_columns(c)
    assert {"explanations.evidence_hash", "explanations.evidence_snapshot"} <= set(added)
    assert {"evidence_hash", "evidence_snapshot"} <= cols
    assert "kind" not in cols and "generator" not in cols                  # NOT NULL columns are left to a real migration
    assert not any(a.startswith("explanations.evidence") for a in again)   # idempotent


# ------------------------------------------------------------------------------------------------ CORS formats (from the rf pull request)
@pytest.mark.parametrize("raw,expected", [
    ("https://example.org", ["https://example.org"]),
    ("https://a.org, https://b.org", ["https://a.org", "https://b.org"]),
    ('["https://a.org"]', ["https://a.org"]),
])
def test_cors_accepts_deployment_formats(monkeypatch, raw, expected):
    from backend.app.config import Settings
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert Settings(_env_file=None).CORS_ORIGINS == expected
