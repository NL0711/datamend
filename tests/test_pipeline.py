"""The ingest and feedback loop on generated CWC-shaped files. No real data and no network: the files are built here.

IST is the assumed time zone, so 08:30 IST is 03:00 UTC, the start of the NEXT rain day (labelled by the date it ends).
"""
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.pipeline import cwc, registry
from backend.app.pipeline.models import (AuditItem, Correction, IngestJob, ModelScore, ModelVersion, Observation, PipelineStation, Proposal, ShadowRun,
                                          TrainingJob, TrainingSnapshot)
from backend.app.validation.models import Review, ValidationResult, ValidationRun

TOKEN = "p" * 32
H = {"X-Admin-Token": TOKEN}
HEADER = ("SlNo,Station,Agency,State LGD Code,State,District LGD Code,District,Tehsil,Block,Village,River,Basin,Tributary,Subtributary,"
          "SubSubtributary,Local River,Latitude,Longitude,Data Acquisition Time,Telemetry Hourly Rainfall (mm)")


def line(i, station, when, mm, lat=23.5, lon=91.6, state="Tripura"):
    return f"{i},{station},CWC,16,{state},654,Gomati,T,-,-,R,B,T,S,-,L,{lat},{lon},{when.strftime('%d-%m-%Y %H:%M')},{mm}"


def csv_text(rows):
    return HEADER + "\n" + "\n".join(line(i + 1, *r) for i, r in enumerate(rows)) + "\n"


# 14 hours of 75 mm plus one 423 mm hour, all from 09:00 to 23:00 IST on 2026-06-10, i.e. inside the rain day that ENDS on 2026-06-11: 1,473 mm
BIG_DAY = [("Amarpur", datetime(2026, 6, 10, h), 75.0) for h in range(9, 23)] + [("Amarpur", datetime(2026, 6, 10, 23), 423.0)]


def wet_days(station, start, days, mm=4.0, hour=14, **kw):
    """One non-zero hour a day for `days` days, values varying so no day repeats."""
    return [(station, datetime(start.year, start.month, start.day, hour) + timedelta(days=d), round(mm + (d % 5) * 0.7 + d * 0.01, 2)) for d in range(days)]


@pytest_asyncio.fixture(autouse=True)
async def _clean(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    async with async_session_factory() as s:
        for model in (Correction, Proposal, AuditItem, TrainingJob, ShadowRun, ModelScore, ModelVersion, TrainingSnapshot, Review, Observation, PipelineStation, IngestJob):
            await s.execute(delete(model))
        await s.execute(delete(ValidationRun).where(ValidationRun.source == "pipeline"))
        await s.commit()
    yield


async def ingest(c: AsyncClient, text: str, name="tr.csv", source="cwc"):
    r = await c.post("/api/pipeline/ingest", headers=H, data={"source": source, "wait": "true"}, files={"file": (name, text.encode(), "text/csv")})
    assert r.status_code == 202, r.text
    return r.json()


# ---------------------------------------------------------------------------------------------- ingest
@pytest.mark.asyncio
async def test_ingest_stores_rows_lists_bad_ones_and_is_idempotent(async_client: AsyncClient):
    rows = wet_days("Amarpur", datetime(2026, 6, 1), 5)
    text = csv_text(rows) + "99,Amarpur,CWC,16,Tripura,1,G,T,-,-,R,B,T,S,-,L,23.5,91.6,not-a-time,3\n100,Amarpur,CWC,16,Tripura,1,G,T,-,-,R,B,T,S,-,L,23.5,91.6,01-06-2026 20:00,abc\n"
    job = await ingest(async_client, text)
    assert job["status"] == "done" and job["rows_read"] == 7 and job["rows_inserted"] == 5 and job["rows_bad"] == 2 and job["stations"] == 1
    assert {b["row"] for b in job["bad_samples"]} == {6, 7} and "IST" in job["assumptions"]["time_zone"] and "non-zero" in job["assumptions"]["zero_hours"]
    again = await ingest(async_client, text)                                     # same file again: nothing new, nothing overwritten
    assert again["rows_inserted"] == 0 and again["rows_duplicate"] == 5
    async with async_session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Observation))).scalar_one() == 5


