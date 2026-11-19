"""Retraining from labels: the label-fusion trainer, the server-CPU path, the Kaggle trigger (the command line is mocked) and the lineage graph.
Generated labels only; nothing contacts Kaggle."""
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.pipeline import fusion, kaggle_trigger
from backend.app.pipeline.models import (AuditItem, Correction, IngestJob, ModelVersion, Observation, PipelineStation, Proposal, TrainingJob,
                                          TrainingSnapshot)
from backend.app.validation.models import Review, ValidationRun

TOKEN = "q" * 32
H = {"X-Admin-Token": TOKEN}
REAL_RUN = subprocess.run


def labelled_rows(n_days=300, seed=1):
    """Faults always carry neighbour_isolated_wet (fixed weight 0.30); clean days sometimes carry climatology_upper_tail (also 0.30), so the
    fixed rule weights cannot tell them apart but learned weights can."""
    rng = random.Random(seed)
    rows = []
    for d in range(n_days):
        day = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
        for k in range(3):
            fault = rng.random() < 0.25
            checks = ["neighbour_isolated_wet"] if fault else (["climatology_upper_tail"] if rng.random() < 0.3 else [])
            rows.append({"run_id": 1, "row_ref": f"{d}-{k}", "station_id": f"s{k}", "day": day, "label": "fault" if fault else "clean",
                         "weight": 1.0, "checks": checks, "mm_original": 5.0, "mm_effective": 5.0})
    return rows


def snapshot_content(rows):
    return "\n".join(json.dumps(r, sort_keys=True) for r in rows)


@pytest_asyncio.fixture(autouse=True)
async def _clean(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "KAGGLE_USERNAME", "")
    monkeypatch.setattr(settings, "KAGGLE_KEY", "")
    async with async_session_factory() as s:
        for model in (Correction, Proposal, AuditItem, TrainingJob, ModelVersion, TrainingSnapshot, Review, Observation, PipelineStation, IngestJob):
            await s.execute(delete(model))
        await s.execute(delete(ValidationRun).where(ValidationRun.source == "pipeline"))
        await s.commit()
    yield


async def add_snapshot(rows) -> int:
    content = snapshot_content(rows)
    async with async_session_factory() as s:
        snap = TrainingSnapshot(cut_day="2026-12-31", n_rows=len(rows), sha256="a" * 64, manifest={"label_counts": {}, "runs": []}, content=content)
        s.add(snap)
        await s.commit()
        return snap.id


# ---------------------------------------------------------------------------------------------- the trainer
def test_trainer_learns_weights_judges_on_later_days_and_beats_fixed_rules():
    res = fusion.train(labelled_rows())
    assert res["kind"] == "label_fusion" and res["temporal_split"] is True and res["labels_not_ground_truth"] is True
    w = dict(zip(res["artifact"]["checks"], res["artifact"]["weights"]))
    assert all(v >= 0 for v in res["artifact"]["weights"]) and w["neighbour_isolated_wet"] > w["climatology_upper_tail"]
    assert res["recall_at_budget"] > res["baseline"]["recall_at_budget"]          # the fixed weights tie the two checks, so within the budget they flag nothing
    assert res["false_alarms_per_1000"] <= res["false_alarm_budget_per_1000"]
    rows = labelled_rows()
    assert res["validation"]["train_until"] < max(r["day"] for r in rows)                          # a later part is held out
    assert res["train"]["n_fault"] >= 20 and res["validation"]["n_fault"] >= 1


def test_trainer_refuses_too_few_labels_and_too_few_days():
    with pytest.raises(fusion.NotEnoughLabels):
        fusion.train(labelled_rows(n_days=8))
    with pytest.raises(fusion.NotEnoughLabels):
        fusion.train([{**r, "day": "2026-01-01"} for r in labelled_rows(n_days=10)])


def test_excluded_corrections_and_unreviewed_rows_never_train():
    rows = labelled_rows()
    rows += [{**rows[0], "row_ref": "x", "label": "unlabelled", "checks": ["impossible_value"]}] * 50
    rows += [{**rows[1], "row_ref": "y", "label": "fault", "excluded_by_correction": True}] * 50
    a, b = fusion.train(labelled_rows()), fusion.train(rows)
    assert a["train"] == b["train"]


