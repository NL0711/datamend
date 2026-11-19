"""Overview, Data Explorer, event-forensics context, the admin review loop, the synthetic Anomaly Lab and the gauge catalogue.
Generated data only; a throwaway database; no network."""
import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.validation import lab, review as review_svc, runs as svc
from backend.app.validation.models import Explanation, Review, ValidationCheckHit, ValidationResult, ValidationRun
from backend.app.validation.records import Reading

TOKEN = "t" * 32
H = {"X-Admin-Token": TOKEN}
T0 = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture(autouse=True)
async def _clean(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    from backend.app.api import settings as settings_api
    settings_api._failures.clear()
    async with async_session_factory() as s:
        for m in (Review, Explanation, ValidationCheckHit, ValidationResult, ValidationRun):
            await s.execute(delete(m))
        await s.commit()
    yield


async def lab_run(client: AsyncClient, profile="reading", seed=1, **kw):
    body = {"profile": profile, "n_stations": 6, "length": 144 if profile == "reading" else 60, "faults": list(lab.FAULTS[profile]), "seed": seed, **kw}
    r = await client.post("/api/validation/lab/generate", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def flagged_rows(client: AsyncClient, run_id: int):
    return (await client.get(f"/api/validation/runs/{run_id}/rows")).json()["rows"]


# ---------------------------------------------------------------- Anomaly Lab
def test_generator_is_deterministic_and_differs_by_seed():
    a, b, c = (lab.generate("reading", 6, 144, lab.FAULTS["reading"], s) for s in (7, 7, 8))
    assert hashlib.sha256(a.content).digest() == hashlib.sha256(b.content).digest() and a.injected == b.injected
    assert a.content != c.content
    assert a.filename == "lab-reading-seed7.csv" and a.n_rows == 6 * 144 and len(a.injected) == 5


@pytest.mark.parametrize("profile", ["reading", "daily"])
def test_injected_faults_sit_on_distinct_stations_with_the_check_each_should_trigger(profile):
    f = lab.generate(profile, 6, 144 if profile == "reading" else 60, lab.FAULTS[profile], 3)
    assert len({i["station_id"] for i in f.injected}) == len(f.injected)
    assert {i["expected_check"] for i in f.injected} <= set(lab.EXPECTED_CHECK.values())
    rows = list(csv.DictReader(io.StringIO(f.content.decode())))
    assert all(1 <= int(i["row_ref"]) <= len(rows) for i in f.injected)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["reading", "daily"])
@pytest.mark.parametrize("seed", [1, 2, 3])
async def test_lab_run_is_synthetic_and_the_real_pipeline_catches_every_injected_fault(async_client: AsyncClient, profile, seed):
    out = await lab_run(async_client, profile, seed)
    assert out["run"]["synthetic"] is True and out["summary"]["label"] == "SYNTHETIC" and "not an accuracy measurement" in out["note"]
    assert out["summary"]["injected"] == len(lab.FAULTS[profile])
    missed = [i for i in out["injected"] if not i["caught"]]
    assert missed == [] and out["summary"]["caught"] == out["summary"]["injected"]


@pytest.mark.asyncio
async def test_lab_with_a_subset_of_faults_only_injects_those(async_client: AsyncClient):
    out = await lab_run(async_client, "reading", 4, faults=["negative_value"])
    assert [i["fault"] for i in out["injected"]] == ["negative_value"] and out["injected"][0]["caught"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("body,msg", [
    ({"faults": []}, "at least one fault"),
    ({"faults": ["teleport"]}, "unknown fault"),
    ({"profile": "daily", "length": 60, "faults": ["counter_jump"]}, "unknown fault"),
])
async def test_lab_refuses_impossible_requests(async_client: AsyncClient, body, msg):
    r = await async_client.post("/api/validation/lab/generate", json={"profile": "reading", "faults": ["counter_jump"], **body})
    assert r.status_code == 422 and msg in r.text


@pytest.mark.asyncio
async def test_a_repeated_fault_name_is_injected_once(async_client: AsyncClient):
    out = await lab_run(async_client, "reading", 5, n_stations=5, faults=["counter_jump", "counter_jump"])
    assert len(out["injected"]) == 1 and out["injected"][0]["caught"] is True


@pytest.mark.asyncio
async def test_lab_input_limits_are_validated(async_client: AsyncClient):
    for bad in ({"n_stations": 4}, {"n_stations": 11}, {"length": 29}, {"length": 289}, {"seed": -1}, {"profile": "weekly"}):
        r = await async_client.post("/api/validation/lab/generate", json={"faults": ["counter_jump"], **bad})
        assert r.status_code == 422, bad
    short = await async_client.post("/api/validation/lab/generate", json={"profile": "reading", "length": 100, "faults": ["counter_jump"]})
    assert short.status_code == 422 and "between 120 and 288" in short.text
    opts = (await async_client.get("/api/validation/lab/options")).json()
    assert opts["label"] == "SYNTHETIC" and opts["faults"]["daily"] == ["repeated_value", "impossible_value", "isolated_wet"]


# ---------------------------------------------------------------- Data Explorer and event forensics
@pytest.mark.asyncio
async def test_explorer_pages_every_row_in_time_order_and_filters_by_time(async_client: AsyncClient):
    run = (await lab_run(async_client, "daily", 1))["run"]
    base = f"/api/validation/runs/{run['id']}/rows"
    flagged = (await async_client.get(base)).json()
    allrows = (await async_client.get(f"{base}?scope=all&sort=time&station=LAB-01")).json()
    assert allrows["total"] == 60 and allrows["total"] > flagged["total"] and len(allrows["rows"]) == 50
    times = [r["time"] for r in allrows["rows"]]
    assert times == sorted(times) and {r["verdict"] for r in allrows["rows"]} >= {"OK"}
    assert {"intensity", "accumulation", "mm"} <= set(allrows["rows"][0])
    win = (await async_client.get(f"{base}?scope=all&sort=time&station=LAB-01&time_from=2026-07-05&time_to=2026-07-07")).json()
    assert [r["time"] for r in win["rows"]] == ["2026-07-05", "2026-07-06", "2026-07-07"]
    assert (await async_client.get(f"{base}?time_from=yesterday")).status_code == 422
    assert (await async_client.get(f"{base}?scope=bogus")).status_code == 422
    assert (await async_client.get(f"{base}?sort=bogus")).status_code == 422
    assert all(r["verdict"] in ("SUSPECT", "UNCERTAIN") for r in flagged["rows"])        # the default is unchanged


@pytest.mark.asyncio
async def test_context_returns_the_neighbouring_rows_in_order(async_client: AsyncClient):
    out = await lab_run(async_client, "daily", 1)
    run_id = out["run"]["id"]
    target = (await flagged_rows(async_client, run_id))[0]
    ctx = (await async_client.get(f"/api/validation/runs/{run_id}/rows/{target['id']}/context?before=3&after=2")).json()
    ids = [r["id"] for r in ctx["rows"]]
    assert target["id"] in ids and ctx["selected_id"] == target["id"] and ctx["station_id"] == target["station_id"]
    times = [r["time"] for r in ctx["rows"]]
    assert times == sorted(times) and len(ctx["rows"]) <= 6
    assert ids.index(target["id"]) <= 3 and len(ids) - 1 - ids.index(target["id"]) <= 2
    assert (await async_client.get(f"/api/validation/runs/{run_id}/rows/{target['id']}/context?before=99")).status_code == 422
    assert (await async_client.get(f"/api/validation/runs/{run_id}/rows/999999/context")).status_code == 404


# ---------------------------------------------------------------- overview
@pytest.mark.asyncio
async def test_overview_counts_runs_rows_and_keeps_synthetic_apart(async_client: AsyncClient):
    empty = (await async_client.get("/api/validation/overview")).json()
    assert empty["runs"]["total"] == 0 and empty["latest_run"] is None and empty["rows"]["total"] == 0
    await lab_run(async_client, "daily", 1)
    real = "day,station_id,mm\n2026-07-01,A,1\n2026-07-02,A,-1\n"
    await async_client.post("/api/validation/runs", files={"file": ("r.csv", real.encode(), "text/csv")}, data={"profile": "daily"})
    await async_client.post("/api/validation/runs", files={"file": ("bad.csv", b"x", "text/csv")}, data={"profile": "reading"})     # rejected
    ov = (await async_client.get("/api/validation/overview")).json()
    assert ov["runs"] == {"total": 3, "completed": 2, "open_live": 0, "rejected_uploads": 1}
    assert ov["rows"] == {"total": 6 * 60 + 2, "uploaded_or_live": 2, "synthetic": 360}
    assert ov["verdicts"]["SUSPECT"] >= 1 and ov["checks_fired"].get("impossible_value") == 2     # one injected by the lab, one negative day uploaded
    assert ov["latest_run"]["label"] == "r.csv" and "accuracy" in ov["note"]


# ---------------------------------------------------------------- the admin review loop
async def one_flagged(client: AsyncClient):
    out = await lab_run(client, "daily", 1)
    row = (await flagged_rows(client, out["run"]["id"]))[0]
    return out["run"]["id"], row


@pytest.mark.asyncio
async def test_a_review_needs_the_admin_token(async_client: AsyncClient, monkeypatch):
    run_id, row = await one_flagged(async_client)
    url = f"/api/validation/runs/{run_id}/rows/{row['id']}/review"
    body = {"decision": "confirmed_fault", "note": "looks stuck", "reviewer": "asha"}
    assert (await async_client.post(url, json=body)).status_code == 401
    assert (await async_client.post(url, json=body, headers={"X-Admin-Token": "wrong" * 8})).status_code == 401
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    assert (await async_client.post(url, json=body, headers=H)).status_code == 403
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    ok = await async_client.post(url, json=body, headers=H)
    assert ok.status_code == 201 and ok.json()["decision"] == "confirmed_fault" and ok.json()["reviewer"] == "asha" and ok.json()["verdict_at_review"] == row["verdict"]
    listed = (await async_client.get(f"/api/validation/runs/{run_id}/rows/{row['id']}/reviews")).json()          # reading is open
    assert [r["note"] for r in listed["reviews"]] == ["looks stuck"] and "false_alarm" in listed["decisions"]


@pytest.mark.asyncio
async def test_a_review_never_changes_the_verdict_score_or_evidence(async_client: AsyncClient):
    run_id, row = await one_flagged(async_client)
    before = (await async_client.get(f"/api/validation/runs/{run_id}/rows/{row['id']}")).json()
    ev_before = (await async_client.get(f"/api/validation/runs/{run_id}/rows/{row['id']}/evidence")).json()
    for d in ("false_alarm", "genuine_extreme", "confirmed_fault"):
        assert (await async_client.post(f"/api/validation/runs/{run_id}/rows/{row['id']}/review", json={"decision": d}, headers=H)).status_code == 201
    after = (await async_client.get(f"/api/validation/runs/{run_id}/rows/{row['id']}")).json()
    assert (after["verdict"], after["rule_score"], after["severity"], after["hits"]) == (before["verdict"], before["rule_score"], before["severity"], before["hits"])
    assert (await async_client.get(f"/api/validation/runs/{run_id}/rows/{row['id']}/evidence")).json() == ev_before


@pytest.mark.asyncio
async def test_review_input_is_validated_and_only_flagged_rows_can_be_reviewed(async_client: AsyncClient):
    run_id, row = await one_flagged(async_client)
    url = f"/api/validation/runs/{run_id}/rows/{row['id']}/review"
    assert (await async_client.post(url, json={"decision": "maybe"}, headers=H)).status_code == 422
    assert (await async_client.post(url, json={}, headers=H)).status_code == 422
    assert (await async_client.post(url, json={"decision": "false_alarm", "note": "x" * 1001}, headers=H)).status_code == 422
    assert (await async_client.post(url, json={"decision": "false_alarm", "reviewer": "x" * 61}, headers=H)).status_code == 422
    ok_row = (await async_client.get(f"/api/validation/runs/{run_id}/rows?verdict=OK")).json()["rows"][0]
    r = await async_client.post(f"/api/validation/runs/{run_id}/rows/{ok_row['id']}/review", json={"decision": "false_alarm"}, headers=H)
    assert r.status_code == 422 and "only flagged rows" in r.text
    assert (await async_client.post(f"/api/validation/runs/{run_id}/rows/999999/review", json={"decision": "false_alarm"}, headers=H)).status_code == 404


@pytest.mark.asyncio
async def test_queue_lists_flags_across_runs_and_moves_a_row_when_it_is_reviewed(async_client: AsyncClient):
    a = (await lab_run(async_client, "daily", 1))["run"]["id"]
    b = (await lab_run(async_client, "reading", 2))["run"]["id"]
    q = (await async_client.get("/api/validation/review/queue")).json()
    assert q["status"] == "unreviewed" and {r["run_id"] for r in q["rows"]} == {a, b} and all(r["synthetic"] for r in q["rows"])
    scores = [r["rule_score"] for r in q["rows"]]
    assert scores == sorted(scores, reverse=True) and q["page_size"] == 50 and all(r["review"] is None for r in q["rows"])
    first = q["rows"][0]
    await async_client.post(f"/api/validation/runs/{first['run_id']}/rows/{first['id']}/review", json={"decision": "genuine_extreme", "note": "storm"}, headers=H)
    after = (await async_client.get("/api/validation/review/queue")).json()
    assert after["total"] == q["total"] - 1 and first["id"] not in {r["id"] for r in after["rows"]}
    done = (await async_client.get("/api/validation/review/queue?status=reviewed")).json()
    assert [r["id"] for r in done["rows"]] == [first["id"]] and done["rows"][0]["review"]["decision"] == "genuine_extreme"
    everything = (await async_client.get("/api/validation/review/queue?status=all")).json()
    assert everything["total"] == q["total"]
    only_a = (await async_client.get(f"/api/validation/review/queue?status=all&run_id={a}")).json()
    assert {r["run_id"] for r in only_a["rows"]} == {a}
    assert {r["verdict"] for r in (await async_client.get("/api/validation/review/queue?verdict=UNCERTAIN&status=all")).json()["rows"]} <= {"UNCERTAIN"}
    chk = (await async_client.get("/api/validation/review/queue?check=impossible_value&status=all")).json()
    assert chk["total"] >= 1 and all("impossible_value" in r["checks"] for r in chk["rows"])
    assert (await async_client.get("/api/validation/review/queue?synthetic=false&status=all")).json()["total"] == 0
    assert (await async_client.get("/api/validation/review/queue?page_size=500")).status_code == 422
    assert (await async_client.get("/api/validation/review/queue?status=bogus")).status_code == 422


@pytest.mark.asyncio
async def test_the_latest_review_counts_and_the_summary_says_what_it_is_not(async_client: AsyncClient):
    run_id, row = await one_flagged(async_client)
    url = f"/api/validation/runs/{run_id}/rows/{row['id']}/review"
    await async_client.post(url, json={"decision": "false_alarm"}, headers=H)
    await async_client.post(url, json={"decision": "confirmed_fault", "note": "changed my mind"}, headers=H)
    s = (await async_client.get("/api/validation/review/summary")).json()
    assert s["reviewed_rows"] == 1 and s["by_decision"] == {"confirmed_fault": 1, "false_alarm": 0, "genuine_extreme": 0, "needs_followup": 0}
    assert s["flagged_rows"] >= 1 and s["unreviewed_rows"] == s["flagged_rows"] - 1
    assert row["checks"][0] in s["by_check"] and s["by_check"][row["checks"][0]]["confirmed_fault"] == 1
    assert "not precision or recall" in s["caveat"] and "not ground truth" in s["caveat"].lower()
    q = (await async_client.get("/api/validation/review/queue?status=reviewed")).json()["rows"][0]
    assert q["review"]["decision"] == "confirmed_fault" and q["review"]["note"] == "changed my mind"


@pytest.mark.asyncio
async def test_exports_carry_the_reviews(async_client: AsyncClient):
    run_id, row = await one_flagged(async_client)
    await async_client.post(f"/api/validation/runs/{run_id}/rows/{row['id']}/review", json={"decision": "needs_followup", "note": "ask the site"}, headers=H)
    js = (await async_client.get(f"/api/validation/runs/{run_id}/export.json")).json()
    rev = [r["review"] for r in js["rows"] if r["review"]]
    assert len(rev) == 1 and rev[0]["decision"] == "needs_followup" and rev[0]["note"] == "ask the site" and "not ground truth" in js["review_note"]
    rows = list(csv.DictReader(io.StringIO((await async_client.get(f"/api/validation/runs/{run_id}/export.csv")).text)))
    assert [r["review_decision"] for r in rows if r["review_decision"]] == ["needs_followup"]


@pytest.mark.asyncio
async def test_reviews_survive_a_live_run_rescoring_and_go_with_a_pruned_run():
    def rds(n, bad=False):
        return [Reading("weather_union", "S1", T0 + timedelta(minutes=15 * i), -1.0 if (bad and i == n - 1) else 0.0, 0.0, "received", "cumulative", False, f"S1@{i}") for i in range(n)]
    async with async_session_factory() as s:
        run = await svc.refresh_live_run(s, rds(5, bad=True), date(2026, 7, 2), 15, "cumulative")
        row = (await s.execute(select(ValidationResult).where(ValidationResult.run_id == run.id, ValidationResult.verdict == "SUSPECT"))).scalars().first()
        await review_svc.add_review(s, row, "false_alarm", "test", "me")
        run = await svc.refresh_live_run(s, rds(6, bad=False) + [], date(2026, 7, 2), 15, "cumulative")        # re-scored: the result rows are replaced
        kept = await review_svc.reviews_for_row(s, run.id, "S1@4")
        assert [r.decision for r in kept] == ["false_alarm"]
        await svc._delete_runs(s, [run.id])
        await s.commit()
        assert (await s.execute(select(Review).where(Review.run_id == run.id))).scalars().first() is None


# ---------------------------------------------------------------- gauge catalogue
@pytest.mark.asyncio
async def test_gauge_catalogue_lists_stations_with_their_cells(async_client: AsyncClient):
    body = (await async_client.get("/api/places/stations?city=Mumbai&limit=5")).json()
    assert body["count"] > 5 and body["shown"] == 5 and "Mumbai" in body["cities"]
    s = body["stations"][0]
    assert s["city"] == "Mumbai" and {"station_id", "place", "latitude", "longitude", "device", "cell", "is_land"} <= set(s) and s["cell"]["grid"].startswith("RF25")
    assert (await async_client.get("/api/places/stations?city=Atlantis")).json()["count"] == 0
    assert (await async_client.get("/api/places/stations?limit=0")).status_code == 422