@pytest.mark.asyncio
async def test_a_file_without_the_expected_columns_is_rejected_whole(async_client: AsyncClient):
    job = await ingest(async_client, "a,b\n1,2\n")
    assert job["status"] == "failed" and "missing columns" in job["error"] and job["rows_inserted"] == 0


@pytest.mark.asyncio
async def test_ingest_needs_the_admin_session_and_a_known_source(async_client: AsyncClient):
    r = await async_client.post("/api/pipeline/ingest", data={"source": "cwc"}, files={"file": ("x.csv", b"a", "text/csv")})
    assert r.status_code == 401
    r = await async_client.post("/api/pipeline/ingest", headers=H, data={"source": "nope"}, files={"file": ("x.csv", b"a", "text/csv")})
    assert r.status_code == 400 and "unknown source" in r.text


def test_station_keys_fit_the_validation_tables_and_times_are_ist():
    assert len(cwc.station_key("Tripura", "x" * 200)) == 64 and cwc.station_key("Tripura", "Amarpur") == "cwc:tripura:amarpur"
    assert cwc.parse_time("01-06-2026 08:30").isoformat() == "2026-06-01T03:00:00+00:00"


# ---------------------------------------------------------------------------------------------- checks
@pytest.mark.asyncio
async def test_rain_day_boundary_and_flags(async_client: AsyncClient):
    rows = []
    rows += [("Amarpur", datetime(2026, 6, 1, 8, 29), 2.0), ("Amarpur", datetime(2026, 6, 1, 8, 30), 3.0)]        # 02:59 UTC and 03:00 UTC
    rows += BIG_DAY                                                                                                 # 1,473 mm in one rain day: impossible
    rows += [("Amarpur", datetime(2026, 7, d, 12), 7.5) for d in (1, 2, 3, 4)]                                       # the same positive value on 4 days
    job = await ingest(async_client, csv_text(rows))
    r = await async_client.post(f"/api/pipeline/jobs/{job['id']}/check", headers=H, json={})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["source"] == "pipeline" and run["profile"] == "daily"
    detail = (await async_client.get(f"/api/validation/runs/{run['id']}/rows?page_size=50&scope=all&sort=time")).json()["rows"]
    by_day = {x["time"]: x for x in detail}
    assert "2026-06-01" in by_day and "2026-06-02" in by_day                          # 08:29 IST is rain day ending 06-01, 08:30 IST is the next
    assert by_day["2026-06-01"]["verdict"] != "SUSPECT" and "2026-06-10" not in by_day
    big = by_day["2026-06-11"]
    assert big["verdict"] == "SUSPECT" and "impossible_value" in big["checks"]
    assert any(x["verdict"] == "SUSPECT" and "repeated_value" in x["checks"] for x in detail)


@pytest.mark.asyncio
async def test_jobs_cut_off_by_a_restart_are_marked_failed(async_client: AsyncClient):
    from backend.app.pipeline.jobs import fail_interrupted_jobs
    async with async_session_factory() as s:
        s.add_all([IngestJob(source="cwc", filename="a.csv", status="running"), IngestJob(source="cwc", filename="b.csv", status="queued"),
                   IngestJob(source="cwc", filename="c.csv", status="done")])
        await s.commit()
    assert await fail_interrupted_jobs() == 2
    jobs = {j["filename"]: j for j in (await async_client.get("/api/pipeline/jobs")).json()["jobs"]}
    assert jobs["a.csv"]["status"] == "failed" and "restart" in jobs["a.csv"]["error"] and jobs["c.csv"]["status"] == "done"