# ---------------------------------------------------------------------------------------------- server CPU path and the gate
@pytest.mark.asyncio
async def test_train_locally_registers_a_challenger_and_the_gate_decides(async_client: AsyncClient):
    sid = await add_snapshot(labelled_rows())
    job = (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "local"})).json()
    assert job["status"] == "complete" and job["model_id"]
    models = (await async_client.get("/api/pipeline/models")).json()["models"]
    m = models[0]
    assert m["alias"] == "challenger" and m["metrics"]["kind"] == "label_fusion" and m["snapshot_id"] == sid
    promoted = (await async_client.post(f"/api/pipeline/models/{m['id']}/promote", headers=H)).json()
    assert promoted["gate"]["profile"] == "label_fusion" and promoted["gate"]["passed"] and promoted["alias"] == "champion"
    assert any(c["rule"] == "recall_not_below_rules" and c["passed"] for c in promoted["gate"]["checks"])
    second = (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "local"})).json()
    again = next(x for x in (await async_client.get("/api/pipeline/models")).json()["models"] if x["id"] == second["model_id"])
    promoted2 = (await async_client.post(f"/api/pipeline/models/{again['id']}/promote", headers=H)).json()
    assert promoted2["alias"] == "champion"                                             # same snapshot: compared with the champion and not lower


@pytest.mark.asyncio
async def test_too_few_labels_fail_the_job_and_register_nothing(async_client: AsyncClient):
    sid = await add_snapshot(labelled_rows(n_days=5))
    job = (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "local"})).json()
    assert job["status"] == "failed" and "too few labels" in job["error"] and job["model_id"] is None
    assert (await async_client.get("/api/pipeline/models")).json()["models"] == []
    assert (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": 999, "target": "local"})).status_code == 404
    assert (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "gpu"})).status_code == 400
    assert (await async_client.post("/api/pipeline/train", json={"snapshot_id": sid})).status_code == 401


def test_gate_does_not_compare_models_from_different_snapshots():
    m = fusion.train(labelled_rows())
    from backend.app.pipeline.registry import evaluate_gate
    other = {**m, "snapshot_sha256": "other"}
    g = evaluate_gate({**m, "snapshot_sha256": "mine"}, other)
    assert g["passed"] and any(c["rule"] == "champion_not_comparable" for c in g["checks"]) and g["champion_compared"] is False
    assert not evaluate_gate({**m, "false_alarms_per_1000": 50.0}, None)["passed"]
    assert not evaluate_gate({**m, "recall_at_budget": -1.0}, None)["passed"]


# ---------------------------------------------------------------------------------------------- Kaggle trigger (command line mocked)
@pytest.mark.asyncio
async def test_kaggle_is_refused_until_configured(async_client: AsyncClient):
    sid = await add_snapshot(labelled_rows())
    r = await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "kaggle"})
    assert r.status_code == 409 and "KAGGLE_USERNAME" in r.text
    assert (await async_client.get("/api/pipeline/train/jobs")).json()["kaggle_configured"] is False


@pytest.mark.asyncio
async def test_kaggle_push_status_and_result_register_a_challenger(async_client: AsyncClient, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "KAGGLE_USERNAME", "owner")
    monkeypatch.setattr(settings, "KAGGLE_KEY", "SECRET-KEY-VALUE")
    sid = await add_snapshot(labelled_rows())
    calls, state = [], {"status": "running"}

    def fake_run(cmd, **kw):
        calls.append(cmd[1:])
        assert kw["env"]["KAGGLE_KEY"] == "SECRET-KEY-VALUE"
        if cmd[1:3] == ["kernels", "push"]:
            folder = Path(cmd[cmd.index("-p") + 1])
            meta = json.loads((folder / "kernel-metadata.json").read_text())
            assert meta["id"].startswith("owner/datamend-fusion-s") and meta["enable_gpu"] == "false" and meta["enable_internet"] == "false"
            script = (folder / "train.py").read_text()
            assert "SECRET-KEY-VALUE" not in script and '__name__ == "__main__"' not in script and "_SNAPSHOT" in script
            run = REAL_RUN([sys.executable, "train.py"], cwd=folder, capture_output=True, text=True, timeout=120)         # the notebook really runs
            assert run.returncode == 0, run.stderr
            state["result"] = json.loads((folder / "result.json").read_text())
            return subprocess.CompletedProcess(cmd, 0, "Kernel version 1 successfully pushed", "")
        if cmd[1:3] == ["kernels", "status"]:
            return subprocess.CompletedProcess(cmd, 0, f'owner/x has status "{state["status"]}"', "")
        if cmd[1:3] == ["kernels", "output"]:
            (Path(cmd[cmd.index("-p") + 1]) / "result.json").write_text(json.dumps(state["result"]))
            return subprocess.CompletedProcess(cmd, 0, "Output file downloaded", "")
        raise AssertionError(cmd)

    monkeypatch.setattr(kaggle_trigger.subprocess, "run", fake_run)
    job = (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "kaggle"})).json()
    assert job["status"] == "running" and job["slug"].startswith("owner/datamend-fusion-s")
    still = (await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers=H)).json()
    assert still["status"] == "running" and state["result"]["ok"] is True
    state["status"] = "complete"
    done = (await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers=H)).json()
    assert done["status"] == "complete" and done["model_id"]
    m = (await async_client.get("/api/pipeline/models")).json()["models"][0]
    assert m["alias"] == "challenger" and m["metrics"]["kind"] == "label_fusion" and m["metrics"]["snapshot_sha256"] == "a" * 64
    assert (await async_client.post(f"/api/pipeline/train/jobs/{job['id']}/refresh", headers=H)).json()["status"] == "complete"      # nothing re-registered
    assert len((await async_client.get("/api/pipeline/models")).json()["models"]) == 1


