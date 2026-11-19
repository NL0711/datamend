"""Synthetic decisions and mocked narration; no external API or trained models."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from jsonschema import Draft202012Validator
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api import rainfall, rainfall_explanations as api
from backend.app.config import settings
from backend.app.db.database import get_db
from backend.app.rainfall.catalog import Station
from backend.app.rainfall.evidence import DecisionEvidence
from backend.app.rainfall.explanation_store import ExplanationRecord
from backend.app.rainfall.explanations import baseline_explanation, narrate
from backend.app.rainfall.service import RainfallService
from backend.app.rainfall.weather_union import CallBudget, RainObservation, WeatherUnionClient

T0 = datetime(2026, 11, 19, 4, tzinfo=timezone.utc)


def make_service(kind="jump"):
    stations = [Station(sid, "Mumbai", sid, 19 + i * .001, 72.8, 2) for i, sid in enumerate("ABCD")]
    svc = RainfallService(WeatherUnionClient("synthetic", "https://weather.test", budget=CallBudget(900)), stations)
    for sid in "ABCD":
        svc.history[sid].append(RainObservation(sid, T0, 2, 0., 0., "OK"))
        svc.history[sid].append(RainObservation(sid, T0 + timedelta(minutes=15), 2,
                                               1. if kind == "isolated" and sid == "A" else 0.,
                                               80. if kind == "jump" and sid == "A" else 0., "OK"))
    return svc


def test_synthetic_evidence_matches_decision_and_explains_assumptions():
    svc = make_service()
    before = list(svc.history["A"])
    evidence = svc.decision_evidence("A")
    check = evidence.checks[0]
    assert evidence.verdict == "SUSPECT" and evidence.rule_score == .79
    assert check.check == "ACCUMULATION_JUMP" and check.observed.value == 80
    assert check.observed.basis == "derived"
    assert check.threshold.parameters["jump_limit"].basis == "assumed"
    assert evidence.run_id == "live:2026-11-20"
    baseline = baseline_explanation(evidence)
    assert "assumed" in baseline.text and "not a probability" in baseline.text
    assert "not a diagnosis" in baseline.text
    assert list(svc.history["A"]) == before


def test_neighbour_disagreement_remains_uncertain():
    evidence = make_service("isolated").decision_evidence("A")
    assert evidence.verdict == "UNCERTAIN"
    assert len(evidence.checks[0].neighbours) == 3
    assert "not a proven fault" in baseline_explanation(evidence).text


def test_clean_reading_does_not_claim_proven_correct():
    evidence = make_service("clean").decision_evidence("A")
    assert evidence.verdict == "OK" and not evidence.checks
    assert "does not prove" in baseline_explanation(evidence).text


def test_missing_data_lists_checks_not_run():
    svc = make_service()
    svc.history["A"].append(RainObservation("A", T0 + timedelta(minutes=30), 2, None, None, "NO_RAIN_FIELDS"))
    evidence = svc.decision_evidence("A")
    assert evidence.verdict == "NO_DATA" and evidence.checks_run == ["NO_RAIN_FIELDS"]
    assert any("NEGATIVE_VALUE" in reason for reason in evidence.not_run)
    assert evidence.checks[0].observed.value is None


def test_counter_predecessor_is_present_after_a_long_gap():
    svc = make_service("clean")
    for i in range(30):
        svc.history["A"].append(RainObservation("A", T0 + timedelta(minutes=20 + i), 2, None, None, "API_ERROR"))
    svc.history["A"].append(RainObservation("A", T0 + timedelta(hours=2), 2, 0., 80., "OK"))
    check = svc.decision_evidence("A").checks[0]
    assert check.check == "ACCUMULATION_JUMP"
    assert len(check.window) == 2 and check.window[0].accumulation.value == 0


@pytest.mark.asyncio
async def test_narrator_service_limits_calls_without_changing_decisions(monkeypatch):
    from backend.app.rainfall import explanation_service as module
    from backend.app.rainfall.explanations import Explanation
    calls = []

    async def fake_narrate(evidence, url, token):
        calls.append(evidence.digest())
        return Explanation(text="Generated from evidence.", contributions=[], model_id="test"), "AI-generated"

    async def fake_save(session, evidence, baseline, narrator, status):
        return {"narrator": narrator, "status": status, "digest": evidence.digest()}

    monkeypatch.setattr(module, "narrate", fake_narrate)
    monkeypatch.setattr(module, "save_explanation", fake_save)
    service = module.ExplanationService()
    evidence = make_service().decision_evidence("A")
    first = await service.explain(None, evidence, True, "https://narrator.test", "")
    second = await service.explain(None, evidence, True, "https://narrator.test", "")
    assert first["narrator"] and second["narrator"] is None
    assert "rate limit" in second["status"] and len(calls) == 1
    assert first["digest"] == second["digest"] == evidence.digest()


def test_schema_and_sample_match_runtime_contract():
    schema = json.loads(Path("docs/contracts/evidence-v1.schema.json").read_text())
    assert schema == DecisionEvidence.model_json_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(make_service().decision_evidence("A").model_dump())
    sample = json.loads(Path("docs/contracts/evidence-v1.example.json").read_text())
    assert sample["label"].startswith("SYNTHETIC")
    Draft202012Validator(schema).validate(sample["evidence"])


@pytest.mark.asyncio
async def test_narrator_receives_evidence_only_and_cannot_modify_it():
    evidence = make_service().decision_evidence("A")
    digest = evidence.digest()

    def respond(request):
        assert request.headers["Authorization"] == "Bearer test-token"
        data = json.loads(request.content)
        assert data["evidence"]["verdict"] == "SUSPECT"
        return httpx.Response(200, json={"text": "Counter jump, assuming millimetres.", "contributions": [
            {"factor": "ACCUMULATION_JUMP", "note": "See the measured counter values and assumed units."}],
            "model_id": "test-narrator", "generated": True})

    result, _ = await narrate(evidence, "https://narrator.test/explain", "test-token", httpx.MockTransport(respond))
    assert result and result.model_id == "test-narrator" and evidence.digest() == digest


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"text": "Override", "verdict": "OK", "contributions": [], "model_id": "bad", "generated": True},
    {"text": "Invented", "contributions": [{"factor": "NOT_IN_EVIDENCE", "note": "x"}], "model_id": "bad", "generated": True},
    {"text": "x", "contributions": [], "model_id": "bad", "generated": False},
    {"text": "x", "contributions": [], "model_id": "bad", "generated": True, "confidence": .99},
    {"text": " ", "contributions": [], "model_id": "bad", "generated": True},
])
async def test_invalid_narrator_reply_falls_back(body):
    evidence = make_service().decision_evidence("A")
    result, status = await narrate(evidence, "https://narrator.test", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    assert result is None and "baseline shown" in status and evidence.verdict == "SUSPECT"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["timeout", "error", "large", "json", "redirect"])
async def test_narrator_network_failures(case):
    def respond(request):
        if case == "timeout": raise httpx.ReadTimeout("secret must not leak")
        if case == "error": return httpx.Response(500, text="secret must not leak")
        if case == "large": return httpx.Response(200, content=b"x" * 65537)
        if case == "redirect": return httpx.Response(302, headers={"Location": "https://elsewhere.test"})
        return httpx.Response(200, text="not json")
    result, status = await narrate(make_service().decision_evidence("A"), "https://narrator.test", transport=httpx.MockTransport(respond))
    assert result is None and "baseline shown" in status and "secret" not in status


@pytest.mark.asyncio
async def test_disconnected_narrator():
    result, status = await narrate(make_service().decision_evidence("A"), "")
    assert result is None and status == "AI narrator not connected"


@pytest.mark.asyncio
async def test_api_storage_stale_reading_auth_and_read_only(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/explanations.db")
    async with engine.begin() as connection:
        await connection.run_sync(ExplanationRecord.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def db():
        async with sessions() as session:
            yield session
            await session.commit()

    svc = make_service()
    monkeypatch.setattr(rainfall, "_service", svc)
    monkeypatch.setattr(settings, "NARRATOR_URL", "")
    monkeypatch.setattr(settings, "EVIDENCE_API_TOKEN", "local-token")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_db] = db
    headers = {"Authorization": "Bearer local-token"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        path = "/api/rainfall/stations/A"
        assert (await client.get(path + "/evidence")).status_code == 401
        response = await client.get(path + "/evidence", headers=headers)
        assert response.status_code == 200
        snapshot = response.json()
        assert (await client.post(path + "/evidence", headers=headers, json={})).status_code == 405
        body = {"evidence_hash": snapshot["evidence_hash"], "use_narrator": True}
        response = await client.post(path + "/explanations", headers=headers, json=body)
        assert response.status_code == 201
        saved = response.json()
        assert saved["evidence"] == snapshot["evidence"] and saved["narrator"] is None
        assert saved["narrator_status"] == "AI narrator not connected"
        svc.history["A"].append(RainObservation("A", T0 + timedelta(minutes=30), 2, 0., 80., "OK"))
        assert (await client.post(path + "/explanations", headers=headers, json=body)).status_code == 409
        stored = await client.get("/api/rainfall/explanations/" + saved["id"], headers=headers)
        assert stored.json()["evidence"] == snapshot["evidence"]
        assert (await client.post(path + "/explanations", headers=headers, json={**body, "verdict": "OK"})).status_code == 422
        assert (await client.get("/api/rainfall/stations/unknown/evidence", headers=headers)).status_code == 404
    await svc.client.aclose()
    await engine.dispose()
