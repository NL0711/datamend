"""Regression tests for the defects an independent review found in the bulk-ingest and feedback-loop code. Generated data only; no network."""
import asyncio
import math
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from backend.app.api import auth as auth_api
from backend.app.api import pipeline as pipeline_api
from backend.app.api import settings as settings_api
from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.main import app
from backend.app.pipeline import cwc, fusion, jobs as jobs_svc, kaggle_trigger, registry, training
from backend.app.pipeline.models import (AuditItem, Correction, IngestJob, ModelVersion, Observation, PipelineStation, Proposal, TrainingJob,
                                          TrainingSnapshot)
from backend.app.validation.models import Review, ValidationRun
from tests.test_pipeline import BIG_DAY, GOOD, H, TOKEN, csv_text, flagged_run, ingest, line, wet_days


@pytest_asyncio.fixture(autouse=True)
async def _clean(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "KAGGLE_USERNAME", "")
    monkeypatch.setattr(settings, "KAGGLE_KEY", "")
    for bucket in (auth_api._failures, getattr(auth_api, "_token_failures", None), settings_api._failures):
        if bucket is not None:
            bucket.clear()
    if hasattr(pipeline_api, "_obs_count_cache"):
        pipeline_api._obs_count_cache.update(at=0.0, n=0, bind=None)
    async with async_session_factory() as s:
        for model in (Correction, Proposal, AuditItem, TrainingJob, ModelVersion, TrainingSnapshot, Review, Observation, PipelineStation, IngestJob):
            await s.execute(delete(model))
        await s.execute(delete(ValidationRun).where(ValidationRun.source == "pipeline"))
        await s.commit()
    yield


async def decide_exclude(c: AsyncClient, run_id: int, kind="exclude_value"):
    await c.post(f"/api/pipeline/runs/{run_id}/proposals", headers=H, json={})                 # repeating it creates nothing new
    made = (await c.get(f"/api/pipeline/proposals?run_id={run_id}")).json()["proposals"]
    pid = next(p["id"] for p in made if p["kind"] == kind)
    assert (await c.post(f"/api/pipeline/proposals/{pid}/decide", headers=H, json={"accept": True, "reviewer": "asha"})).status_code == 200


# ------------------------------------------------------------------------------------------------ 1: locked test years
@pytest.mark.asyncio
async def test_f1_a_short_or_empty_exclusion_list_needs_the_override_and_is_recorded_truthfully(async_client: AsyncClient):
    post = lambda body: async_client.post("/api/pipeline/snapshots", headers=H, json={"cut_day": "2026-12-31", **body})
    for body in ({"exclude_years": []}, {"exclude_years": [2018, 2019]}):
        r = await post(body)
        assert r.status_code == 400 and "allow_test_years" in r.json()["detail"], body
    ok = await post({"exclude_years": [], "allow_test_years": True})
    assert ok.status_code == 201 and ok.json()["manifest"]["test_years_override"] is True and ok.json()["manifest"]["excluded_years"] == []
    part = (await post({"exclude_years": [2018, 2019], "allow_test_years": True})).json()["manifest"]
    assert part["test_years_override"] is True and part["excluded_years"] == [2018, 2019]
    default = (await post({})).json()["manifest"]
    assert default["test_years_override"] is False and default["excluded_years"] == list(range(2018, 2026))
    full = (await post({"exclude_years": list(range(2018, 2027))})).json()["manifest"]
    assert full["test_years_override"] is False


