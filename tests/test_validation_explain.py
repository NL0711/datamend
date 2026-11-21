"""Evidence contract, Explainer seam and AI chat (spec slice 6). The narrator is a mocked transport; no real service is called."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jsonschema
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from backend.app.db.database import async_session_factory
from backend.app.main import app
from backend.app.validation import narrate
from backend.app.validation.evidence import MAX_PAYLOAD_BYTES, evidence_v1
from backend.app.validation.explain import BaselineExplainer, NarratorExplainer, NarratorUnavailable, _Limiter
from backend.app.validation.models import Explanation, Review, ValidationCheckHit, ValidationResult, ValidationRun

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "docs/contracts/evidence-v1.schema.json").read_text(encoding="utf8"))
T0 = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    async with async_session_factory() as s:
        for m in (Review, Explanation, ValidationCheckHit, ValidationResult, ValidationRun):
            await s.execute(delete(m))
        await s.commit()
    yield
    app.dependency_overrides.clear()


def faulty_csv() -> bytes:
    lines = ["timestamp,station_id,accumulation,intensity"]
    for i in range(12):
        t = (T0 + timedelta(minutes=15 * i)).isoformat().replace("+00:00", "Z")
        lines.append(f"{t},A,{120.0 if i >= 6 else 0.0},{500.0 if i == 8 else 0.0}")
    return ("\n".join(lines) + "\n").encode()


async def make_run(client: AsyncClient):
    r = await client.post("/api/validation/runs", files={"file": ("f.csv", faulty_csv(), "text/csv")},
                          data={"profile": "reading", "accumulation_mode": "cumulative", "interval_minutes": "15", "synthetic": "true"})
    assert r.status_code == 201, r.text
    run = r.json()
    page = (await client.get(f"/api/validation/runs/{run['id']}/rows")).json()
    return run, page["rows"]


def narrator_with(handler, **kw):
    return NarratorExplainer("https://narrator.test/explain", kw.pop("token", "secret-token"), 5.0, httpx.MockTransport(handler), _Limiter(1000))


GOOD = {"text": "The counter jumped, so the gauge may have been reset or faulty.", "contributions": [{"check": "counter_jump", "note": "step of 120"}],
        "model_id": "narrator-test-1", "confidence": 0.8}


# ---------------------------------------------------------------- the contract
def test_schema_is_valid_and_the_shipped_example_conforms():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    ex = json.loads((ROOT / "docs/contracts/examples/evidence-v1.counter_jump.json").read_text(encoding="utf8"))
    jsonschema.validate(ex, SCHEMA)


def test_schema_rejects_unknown_fields_missing_basis_and_a_bad_verdict():
    ex = json.loads((ROOT / "docs/contracts/examples/evidence-v1.counter_jump.json").read_text(encoding="utf8"))
    for mutate in (lambda d: d.update(extra=1), lambda d: d["observed"].pop("basis"), lambda d: d["row"].update(verdict="BAD"),
                   lambda d: d.update(provider={"calibrated": False})):
        bad = json.loads(json.dumps(ex))
        mutate(bad)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, SCHEMA)


@pytest.mark.asyncio
async def test_every_real_evidence_payload_conforms_to_the_schema(async_client: AsyncClient):
    run, rows = await make_run(async_client)
    assert rows
    n = 0
    for row in rows:
        body = (await async_client.get(f"/api/validation/runs/{run['id']}/rows/{row['id']}/evidence")).json()
        assert body["schema"] == "evidence-v1" and body["evidence"]
        for ev in body["evidence"]:
            jsonschema.validate(ev, SCHEMA)
            assert "provider" not in ev                            # never invented by the rule-based platform
            assert len(json.dumps(ev).encode()) <= MAX_PAYLOAD_BYTES
            n += 1
    assert n == 2        # one counter jump and one intensity above the ceiling in the generated file
    assert (await async_client.get(f"/api/validation/runs/{run['id']}/rows/{rows[0]['id']}/evidence?check=nope")).json()["evidence"] == []


def test_oversize_evidence_is_cut_under_64kb_and_says_so():
    run = ValidationRun(id=1, profile="reading", source="upload", platform_version="t", git_commit="t", synthetic=False)
    row = ValidationResult(id=2, run_id=1, row_ref="r", station_id="A", verdict="UNCERTAIN", rule_score=0.3)
    nb = [{"station_id": f"S{i:05d}", "distance_km": 1.0, "wet": False, "basis": "measured"} for i in range(2000)]
    hit = ValidationCheckHit(check="neighbour_isolated_wet", layer="neighbour", kind="uncertain", weight=0.3, reason="x",
                             evidence={"profile": "reading", "time_basis": "observed", "neighbours": nb})
    ev = evidence_v1(run, row, hit)
    assert len(json.dumps(ev).encode()) <= MAX_PAYLOAD_BYTES and ev["truncated"] is True and ev["next"].endswith("/rows/2")
    jsonschema.validate(ev, SCHEMA)


# ---------------------------------------------------------------- baseline
@pytest.mark.asyncio
async def test_baseline_explains_from_the_evidence_and_is_marked_generated():
    ev = json.loads((ROOT / "docs/contracts/examples/evidence-v1.counter_jump.json").read_text(encoding="utf8"))
    ex = await BaselineExplainer().explain(ev)
    assert ex.generated is True and ex.generator == "baseline-rules" and ex.confidence is None
    assert ev["reason"] in ex.text and "120" in ex.text and "not a probability" in ex.text and "fixed rules" in ex.text
    assert "AI" not in ex.text


@pytest.mark.asyncio
async def test_baseline_refuses_questions_instead_of_inventing_answers():
    with pytest.raises(NarratorUnavailable):
        await BaselineExplainer().explain({"x": 1}, question="why?", kind="chat")
    with pytest.raises(NarratorUnavailable):
        await BaselineExplainer().explain(None)


# ---------------------------------------------------------------- narrator client (mocked transport)
@pytest.mark.asyncio
async def test_narrator_request_shape_and_token_and_reply_parsing():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"], seen["body"] = req.headers.get("authorization"), json.loads(req.content)
        return httpx.Response(200, json=GOOD)

    ev = {"schema": "evidence-v1", "check": "counter_jump"}
    ex = await narrator_with(handler).explain(ev, question="why?", kind="chat", context={"run_headline": {"rows": 1}})
    assert seen["auth"] == "Bearer secret-token"
    assert seen["body"] == {"schema": "narrator-request-v1", "kind": "chat", "evidence": ev, "question": "why?", "context": {"run_headline": {"rows": 1}}}
    assert ex.generator == "mcp-narrator" and ex.model_id == "narrator-test-1" and ex.confidence == 0.8 and ex.generated is True


@pytest.mark.asyncio
@pytest.mark.parametrize("make_response", [
    lambda r: httpx.Response(500), lambda r: httpx.Response(200, text="not json"), lambda r: httpx.Response(200, json={"text": "", "model_id": "m"}),
    lambda r: httpx.Response(200, json={"text": "x" * 4001, "model_id": "m"}), lambda r: httpx.Response(200, json={"text": "ok"}),
    lambda r: httpx.Response(200, json={"text": "ok", "model_id": "m", "contributions": "no"}),
    lambda r: httpx.Response(200, json={"text": "ok", "model_id": "m", "confidence": "high"}),
    lambda r: httpx.Response(302, headers={"location": "https://evil.test"}),
])
async def test_narrator_bad_replies_are_refused(make_response):
    with pytest.raises(NarratorUnavailable):
        await narrator_with(make_response).explain({"check": "c"})


@pytest.mark.asyncio
async def test_narrator_timeout_oversize_request_and_rate_limit():
    def boom(req):
        raise httpx.ConnectTimeout("t")

    with pytest.raises(NarratorUnavailable, match="did not answer"):
        await narrator_with(boom).explain({"check": "c"})
    with pytest.raises(NarratorUnavailable, match="64 KB"):
        await narrator_with(lambda r: httpx.Response(200, json=GOOD)).explain({"check": "counter_jump", "blob": "x" * 70000})
    limited = NarratorExplainer("https://narrator.test/x", "", 5.0, httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD)), _Limiter(2))
    await limited.explain({"check": "counter_jump"})
    await limited.explain({"check": "counter_jump"})
    with pytest.raises(NarratorUnavailable, match="limited"):
        await limited.explain({"check": "counter_jump"})


def test_narrator_url_must_be_http_or_https():
    for bad in ("file:///etc/passwd", "ftp://x", "narrator", ""):
        with pytest.raises(ValueError):
            NarratorExplainer(bad)


# ---------------------------------------------------------------- API
@pytest.mark.asyncio
async def test_baseline_explain_is_stored_separately_and_changes_no_verdict(async_client: AsyncClient):
    run, rows = await make_run(async_client)
    row = rows[0]
    before = (await async_client.get(f"/api/validation/runs/{run['id']}/rows/{row['id']}")).json()
    res = await async_client.post(f"/api/validation/runs/{run['id']}/rows/{row['id']}/explain", json={"generator": "baseline"})
    assert res.status_code == 201
    items = res.json()["explanations"]
    assert items and all(e["generated"] is True and e["generator"] == "baseline-rules" and "fixed rules" in e["label"] for e in items)
    stored = (await async_client.get(f"/api/validation/runs/{run['id']}/rows/{row['id']}/explanations")).json()["explanations"]
    assert len(stored) == len(items)
    after = (await async_client.get(f"/api/validation/runs/{run['id']}/rows/{row['id']}")).json()
    assert (after["verdict"], after["rule_score"], after["hits"]) == (before["verdict"], before["rule_score"], before["hits"])


@pytest.mark.asyncio
async def test_narrator_unset_says_not_connected_and_invents_nothing(async_client: AsyncClient, monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")      # a developer's local .env may hold a real key; this test is about "nothing set"
    monkeypatch.setattr(settings, "NARRATOR_URL", "")
    run, rows = await make_run(async_client)
    st = (await async_client.get("/api/validation/narrator")).json()
    assert st["connected"] is False and st["message"] == "AI narrator not connected" and st["provider"] is None and "GEMINI_API_KEY" in st["note"]
    r = await async_client.post(f"/api/validation/runs/{run['id']}/rows/{rows[0]['id']}/explain", json={"generator": "narrator"})
    assert r.status_code == 503 and "not connected" in r.text
    c = await async_client.post(f"/api/validation/runs/{run['id']}/chat", json={"message": "why was this flagged?", "row_id": rows[0]["id"]})
    assert c.status_code == 503 and "AI narrator not connected" in c.text
    assert (await async_client.get(f"/api/validation/runs/{run['id']}/chat")).json() == {"messages": []}


@pytest.mark.asyncio
async def test_chat_with_a_narrator_is_grounded_stored_and_badged(async_client: AsyncClient):
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        # name the check of the evidence that was sent: a reply that names a check that did not fire is discarded
        return httpx.Response(200, json={**GOOD, "contributions": [{"check": body["evidence"]["check"], "note": "step of 120"}]})

    app.dependency_overrides[narrate.get_narrator] = lambda: narrator_with(handler)
    run, rows = await make_run(async_client)
    assert (await async_client.get("/api/validation/narrator")).json() == {"connected": True, "host": "narrator.test", "provider": "mcp-narrator",
                                                                          "message": "narrator configured (reachability is checked per request)", "implemented": True}
    r = await async_client.post(f"/api/validation/runs/{run['id']}/chat", json={"message": "  why was this flagged?  ", "row_id": rows[0]["id"]})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["label"] == "AI-generated" and m["generated"] is True and m["question"] == "why was this flagged?" and m["confidence_note"] == "the narrator's own number"
    sent = seen[0]
    assert sent["kind"] == "chat" and sent["question"] == "why was this flagged?"
    jsonschema.validate(sent["evidence"], SCHEMA)                       # the narrator gets exactly one evidence-v1 payload
    assert sent["evidence"]["row"]["id"] == rows[0]["id"] and sent["context"]["run_headline"]["rows"] == 12
    hist = (await async_client.get(f"/api/validation/runs/{run['id']}/chat")).json()["messages"]
    assert [x["id"] for x in hist] == [m["id"]]
    ex = await async_client.post(f"/api/validation/runs/{run['id']}/rows/{rows[0]['id']}/explain", json={"generator": "narrator"})
    assert ex.status_code == 201 and all(e["label"] == "AI-generated" for e in ex.json()["explanations"])


@pytest.mark.asyncio
async def test_run_level_chat_needs_no_row_and_failures_are_502_not_invented(async_client: AsyncClient):
    app.dependency_overrides[narrate.get_narrator] = lambda: narrator_with(lambda r: httpx.Response(200, json=GOOD))
    run, _ = await make_run(async_client)
    ok = await async_client.post(f"/api/validation/runs/{run['id']}/chat", json={"message": "summarise this run"})
    assert ok.status_code == 201 and ok.json()["result_id"] is None
    app.dependency_overrides[narrate.get_narrator] = lambda: narrator_with(lambda r: httpx.Response(500))
    bad = await async_client.post(f"/api/validation/runs/{run['id']}/chat", json={"message": "again"})
    assert bad.status_code == 502
    assert len((await async_client.get(f"/api/validation/runs/{run['id']}/chat")).json()["messages"]) == 1     # the failed turn stored nothing


@pytest.mark.asyncio
async def test_chat_input_validation_and_missing_things(async_client: AsyncClient):
    app.dependency_overrides[narrate.get_narrator] = lambda: narrator_with(lambda r: httpx.Response(200, json=GOOD))
    run, rows = await make_run(async_client)
    base = f"/api/validation/runs/{run['id']}/chat"
    assert (await async_client.post(base, json={"message": ""})).status_code == 422
    assert (await async_client.post(base, json={"message": "     "})).status_code == 422      # review finding: was a 500
    assert (await async_client.post(base, json={"message": "x" * 2001})).status_code == 422
    assert (await async_client.post(base, json={"message": "hi", "row_id": 999999})).status_code == 404
    assert (await async_client.post("/api/validation/runs/999999/chat", json={"message": "hi"})).status_code == 404
    assert (await async_client.post(f"/api/validation/runs/{run['id']}/rows/{rows[0]['id']}/explain", json={"generator": "magic"})).status_code == 422
    clean = [r for r in (await async_client.get(f"/api/validation/runs/{run['id']}/rows?verdict=OK")).json()["rows"]]
    assert clean
    r = await async_client.post(f"/api/validation/runs/{run['id']}/rows/{clean[0]['id']}/explain", json={"generator": "baseline"})
    assert r.status_code == 404 and "no fired check" in r.text