@pytest.mark.asyncio
async def test_check_needs_a_finished_job_and_data(async_client: AsyncClient):
    assert (await async_client.post("/api/pipeline/jobs/999/check", headers=H, json={})).status_code == 404
    job = await ingest(async_client, "a,b\n1,2\n")
    assert (await async_client.post(f"/api/pipeline/jobs/{job['id']}/check", headers=H, json={})).status_code == 409


# ---------------------------------------------------------------------------------------------- proposals, corrections, labels
async def flagged_run(c: AsyncClient):
    rows = wet_days("Amarpur", datetime(2026, 5, 1), 20) + BIG_DAY
    job = await ingest(c, csv_text(rows))
    run = (await c.post(f"/api/pipeline/jobs/{job['id']}/check", headers=H, json={})).json()
    return run["id"]


@pytest.mark.asyncio
async def test_proposals_are_generated_idempotent_and_change_nothing_until_accepted(async_client: AsyncClient):
    run_id = await flagged_run(async_client)
    made = (await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={})).json()
    kinds = {p["kind"] for p in made["proposals"]}
    assert "exclude_value" in kinds and "review_peak" in kinds and all(p["generated"] and p["status"] == "pending" for p in made["proposals"])
    assert (await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={})).json()["created"] == 0
    async with async_session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Correction))).scalar_one() == 0
        assert (await s.execute(select(func.count()).select_from(Review))).scalar_one() == 0
    pid = next(p["id"] for p in made["proposals"] if p["kind"] == "exclude_value")
    ok = await async_client.post(f"/api/pipeline/proposals/{pid}/decide", headers=H, json={"accept": True, "reviewer": "asha", "note": "stuck telemetry"})
    assert ok.status_code == 200 and ok.json()["status"] == "accepted"
    async with async_session_factory() as s:
        c = (await s.execute(select(Correction))).scalars().one()
        assert c.corrected_mm is None and c.original_mm and c.original_mm > 1000          # excluded, the original value is kept beside it
        assert (await s.execute(select(Review))).scalars().one().decision == "confirmed_fault"
        assert (await s.execute(select(func.count()).select_from(Observation).where(Observation.value_mm == 75.0))).scalar_one() == 14     # raw untouched
    assert (await async_client.post(f"/api/pipeline/proposals/{pid}/decide", headers=H, json={"accept": False})).status_code == 409
    pid2 = next(p["id"] for p in made["proposals"] if p["kind"] == "review_peak")
    assert (await async_client.post(f"/api/pipeline/proposals/{pid2}/decide", headers=H, json={"accept": False})).json()["status"] == "rejected"
    assert (await async_client.post("/api/pipeline/proposals/9999/decide", headers=H, json={"accept": True})).status_code == 404
    assert (await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={"generator": "mcp-narrator"})).status_code == 400   # NOT IMPLEMENTED


# ---------------------------------------------------------------------------------------------- audit sample
@pytest.mark.asyncio
async def test_audit_sample_is_random_weighted_and_estimates_missed_faults(async_client: AsyncClient):
    run_id = await flagged_run(async_client)
    d = (await async_client.post(f"/api/pipeline/runs/{run_id}/audit", headers=H, json={"n": 10, "seed": 7})).json()
    assert d["drawn"] == 10
    same = (await async_client.post(f"/api/pipeline/runs/{run_id}/audit", headers=H, json={"n": 5, "seed": 7})).json()        # never the same day twice
    assert {i["row_ref"] for i in d["items"]}.isdisjoint({i["row_ref"] for i in same["items"]})
    items = (await async_client.get(f"/api/pipeline/runs/{run_id}/audit")).json()["items"]
    assert len(items) == 15 and len({round(i["inclusion_probability"], 12) for i in items}) == 1          # two draws are one sample: one weight for all
    first = items[0]
    assert abs(first["weight"] * first["inclusion_probability"] - 1.0) < 1e-9
    for i, it in enumerate(d["items"]):
        dec = "missed_fault" if i < 2 else ("unsure" if i == 2 else "ok")
        assert (await async_client.post(f"/api/pipeline/audit/{it['id']}/decide", headers=H, json={"decision": dec})).status_code == 200
    est = (await async_client.get(f"/api/pipeline/runs/{run_id}/audit")).json()["estimate"]
    assert est["decided"] == 9 and est["unsure"] == 1 and est["missed_faults"] == 2 and 0 < est["missed_fault_rate"] < 1 and len(est["interval_95"]) == 2
    assert (await async_client.post(f"/api/pipeline/audit/{d['items'][0]['id']}/decide", headers=H, json={"decision": "maybe"})).status_code == 400