# ------------------------------------------------------------------------------------------------ 2: duplicates and proposal labels
@pytest.mark.asyncio
async def test_f2_the_same_station_day_in_two_runs_is_one_row_with_the_newest_label(async_client: AsyncClient):
    rows = wet_days("Amarpur", datetime(2026, 5, 1), 20) + BIG_DAY
    job = await ingest(async_client, csv_text(rows))
    run1 = (await async_client.post(f"/api/pipeline/jobs/{job['id']}/check", headers=H, json={})).json()["id"]
    run2 = (await async_client.post(f"/api/pipeline/jobs/{job['id']}/check", headers=H, json={})).json()["id"]
    await decide_exclude(async_client, run1)
    await decide_exclude(async_client, run2)
    async with async_session_factory() as s:                      # in the newer run the reviewer changed their mind
        rev = (await s.execute(select(Review).where(Review.run_id == run2))).scalars().one()
        s.add(Review(run_id=run2, row_ref=rev.row_ref, station_id=rev.station_id, decision="false_alarm", reviewer="asha", verdict_at_review=rev.verdict_at_review))
        await s.commit()
    snap = (await async_client.post("/api/pipeline/snapshots", headers=H, json={"cut_day": "2026-12-31"})).json()
    assert snap["n_rows"] == 1 and snap["manifest"]["skipped"]["duplicate_station_day"] == 1 and snap["manifest"]["runs"] == [run2]
    data = (await async_client.get(f"/api/pipeline/snapshots/{snap['id']}/data.jsonl")).text
    assert '"label":"clean"' in data and '"label":"fault"' not in data


@pytest.mark.asyncio
async def test_f2_only_an_exclude_proposal_confirms_a_fault(async_client: AsyncClient):
    run_id = await flagged_run(async_client)
    await decide_exclude(async_client, run_id, "review_peak")
    async with async_session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Review))).scalar_one() == 0         # "check this" is not a fault label
        assert (await s.execute(select(func.count()).select_from(Correction))).scalar_one() == 0
    await decide_exclude(async_client, run_id, "exclude_value")
    async with async_session_factory() as s:
        assert (await s.execute(select(Review))).scalars().one().decision == "confirmed_fault"


# ------------------------------------------------------------------------------------------------ 3: excluded faults train
def impossible_rows(n_days=300, seed=3):
    rng = random.Random(seed)
    rows = []
    for d in range(n_days):
        day = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
        for k in range(3):
            r = rng.random()
            if r < 0.2:      # confirmed by excluding the value: the clearest fault
                rows.append({"run_id": 1, "row_ref": f"{d}-{k}", "station_id": f"s{k}", "day": day, "label": "fault", "weight": 1.0,
                             "checks": ["impossible_value"], "excluded_by_correction": True})
            elif r < 0.3:
                rows.append({"run_id": 1, "row_ref": f"{d}-{k}", "station_id": f"s{k}", "day": day, "label": "fault", "weight": 1.0, "checks": ["repeated_value"]})
            else:
                rows.append({"run_id": 1, "row_ref": f"{d}-{k}", "station_id": f"s{k}", "day": day, "label": "clean", "weight": 1.0,
                             "checks": ["climatology_upper_tail"] if rng.random() < 0.2 else []})
    return rows


def test_f3_impossible_value_learns_a_positive_weight_and_unfired_checks_are_reported():
    res = fusion.train(impossible_rows())
    w = dict(zip(res["artifact"]["checks"], res["artifact"]["weights"]))
    assert w["impossible_value"] > 0
    art = res["artifact"]
    assert "duplicate_row" in art["never_fired_in_training"] and "impossible_value" not in art["never_fired_in_training"]
    assert art["effective_rule_weights"]["duplicate_row"] == fusion.FIXED_WEIGHTS["duplicate_row"] and art["effective_rule_weights"]["impossible_value"] is None


# ------------------------------------------------------------------------------------------------ 4: bad numbers, widths, errors
def test_f4_non_finite_numbers_are_not_numbers():
    assert cwc._num("nan") is None and cwc._num("inf") is None and cwc._num("-Infinity") is None and cwc._num("3.5") == 3.5 and cwc._num("-2") == -2.0