@pytest.mark.asyncio
async def test_kaggle_failures_are_reported_without_the_key(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "KAGGLE_USERNAME", "owner")
    monkeypatch.setattr(settings, "KAGGLE_KEY", "SECRET-KEY-VALUE")
    sid = await add_snapshot(labelled_rows())

    def boom(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "401 Unauthorized for key SECRET-KEY-VALUE")

    monkeypatch.setattr(kaggle_trigger.subprocess, "run", boom)
    job = (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "kaggle"})).json()
    assert job["status"] == "failed" and "Unauthorized" in job["error"] and "SECRET-KEY-VALUE" not in job["error"]
    monkeypatch.setattr(kaggle_trigger.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    job2 = (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": sid, "target": "kaggle"})).json()
    assert job2["status"] == "failed" and "not installed" in job2["error"]


# ---------------------------------------------------------------------------------------------- lineage
@pytest.mark.asyncio
async def test_lineage_links_job_run_snapshot_training_and_model(async_client: AsyncClient):
    from datetime import datetime, timedelta
    rows = []
    for d in range(20):
        rows.append(("Amarpur", datetime(2026, 5, 1, 14) + timedelta(days=d), round(4 + (d % 5) * 0.7 + d * 0.01, 2)))
    rows += [("Amarpur", datetime(2026, 6, 10, h), 75.0) for h in range(9, 23)] + [("Amarpur", datetime(2026, 6, 10, 23), 423.0)]
    header = ("SlNo,Station,Agency,State LGD Code,State,District LGD Code,District,Tehsil,Block,Village,River,Basin,Tributary,Subtributary,"
              "SubSubtributary,Local River,Latitude,Longitude,Data Acquisition Time,Telemetry Hourly Rainfall (mm)")
    text = header + "\n" + "\n".join(f"{i},{s},CWC,16,Tripura,1,G,T,-,-,R,B,T,S,-,L,23.5,91.6,{t.strftime('%d-%m-%Y %H:%M')},{v}" for i, (s, t, v) in enumerate(rows, 1)) + "\n"
    job = (await async_client.post("/api/pipeline/ingest", headers=H, data={"source": "cwc", "wait": "true"}, files={"file": ("t.csv", text.encode(), "text/csv")})).json()
    run = (await async_client.post(f"/api/pipeline/jobs/{job['id']}/check", headers=H, json={})).json()
    await async_client.post(f"/api/pipeline/runs/{run['id']}/proposals", headers=H, json={})
    pid = (await async_client.get(f"/api/pipeline/proposals?run_id={run['id']}")).json()["proposals"][0]["id"]
    await async_client.post(f"/api/pipeline/proposals/{pid}/decide", headers=H, json={"accept": True})
    snap = (await async_client.post("/api/pipeline/snapshots", headers=H, json={"cut_day": "2026-12-31"})).json()
    assert snap["manifest"]["runs"] == [run["id"]]
    tj = (await async_client.post("/api/pipeline/train", headers=H, json={"snapshot_id": snap["id"], "target": "local"})).json()
    assert tj["status"] == "failed"                                                        # one label is far too few; the graph still shows the attempt
    reg = (await async_client.post("/api/pipeline/models", headers=H, json={"name": "stnet", "version": "1", "metrics": {}, "snapshot_id": snap["id"]})).json()
    g = (await async_client.get("/api/pipeline/lineage")).json()
    ids = {n["id"] for n in g["nodes"]}
    assert {f"job:{job['id']}", f"run:{run['id']}", f"snapshot:{snap['id']}", f"train:{tj['id']}", f"model:{reg['id']}"} <= ids
    pairs = {(e["from"], e["to"]) for e in g["edges"]}
    assert (f"job:{job['id']}", f"run:{run['id']}") in pairs and (f"run:{run['id']}", f"snapshot:{snap['id']}") in pairs
    assert (f"snapshot:{snap['id']}", f"train:{tj['id']}") in pairs and (f"snapshot:{snap['id']}", f"model:{reg['id']}") in pairs     # a model registered by hand
    run_node = next(n for n in g["nodes"] if n["id"] == f"run:{run['id']}")
    assert run_node["facts"]["flagged"] >= 1 and run_node["facts"]["corrections"] == 1 and run_node["facts"]["reviews"] == 1
    assert all(e["from"] in ids and e["to"] in ids for e in g["edges"])