# ---------------------------------------------------------------------------------------------- snapshots
@pytest.mark.asyncio
async def test_snapshot_respects_the_cut_the_locked_test_years_and_label_rules(async_client: AsyncClient):
    run_id = await flagged_run(async_client)                         # data in 2026
    await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={})
    pid = (await async_client.get(f"/api/pipeline/proposals?run_id={run_id}")).json()["proposals"][0]["id"]
    await async_client.post(f"/api/pipeline/proposals/{pid}/decide", headers=H, json={"accept": True, "reviewer": "asha"})
    audit = (await async_client.post(f"/api/pipeline/runs/{run_id}/audit", headers=H, json={"n": 4, "seed": 1})).json()["items"]
    for it, dec in zip(audit, ("ok", "ok", "missed_fault", "unsure")):
        await async_client.post(f"/api/pipeline/audit/{it['id']}/decide", headers=H, json={"decision": dec})
    snap = (await async_client.post("/api/pipeline/snapshots", headers=H, json={"cut_day": "2026-12-31"})).json()
    assert snap["n_rows"] == 4 and snap["manifest"]["random_sample_rows"] == 3 and snap["manifest"]["excluded_years"] == list(range(2018, 2026))
    data = await async_client.get(f"/api/pipeline/snapshots/{snap['id']}/data.jsonl")
    assert data.headers["x-snapshot-sha256"] == snap["sha256"] and data.text.count("\n") == 3 and '"label_tier":"real_reviewer"' in data.text
    assert '"label":"fault"' in data.text and '"label":"clean"' in data.text and "unsure" not in data.text
    early = (await async_client.post("/api/pipeline/snapshots", headers=H, json={"cut_day": "2026-05-15"})).json()          # nothing after the cut
    assert early["n_rows"] < snap["n_rows"] and early["manifest"]["skipped"]["after_cut"] > 0
    locked = (await async_client.post("/api/pipeline/snapshots", headers=H, json={"cut_day": "2026-12-31", "exclude_years": list(range(2018, 2027))})).json()
    assert locked["n_rows"] == 0 and locked["manifest"]["skipped"]["excluded_year"] > 0                                        # an excluded year is left out


# ---------------------------------------------------------------------------------------------- registry and gate
GOOD = {"recall_at_budget": 0.60, "false_alarms_per_1000": 4.0, "protected_extremes_flagged": 2, "false_alarm_budget_per_1000": 5.0,
        "frozen_protocol": True, "test_years_untouched": True}


def test_gate_rules():
    g = registry.evaluate_gate(GOOD, None)
    assert g["passed"] and any(c["rule"] == "no_champion_yet" for c in g["checks"])
    assert not registry.evaluate_gate({**GOOD, "false_alarms_per_1000": 6.0}, None)["passed"]
    assert not registry.evaluate_gate({**GOOD, "test_years_untouched": False}, None)["passed"]
    assert not registry.evaluate_gate({k: v for k, v in GOOD.items() if k != "recall_at_budget"}, None)["passed"]
    assert registry.evaluate_gate({**GOOD, "recall_at_budget": 0.62}, GOOD)["passed"]
    assert not registry.evaluate_gate({**GOOD, "recall_at_budget": 0.55}, GOOD)["passed"]
    assert not registry.evaluate_gate({**GOOD, "protected_extremes_flagged": 3}, GOOD)["passed"]