@pytest.mark.asyncio
async def test_f4_bad_negative_and_long_rows(async_client: AsyncClient):
    long_name, long_state = "N" * 200, "S" * 100
    base = datetime(2026, 6, 1, 14)
    rows = [("A", base, "nan"), ("A", base + timedelta(days=1), "inf"), ("A", base + timedelta(days=2), "-5"), ("A", base + timedelta(days=3), "4"),
            (long_name, base, "3")]
    text = csv_text([r for r in rows[:4]]) + line(9, long_name, base, 3, state=long_state) + "\n"
    job = await ingest(async_client, text)
    assert job["status"] == "done" and job["rows_bad"] == 2 and job["rows_inserted"] == 3
    probs = {b["row"]: b for b in job["bad_samples"]}
    assert "finite" in probs[1]["problem"] and "finite" in probs[2]["problem"] and probs[3]["stored"] is True and "negative" in probs[3]["problem"]
    async with async_session_factory() as s:
        st = (await s.execute(select(PipelineStation).where(PipelineStation.name.like("NNN%")))).scalars().one()
        assert len(st.name) == 128 and len(st.state) == 64
        assert (await s.execute(select(func.count()).select_from(Observation).where(Observation.value_mm < 0))).scalar_one() == 1
        assert (await s.execute(select(func.count()).select_from(Observation).where(Observation.value_mm.is_(None)))).scalar_one() == 0


@pytest.mark.asyncio
async def test_f4_a_storage_error_is_never_shown_and_the_stored_count_is_true(async_client: AsyncClient, monkeypatch):
    real, calls = jobs_svc.insert_observations, {"n": 0}

    async def flaky(session, rows):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("INSERT INTO pipeline_observations (secret) VALUES (:p1) [parameters: ('x',)]")
        await real(session, rows)

    monkeypatch.setattr(jobs_svc, "insert_observations", flaky)
    monkeypatch.setattr(jobs_svc, "CHUNK_ROWS", 5)
    job = await ingest(async_client, csv_text(wet_days("Amarpur", datetime(2026, 6, 1), 12)))
    assert job["status"] == "failed" and job["error"] == jobs_svc.STORAGE_ERROR and "INSERT" not in job["error"] and "secret" not in job["error"]
    assert job["rows_inserted"] == 5                                  # the first chunk stays stored, and the job says so


# ------------------------------------------------------------------------------------------------ 5: rollback walks back
@pytest.mark.asyncio
async def test_f5_repeated_rollbacks_walk_back_then_refuse(async_client: AsyncClient):
    reg = lambda v, rec: async_client.post("/api/pipeline/models", headers=H, json={"name": "stnet", "version": v, "metrics": {**GOOD, "recall_at_budget": rec}})
    ids = []
    for v, rec in (("1", 0.5), ("2", 0.6), ("3", 0.7)):
        mid = (await reg(v, rec)).json()["id"]
        assert (await async_client.post(f"/api/pipeline/models/{mid}/promote", headers=H)).json()["alias"] == "champion"
        ids.append(mid)
    roll = lambda: async_client.post("/api/pipeline/models/stnet/rollback", headers=H)
    assert (await roll()).json()["version"] == "2"
    assert (await roll()).json()["version"] == "1"                     # before the fix this flipped back to 3
    r = await roll()
    assert r.status_code == 409 and "oldest" in r.json()["detail"]
    models = {m["version"]: m["alias"] for m in (await async_client.get("/api/pipeline/models")).json()["models"]}
    assert models == {"1": "champion", "2": "archived", "3": "archived"}


@pytest.mark.asyncio
async def test_f5_two_champions_are_tolerated_and_promotion_demotes_all(async_client: AsyncClient):
    async with async_session_factory() as s:
        for v in ("1", "2"):
            s.add(ModelVersion(name="m", version=v, metrics=GOOD, alias="champion"))
        s.add(ModelVersion(name="m", version="3", metrics={**GOOD, "recall_at_budget": 0.9}, alias="challenger"))
        await s.commit()
        assert (await registry.champion(s, "m")).version == "2"        # the newest
        new = (await s.execute(select(ModelVersion).where(ModelVersion.version == "3"))).scalars().one()
        await registry.promote(s, new.id)
        aliases = {m.version: m.alias for m in (await s.execute(select(ModelVersion).where(ModelVersion.name == "m"))).scalars()}
        assert aliases == {"1": "archived", "2": "archived", "3": "champion"}


