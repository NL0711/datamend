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
from backend.app.pipeline.models import (AuditItem, Correction, IngestJob, ModelVersion, Observation, PipelineStation, Proposal, TrainingJob,
                                          TrainingSnapshot)
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
        for model in (Correction, Proposal, AuditItem, TrainingJob, ModelVersion, TrainingSnapshot, Review, Observation, PipelineStation, IngestJob):
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
    assert st["sources"] == ["cwc", "isd"] and any("scoring with a registered model" in x for x in st["not_implemented"])