@pytest.mark.asyncio
async def test_register_promote_reject_and_roll_back(async_client: AsyncClient):
    reg = lambda v, m: async_client.post("/api/pipeline/models", headers=H, json={"name": "stnet", "version": v, "metrics": m})
    a = (await reg("1", GOOD)).json()
    assert a["alias"] == "challenger" and a["metrics_basis"].startswith("declared")
    assert (await async_client.post(f"/api/pipeline/models/{a['id']}/promote", headers=H)).json()["alias"] == "champion"
    worse = (await reg("2", {**GOOD, "recall_at_budget": 0.40})).json()
    r = (await async_client.post(f"/api/pipeline/models/{worse['id']}/promote", headers=H)).json()
    assert r["alias"] == "rejected" and not r["gate"]["passed"]
    better = (await reg("3", {**GOOD, "recall_at_budget": 0.70})).json()
    assert (await async_client.post(f"/api/pipeline/models/{better['id']}/promote", headers=H)).json()["alias"] == "champion"
    models = {m["version"]: m["alias"] for m in (await async_client.get("/api/pipeline/models")).json()["models"]}
    assert models == {"1": "archived", "2": "rejected", "3": "champion"}
    assert (await async_client.post(f"/api/pipeline/models/{better['id']}/promote", headers=H)).status_code == 409
    back = (await async_client.post("/api/pipeline/models/stnet/rollback", headers=H)).json()
    assert back["version"] == "1" and back["alias"] == "champion"
    assert (await async_client.post("/api/pipeline/models", headers=H, json={"name": "x", "version": "1", "metrics": {}, "snapshot_id": 9999})).status_code == 404


@pytest.mark.asyncio
async def test_status_lists_what_is_not_implemented(async_client: AsyncClient):
    st = (await async_client.get("/api/pipeline/status")).json()
    assert st["sources"] == ["cwc"] and any("scoring with the RF25 STNet" in x for x in st["not_implemented"])


# ---------------------------------------------------------------------------------------------- AI proposer (Gemini layer, fake LLM)
class FakeLLM:
    generator = "gemini"

    def __init__(self, label="false_alarm", fail_after=None):
        self.label, self.fail_after, self.calls = label, fail_after, 0

    async def propose_label(self, evidences):
        from backend.app.validation.explain import NarratorRateLimited
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise NarratorRateLimited("quota used up")
        self.calls += 1
        return {"label": self.label, "reason": f"Evidence of {len(evidences)} check(s) reviewed."}


@pytest.mark.asyncio
async def test_ai_proposals_need_a_connected_llm(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")      # never reach the real API from a test, whatever the local .env holds
    monkeypatch.setattr(settings, "NARRATOR_URL", "")
    run_id = await flagged_run(async_client)
    r = await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={"generator": "ai"})
    assert r.status_code == 503 and "no AI proposer" in r.json()["detail"]