# ------------------------------------------------------------------------------------------------ 6: gate
def label_metrics(**over):
    m = fusion.train(impossible_rows())
    m = {**m, "snapshot_sha256": "s1"}
    m.update(over)
    return m


def test_f6_label_minimums_come_from_one_place_and_are_raised():
    assert fusion.MIN_VAL_FAULT >= 5 and fusion.MIN_VAL_CLEAN >= 20
    m = label_metrics()
    assert registry.evaluate_gate(m, None)["passed"]
    thin = {**m, "validation": {**m["validation"], "n_fault": 1, "n_clean": 1}}
    g = registry.evaluate_gate(thin, None)
    assert not g["passed"] and not next(c for c in g["checks"] if c["rule"] == "enough_labels")["passed"]
    rows, seen = impossible_rows(), 0
    for r in rows:                                                      # the later part keeps only 2 faults: too few to judge on
        if r["day"] > "2026-08-14" and r["label"] == "fault":
            seen += 1
            if seen > 2:
                r["label"] = "clean"
    with pytest.raises(fusion.NotEnoughLabels):                         # the trainer refuses a thin validation set
        fusion.train(rows)


def test_f6_two_models_without_a_snapshot_hash_are_not_the_same_snapshot():
    m = label_metrics(snapshot_sha256=None)
    g = registry.evaluate_gate(m, {**m, "snapshot_sha256": None})
    assert g["champion_compared"] is False and any(c["rule"] == "champion_not_comparable" for c in g["checks"])


def test_f6_non_numeric_metrics_fail_the_gate_with_a_reason():
    g = registry.evaluate_gate({**GOOD, "recall_at_budget": "high", "false_alarms_per_1000": "x"}, GOOD)
    assert g["passed"] is False and g["checks"]
    m = label_metrics()
    assert registry.evaluate_gate({**m, "baseline": "none"}, None)["passed"] is False
    assert registry.evaluate_gate({**m, "false_alarm_budget_per_1000": "five"}, None)["passed"] is False


@pytest.mark.asyncio
async def test_f6_promoting_a_model_with_text_metrics_is_a_rejection_not_a_500(async_client: AsyncClient):
    r = await async_client.post("/api/pipeline/models", headers=H, json={"name": "k", "version": "1", "metrics": {**GOOD, "false_alarms_per_1000": "abc"}})
    out = await async_client.post(f"/api/pipeline/models/{r.json()['id']}/promote", headers=H)
    assert out.status_code == 200 and out.json()["alias"] == "rejected" and out.json()["gate"]["passed"] is False


@pytest.mark.asyncio
async def test_f6_the_snapshot_hash_is_not_stored_as_an_artifact_hash(async_client: AsyncClient):
    async with async_session_factory() as s:
        snap = TrainingSnapshot(cut_day="2026-12-31", n_rows=0, sha256="a" * 64, manifest={}, content="\n".join(__import__("json").dumps(r) for r in impossible_rows()))
        s.add(snap)
        await s.commit()
        sid = snap.id
    job = (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "local"})).json()
    assert job["status"] == "complete"
    m = (await async_client.get("/api/pipeline/models")).json()["models"][0]
    assert m["artifact_sha256"] is None and m["metrics"]["snapshot_sha256"] == "a" * 64


# ------------------------------------------------------------------------------------------------ 7: not-run reporting
@pytest.mark.asyncio
async def test_f7_the_run_says_the_neighbour_checks_cannot_be_trusted(async_client: AsyncClient):
    run_id = await flagged_run(async_client)
    full = (await async_client.get(f"/api/validation/runs/{run_id}")).json()
    nb = [n for n in full["not_run"] if n["check"] == "neighbour" and "not known to be dry" in n["reason"]]
    assert nb and "non-zero hours" in nb[0]["reason"]
    assert "not known to be dry" in full["settings"]["pipeline"]["neighbour_checks"]
    assert "NOT stated" in cwc.ASSUMPTIONS["time_stamp"]