@pytest.mark.asyncio
async def test_ai_proposals_are_generated_idempotent_and_accepting_records_the_reviewers_label(async_client: AsyncClient):
    from backend.app.main import app
    from backend.app.validation import narrate
    llm = FakeLLM("genuine_extreme")
    app.dependency_overrides[narrate.get_narrator] = lambda: llm
    try:
        run_id = await flagged_run(async_client)
        made = (await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={"generator": "ai"})).json()
        assert made["created"] >= 1 and made["stopped"] is None
        assert all(p["kind"] == "llm_genuine_extreme" and p["generator"] == "gemini" and p["generated"] and p["status"] == "pending" for p in made["proposals"])
        again = (await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={"generator": "ai"})).json()
        assert again["created"] == 0 and llm.calls == made["created"]            # a second press asks the LLM nothing new
        async with async_session_factory() as s:
            assert (await s.execute(select(func.count()).select_from(Review))).scalar_one() == 0     # generating changed no decision
        pid = made["proposals"][0]["id"]
        ok = (await async_client.post(f"/api/pipeline/proposals/{pid}/decide", headers=H, json={"accept": True, "reviewer": "asha"})).json()
        assert ok["status"] == "accepted"
        async with async_session_factory() as s:
            rv = (await s.execute(select(Review))).scalars().all()
            assert [r.decision for r in rv] == ["genuine_extreme"]
            assert (await s.execute(select(func.count()).select_from(Correction))).scalar_one() == 0   # a label is not a correction
            for res in (await s.execute(select(ValidationResult).where(ValidationResult.run_id == run_id))).scalars():
                assert res.verdict in ("OK", "SUSPECT", "UNCERTAIN", "NO_DATA")                          # verdicts untouched
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ai_proposals_stop_on_quota_and_keep_what_was_made(async_client: AsyncClient):
    from backend.app.main import app
    from backend.app.validation import narrate
    llm = FakeLLM(fail_after=0)
    app.dependency_overrides[narrate.get_narrator] = lambda: llm
    try:
        run_id = await flagged_run(async_client)
        r = await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={"generator": "ai"})
        assert r.status_code == 502 and "quota" in r.json()["detail"]      # nothing made, so the reason is the answer
        async with async_session_factory() as s:
            assert (await s.execute(select(func.count()).select_from(Proposal))).scalar_one() == 0
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------------------------- scoring with a registered model, shadow run
def fusion_metrics(w_impossible: float, bias: float, threshold: float = 0.5):
    from backend.app.pipeline import fusion
    weights = [w_impossible if c == "impossible_value" else 0.1 for c in fusion.CHECKS]
    return {"kind": "label_fusion", "artifact": {"kind": "label_fusion", "checks": list(fusion.CHECKS), "weights": weights, "bias": bias, "threshold": threshold}}


async def register_model(metrics, name="label-fusion", version="t1", alias="challenger"):
    async with async_session_factory() as s:
        m = await registry.register(s, name, version, metrics)
        m.alias = alias
        await s.commit()
        return m.id


async def flagged_rows(run_id):
    async with async_session_factory() as s:
        return (await s.execute(select(ValidationResult).where(ValidationResult.run_id == run_id, ValidationResult.verdict.in_(("SUSPECT", "UNCERTAIN"))))).scalars().all()


@pytest.mark.asyncio
async def test_scoring_stores_scores_apart_and_puts_a_provider_block_in_the_evidence(async_client: AsyncClient):
    import json
    from pathlib import Path
    import jsonschema
    run_id = await flagged_run(async_client)
    row = (await flagged_rows(run_id))[0]
    ev_url = f"/api/validation/runs/{run_id}/rows/{row.id}/evidence"
    assert all("provider" not in e for e in (await async_client.get(ev_url)).json()["evidence"])      # nothing scored yet: no block, never invented
    mid = await register_model(fusion_metrics(6.0, -3.0))
    out = await async_client.post(f"/api/pipeline/runs/{run_id}/score", headers=H, json={"model_id": mid})
    assert out.status_code == 200 and out.json()["flagged"] >= 1 and out.json()["rows"] >= 1
    evs = (await async_client.get(ev_url)).json()["evidence"]
    prov = evs[0]["provider"]
    assert prov["label_tier"] == "reviewer_labels" and prov["calibrated"] is False and prov["flagged"] is True and 0.5 <= prov["score"] <= 1
    schema = json.loads((Path(__file__).resolve().parents[1] / "docs/contracts/evidence-v1.schema.json").read_text(encoding="utf8"))
    jsonschema.validate(evs[0], schema)                                                              # the block matches the contract
    again = (await async_client.post(f"/api/pipeline/runs/{run_id}/score", headers=H, json={"model_id": mid})).json()
    async with async_session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(ModelScore))).scalar_one() == again["rows"]   # re-scoring replaces, never duplicates
        after = (await s.execute(select(ValidationResult).where(ValidationResult.id == row.id))).scalar_one()
        assert (after.verdict, after.rule_score) == (row.verdict, row.rule_score)                    # the verdict and rule score are untouched
    listed = (await async_client.get(f"/api/pipeline/runs/{run_id}/scores?model_id={mid}&flagged_only=true")).json()["scores"]
    assert listed and all(x["flagged"] for x in listed)