# ------------------------------------------------------------------------------------------------ 8: auth
@pytest.mark.asyncio
async def test_f8_wrong_tokens_in_the_login_middleware_are_limited(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    async with AsyncClient(transport=ASGITransport(app=app, client=("10.0.0.1", 1)), base_url="http://test") as c:
        for _ in range(auth_api.TOKEN_MAX_FAILURES):
            assert (await c.get("/api/validation/runs", headers={"X-Admin-Token": "guess"})).status_code == 401
        assert (await c.get("/api/validation/runs", headers={"X-Admin-Token": "guess"})).status_code == 429
        assert (await c.get("/api/validation/runs", headers={"X-Admin-Token": TOKEN})).status_code == 429       # even the right one waits: no oracle
    async with AsyncClient(transport=ASGITransport(app=app, client=("10.0.0.2", 1)), base_url="http://test") as other:
        assert (await other.get("/api/validation/runs", headers={"X-Admin-Token": TOKEN})).status_code == 200       # another client is unaffected


@pytest.mark.asyncio
async def test_f8_one_client_cannot_lock_everyone_out_of_login(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "admin@admin.com")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "admin")
    body = {"email": "admin@admin.com", "password": "bad"}
    async with AsyncClient(transport=ASGITransport(app=app, client=("10.0.0.3", 1)), base_url="http://test") as attacker:
        for _ in range(auth_api.MAX_FAILURES):
            assert (await attacker.post("/api/auth/login", json=body)).status_code == 401
        assert (await attacker.post("/api/auth/login", json=body)).status_code == 429
    async with AsyncClient(transport=ASGITransport(app=app, client=("10.0.0.4", 1)), base_url="http://test") as admin:
        assert (await admin.post("/api/auth/login", json={**body, "password": "admin"})).status_code == 200
        spoof = await admin.post("/api/auth/login", json=body, headers={"X-Forwarded-For": "10.0.0.3"})          # the header is not trusted
        assert spoof.status_code == 401


@pytest.mark.asyncio
async def test_f8_docs_and_openapi_need_a_session_and_root_shows_status_only(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    for url in ("/docs", "/openapi.json", "/redoc"):
        assert (await async_client.get(url)).status_code == 401, url
        assert (await async_client.get(url, headers={"X-Admin-Token": TOKEN})).status_code == 200, url
    assert (await async_client.get("/")).json() == {"status": "online"}
    assert "project" in (await async_client.get("/", headers={"X-Admin-Token": TOKEN})).json()


# ------------------------------------------------------------------------------------------------ 9: training
async def add_snapshot(content: str) -> int:
    async with async_session_factory() as s:
        snap = TrainingSnapshot(cut_day="2026-12-31", n_rows=1, sha256="b" * 64, manifest={}, content=content)
        s.add(snap)
        await s.commit()
        return snap.id


@pytest.mark.asyncio
async def test_f9_a_broken_snapshot_fails_the_job_instead_of_leaving_it_running(async_client: AsyncClient):
    sid = await add_snapshot("this is not json\n")
    r = await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "local"})
    assert r.status_code == 202 and r.json()["status"] == "failed" and r.json()["error"] == training.SAFE_FAILURE
    sid2 = await add_snapshot('{"label": "fault"}\n')                    # a row without a day: KeyError
    r2 = await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid2, "target": "local"})
    assert r2.json()["status"] == "failed" and "KeyError" not in r2.json()["error"]


@pytest.mark.asyncio
async def test_f9_an_unexpected_push_error_fails_the_job(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "KAGGLE_USERNAME", "owner")
    monkeypatch.setattr(settings, "KAGGLE_KEY", "K")
    monkeypatch.setattr(kaggle_trigger, "push", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full at /secret/path")))
    sid = await add_snapshot("{}\n")
    r = await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "kaggle"})
    assert r.status_code == 202 and r.json()["status"] == "failed" and "/secret/path" not in r.json()["error"]