@pytest.mark.asyncio
async def test_a_model_that_cannot_score_on_the_server_says_so(async_client: AsyncClient):
    run_id = await flagged_run(async_client)
    stnet = await register_model({"kind": "stnet", "recall_at_budget": 0.6})
    r = await async_client.post(f"/api/pipeline/runs/{run_id}/score", headers=H, json={"model_id": stnet})
    assert r.status_code == 422 and "NOT IMPLEMENTED" in r.json()["detail"]
    assert (await async_client.post(f"/api/pipeline/runs/{run_id}/score", headers=H, json={"model_id": 9999})).status_code == 404


@pytest.mark.asyncio
async def test_shadow_run_compares_champion_and_challenger_on_reviewed_rows(async_client: AsyncClient):
    run_id = await flagged_run(async_client)
    row = (await flagged_rows(run_id))[0]
    async with async_session_factory() as s:
        s.add(Review(run_id=run_id, row_ref=row.row_ref, station_id=row.station_id, decision="confirmed_fault", reviewer="asha", verdict_at_review=row.verdict))
        await s.commit()
    champ = await register_model(fusion_metrics(6.0, -3.0), version="champ", alias="champion")
    weak = await register_model(fusion_metrics(0.5, -3.0), version="weak")
    r = await async_client.post(f"/api/pipeline/runs/{run_id}/shadow", headers=H, json={"model_id": weak})
    assert r.status_code == 200
    rep = r.json()["report"]
    assert rep["reviewed_rows_used"] == 1 and rep["champion"]["model_id"] == champ and "not ground truth" in rep["note"]
    assert rep["champion"]["recall_on_reviewed"] == 1.0 and rep["challenger"]["recall_on_reviewed"] == 0.0 and rep["disagreements"] >= 1
    assert (await async_client.get(f"/api/pipeline/models/{weak}/shadow")).json()["shadow"]["id"] == r.json()["id"]
    assert (await async_client.post(f"/api/pipeline/runs/{run_id}/shadow", headers=H, json={"model_id": champ})).status_code == 422   # not a challenger


def test_shadow_rules_never_pass_by_default():
    from backend.app.pipeline import scoring
    assert scoring.evaluate_shadow(None)["passed"] is False
    base = {"rows": 10, "reviewed_rows_used": 4, "note": "n"}
    good = {**base, "challenger": {"recall_on_reviewed": 1.0, "false_alarms_flagged": 0, "genuine_extremes_flagged": 0},
            "champion": {"recall_on_reviewed": 0.5, "false_alarms_flagged": 1, "genuine_extremes_flagged": 1}}
    assert scoring.evaluate_shadow(good)["passed"] is True
    worse = {**good, "challenger": {"recall_on_reviewed": 0.2, "false_alarms_flagged": 0, "genuine_extremes_flagged": 0}}
    assert scoring.evaluate_shadow(worse)["passed"] is False
    no_faults = {**good, "challenger": {"recall_on_reviewed": None, "false_alarms_flagged": 0, "genuine_extremes_flagged": 0}}
    assert scoring.evaluate_shadow(no_faults)["passed"] is False          # no reviewed fault: cannot show the challenger is better


@pytest.mark.asyncio
async def test_promote_with_require_shadow_keeps_a_challenger_without_a_shadow_run(async_client: AsyncClient):
    mid = await register_model(fusion_metrics(6.0, -3.0))
    r = await async_client.post(f"/api/pipeline/models/{mid}/promote?require_shadow=true", headers=H)
    assert r.status_code == 200 and r.json()["alias"] == "challenger"
    assert any(c["rule"] == "shadow_run_done" and not c["passed"] for c in r.json()["gate"]["checks"])


@pytest.mark.asyncio
async def test_run_export_lays_scores_proposals_and_corrections_beside_the_data(async_client: AsyncClient):
    from backend.app.main import app
    from backend.app.validation import narrate
    run_id = await flagged_run(async_client)
    plain_csv = (await async_client.get(f"/api/validation/runs/{run_id}/export.csv")).text.splitlines()[0]
    assert "model_score" not in plain_csv and "ai_proposal" not in plain_csv          # no model columns until a model has scored the run
    mid = await register_model(fusion_metrics(6.0, -3.0))
    await async_client.post(f"/api/pipeline/runs/{run_id}/score", headers=H, json={"model_id": mid})
    props = (await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={})).json()["proposals"]
    app.dependency_overrides[narrate.get_narrator] = lambda: FakeLLM("needs_followup")
    try:
        await async_client.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={"generator": "ai"})
    finally:
        app.dependency_overrides.clear()
    pid = next(p["id"] for p in props if p["kind"] == "exclude_value")
    await async_client.post(f"/api/pipeline/proposals/{pid}/decide", headers=H, json={"accept": True, "reviewer": "asha"})
    ex = (await async_client.get(f"/api/validation/runs/{run_id}/export.json")).json()
    assert "none of them changes a verdict" in ex["pipeline_note"]
    flagged = [r for r in ex["rows"] if r["model_scores"]]
    assert flagged and all(set(r) >= {"model_scores", "proposals", "corrections"} for r in ex["rows"])
    row = next(r for r in ex["rows"] if r["corrections"])
    assert row["corrections"][0]["corrected_mm"] is None and row["original_row"]                     # the original stays, the exclusion is beside it
    assert any(p["generator"] == "gemini" and p["generated"] for r in ex["rows"] for p in r["proposals"])
    head, *lines = (await async_client.get(f"/api/validation/runs/{run_id}/export.csv")).text.splitlines()
    assert "model_score" in head and "model_flagged" in head and "ai_proposal" in head
    assert any("[AI-generated, pending] llm_needs_followup" in ln for ln in lines)


@pytest.mark.asyncio
async def test_exported_score_file_gives_a_provider_block_only_where_it_covers_the_station_and_day(async_client: AsyncClient, tmp_path, monkeypatch):
    import numpy as np
    from tests.test_score_provider import write
    run_id = await flagged_run(async_client)
    row = (await flagged_rows(run_id))[0]
    ev_url = f"/api/validation/runs/{run_id}/rows/{row.id}/evidence"
    day = row.time_key[:10]
    f = write(tmp_path / "s.npz", scores=np.array([[3.2]], dtype=np.float32), periods=(day,), lat=(23.5,), lon=(91.6,), threshold=1.0, budget=5.0,
              faults={"drift": np.array([[0.7]], dtype=np.float32)})
    monkeypatch.setattr(settings, "SCORE_EXPORT_PATH", f)
    prov = (await async_client.get(ev_url)).json()["evidence"][0]["provider"]
    assert prov["model_kind"] == "stnet" and prov["flagged"] is True and prov["fault_scores"]["drift"] == pytest.approx(0.7) and prov["label_tier"] == "synthetic"
    other = write(tmp_path / "o.npz", scores=np.array([[3.2]], dtype=np.float32), periods=("1999-01-01",), lat=(23.5,), lon=(91.6,))
    monkeypatch.setattr(settings, "SCORE_EXPORT_PATH", other)
    assert "provider" not in (await async_client.get(ev_url)).json()["evidence"][0]            # the file does not cover that day: no block
    monkeypatch.setattr(settings, "SCORE_EXPORT_PATH", str(tmp_path / "missing.npz"))
    assert (await async_client.get(ev_url)).status_code == 200                                  # a bad file is logged, never a crash