@pytest.mark.asyncio
async def test_f9_two_simultaneous_refreshes_register_one_challenger(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "KAGGLE_USERNAME", "owner")
    monkeypatch.setattr(settings, "KAGGLE_KEY", "K")
    sid = await add_snapshot("{}\n")
    async with async_session_factory() as s:
        job = TrainingJob(snapshot_id=sid, target="kaggle", name="label-fusion", status="running", slug="owner/datamend-fusion-s1-j1")
        s.add(job)
        await s.commit()
        jid = job.id
    monkeypatch.setattr(kaggle_trigger, "status", lambda slug, acct: "complete")

    def slow_fetch(slug, acct):
        time.sleep(0.2)
        return {"ok": True, "metrics": {"kind": "label_fusion", "snapshot_sha256": "b" * 64}}

    monkeypatch.setattr(kaggle_trigger, "fetch_result", slow_fetch)
    a, b = await asyncio.gather(async_client.post(f"/api/pipeline/train/jobs/{jid}/refresh", headers=H),
                                async_client.post(f"/api/pipeline/train/jobs/{jid}/refresh", headers=H))
    assert a.status_code == 200 and b.status_code == 200
    async with async_session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(ModelVersion))).scalar_one() == 1


# ------------------------------------------------------------------------------------------------ 10: uploads
@pytest.mark.asyncio
async def test_f10_the_saved_upload_is_removed_when_creating_the_job_fails(async_client: AsyncClient, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs_svc, "UPLOAD_DIR", tmp_path)

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(jobs_svc, "create_job", boom)
    with pytest.raises(RuntimeError):
        await async_client.post("/api/pipeline/ingest", headers=H, data={"source": "cwc"}, files={"file": ("a.csv", b"x,y\n1,2\n", "text/csv")})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_f10_a_large_content_length_is_refused_before_reading(async_client: AsyncClient, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs_svc, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(jobs_svc, "MAX_BYTES", 100)
    r = await async_client.post("/api/pipeline/ingest", headers={**H, "Content-Length": "5000"}, data={"source": "cwc"},
                                files={"file": ("a.csv", b"x" * 10, "text/csv")})
    assert r.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_f10_orphan_uploads_older_than_a_day_are_deleted(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs_svc, "UPLOAD_DIR", tmp_path)
    old, new = tmp_path / "old.csv", tmp_path / "new.csv"
    old.write_text("x")
    new.write_text("x")
    import os
    past = time.time() - 3 * 86400
    os.utime(old, (past, past))
    assert jobs_svc.remove_orphan_uploads() == 1 and not old.exists() and new.exists()


# ------------------------------------------------------------------------------------------------ 11: resource use
@pytest.mark.asyncio
async def test_f11_status_caches_the_observation_count(async_client: AsyncClient):
    await ingest(async_client, csv_text(wet_days("Amarpur", datetime(2026, 6, 1), 4)))
    first = (await async_client.get("/api/pipeline/status")).json()
    assert first["observations"] == 4 and "cached" in first["observations_note"]
    async with async_session_factory() as s:
        await s.execute(delete(Observation))
        await s.commit()
    assert (await async_client.get("/api/pipeline/status")).json()["observations"] == 4          # still the cached value inside the 30 seconds


@pytest.mark.asyncio
async def test_f11_the_period_filter_is_applied_in_the_query(async_client: AsyncClient):
    from backend.app.pipeline import qc
    job = await ingest(async_client, csv_text(wet_days("Amarpur", datetime(2026, 6, 1), 10)))
    async with async_session_factory() as s:
        out = await qc.daily_totals(s, "cwc", datetime(2026, 6, 3).date(), datetime(2026, 6, 5).date())
    assert [r.day.isoformat() for r in out] == ["2026-06-03", "2026-06-04", "2026-06-05"] and job["status"] == "done"
