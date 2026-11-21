"""Integration: upload -> checks -> storage -> API (spec slice 5). Generated data only; a throwaway SQLite file (see conftest)."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from backend.app.db.database import async_session_factory
from backend.app.validation import runs as svc
from backend.app.validation.models import Explanation, Review, ValidationCheckHit, ValidationResult, ValidationRun
from backend.app.validation.records import Reading

T0 = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture(autouse=True)
async def _clean_runs():
    async with async_session_factory() as s:
        for m in (Review, Explanation, ValidationCheckHit, ValidationResult, ValidationRun):
            await s.execute(delete(m))
        await s.commit()
    yield


def reading_csv(n=40, station="A", faults=True) -> bytes:
    """One station, 15-minute readings, cumulative counter; with faults: a jump at row 20 and a negative at row 30 (the counter then
    returns to 120, which is itself a second jump): 3 SUSPECT rows."""
    lines = ["timestamp,station_id,accumulation,intensity"]
    acc = 0.0
    for i in range(n):
        t = (T0 + timedelta(minutes=15 * i)).isoformat().replace("+00:00", "Z")
        val = acc
        if faults and i == 20:
            acc += 120.0
            val = acc
        elif faults and i == 30:
            val = -3.0
        lines.append(f"{t},{station},{val},0.0")
    return ("\n".join(lines) + "\n").encode()


async def post(client: AsyncClient, content: bytes, name="r.csv", **form):
    data = {"profile": "reading", "accumulation_mode": "cumulative", "interval_minutes": "15", **form}
    return await client.post("/api/validation/runs", files={"file": (name, content, "text/csv")}, data=data)


@pytest.mark.asyncio
async def test_upload_creates_a_run_with_report_and_flagged_rows(async_client: AsyncClient):
    res = await post(async_client, reading_csv(), synthetic="true")
    assert res.status_code == 201, res.text
    run = res.json()
    assert run["status"] == "completed" and run["n_rows"] == 40 and run["synthetic"] is True and run["storage"] == "SQLite file"
    assert run["settings"]["thresholds_basis"] == "design choices, uncalibrated" and run["input_sha256"] and run["platform_version"]
    h = run["headline"]
    assert h["rows"] == 40 and h["share_suspect"] == pytest.approx(3 / 40) and "grade" not in h
    assert h["completeness"]["value"] == 1.0
    assert {"check": "neighbour", "station_id": "A", "reason": "no coordinates for this station"} in run["not_run"]

    page = (await async_client.get(f"/api/validation/runs/{run['id']}/rows")).json()
    assert page["total"] == 3 and page["page_size"] == 50
    scores = [r["rule_score"] for r in page["rows"]]
    assert scores == sorted(scores, reverse=True) and page["rows"][0]["verdict"] == "SUSPECT"
    assert {c for r in page["rows"] for c in r["checks"]} >= {"negative_value", "counter_jump"}

    row_id = page["rows"][0]["id"]
    ev = (await async_client.get(f"/api/validation/runs/{run['id']}/rows/{row_id}")).json()
    assert ev["original_row"]["station_id"] == "A" and ev["score_kind"].startswith("rule score")
    assert ev["hits"][0]["evidence"]["observed"]["basis"] in ("measured", "assumed")


@pytest.mark.asyncio
async def test_rows_are_paged_filtered_and_capped_at_50(async_client: AsyncClient):
    lines = ["day,station_id,mm"] + [f"2026-07-{d:02d},A,-1" for d in range(1, 29)] + [f"2026-08-{d:02d},A,-1" for d in range(1, 29)]
    run = (await async_client.post("/api/validation/runs", files={"file": ("d.csv", ("\n".join(lines) + "\n").encode(), "text/csv")}, data={"profile": "daily"})).json()
    p1 = (await async_client.get(f"/api/validation/runs/{run['id']}/rows")).json()
    assert p1["total"] == 56 and len(p1["rows"]) == 50 and p1["pages"] == 2
    p2 = (await async_client.get(f"/api/validation/runs/{run['id']}/rows?page=2")).json()
    assert len(p2["rows"]) == 6
    assert (await async_client.get(f"/api/validation/runs/{run['id']}/rows?page_size=500")).status_code == 422
    assert (await async_client.get(f"/api/validation/runs/{run['id']}/rows?verdict=BOGUS")).status_code == 422
    only = (await async_client.get(f"/api/validation/runs/{run['id']}/rows?check=impossible_value&station=B")).json()
    assert only["total"] == 0


@pytest.mark.asyncio
async def test_series_is_downsampled_on_the_server_but_keeps_flagged_markers(async_client: AsyncClient):
    run = (await post(async_client, reading_csv(n=600))).json()
    s = (await async_client.get(f"/api/validation/runs/{run['id']}/series?station=A&max_points=100")).json()
    assert s["n_total"] == 600 and s["downsampled"] is True and len(s["points"]) <= 100
    assert {f["verdict"] for f in s["flagged"]} == {"SUSPECT"} and len(s["flagged"]) == 3
    assert {c for f in s["flagged"] for c in f["checks"]} >= {"counter_jump", "negative_value"}      # lanes need the fired checks
    full = (await async_client.get(f"/api/validation/runs/{run['id']}/series?station=A&max_points=1000")).json()
    assert full["downsampled"] is False and len(full["points"]) == 600


@pytest.mark.asyncio
async def test_exports_keep_original_columns_and_the_json_is_complete(async_client: AsyncClient):
    content = reading_csv()
    run = (await post(async_client, content)).json()
    csv_text = (await async_client.get(f"/api/validation/runs/{run['id']}/export.csv")).text
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    orig = list(csv.DictReader(io.StringIO(content.decode())))
    assert len(rows) == len(orig) == 40
    assert all(r[k] == o[k] for r, o in zip(rows, orig) for k in o)                   # original columns untouched
    assert {"verdict", "rule_score", "severity", "fired_checks"} <= set(rows[0]) and rows[30]["verdict"] == "SUSPECT"
    assert "negative_value" in rows[30]["fired_checks"]
    js = (await async_client.get(f"/api/validation/runs/{run['id']}/export.json")).json()
    assert len(js["rows"]) == 40 and js["run"]["git_commit"] and any(r["hits"] for r in js["rows"])
    assert js["rows"][30]["original_row"]["accumulation"] == "-3.0"


@pytest.mark.asyncio
async def test_rejected_file_returns_422_and_is_recorded_as_a_failed_run(async_client: AsyncClient):
    res = await async_client.post("/api/validation/runs", files={"file": ("e.csv", b"timestamp,station_id\n", "text/csv")}, data={"profile": "reading"})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["rejected"] is True and "data rows" in detail["reason"]
    runs = (await async_client.get("/api/validation/runs")).json()["runs"]
    assert runs[0]["status"] == "failed" and runs[0]["id"] == detail["run_id"] and runs[0]["error"]
    bad = await async_client.post("/api/validation/runs", files={"file": ("x.parquet", b"x", "application/octet-stream")}, data={"profile": "reading"})
    assert bad.status_code == 422 and "NOT IMPLEMENTED" in bad.text


@pytest.mark.asyncio
async def test_missing_run_and_row_are_404(async_client: AsyncClient):
    assert (await async_client.get("/api/validation/runs/999999")).status_code == 404
    run = (await post(async_client, reading_csv(n=5, faults=False))).json()
    assert (await async_client.get(f"/api/validation/runs/{run['id']}/rows/999999")).status_code == 404


@pytest.mark.asyncio
async def test_run_cap_prunes_the_oldest_runs():
    async with async_session_factory() as s:
        ids = []
        for i in range(53):
            r = ValidationRun(profile="daily", source="upload", label=f"r{i}", platform_version="t", git_commit="t", status="completed")
            s.add(r)
            await s.flush()
            ids.append(r.id)
        await s.commit()
        deleted = await svc.prune_runs(s)
        await s.commit()
        remaining = (await s.execute(select(func.count()).select_from(ValidationRun))).scalar_one()
        oldest = (await s.execute(select(func.min(ValidationRun.id)))).scalar_one()
    assert deleted == 3 and remaining == 50 and oldest == ids[3]


@pytest.mark.asyncio
async def test_rejected_uploads_are_pruned_before_completed_runs():
    """Review finding: 50 bad uploads must not evict completed runs."""
    async with async_session_factory() as s:
        done = []
        for i in range(10):
            r = ValidationRun(profile="daily", source="upload", label=f"ok{i}", platform_version="t", git_commit="t", status="completed")
            s.add(r)
            await s.flush()
            done.append(r.id)
        for i in range(45):
            s.add(ValidationRun(profile="daily", source="upload", label=f"bad{i}", platform_version="t", git_commit="t", status="failed", error="x"))
        await s.commit()
        assert await svc.prune_runs(s) == 5
        await s.commit()
        kept_ok = (await s.execute(select(func.count()).select_from(ValidationRun).where(ValidationRun.status == "completed"))).scalar_one()
    assert kept_ok == 10


@pytest.mark.asyncio
async def test_csv_export_defuses_formulas_but_keeps_numbers_and_json_cells(async_client: AsyncClient):
    """Review finding: a text cell starting with = + - @ is a formula in a spreadsheet; numbers such as -3.0 must stay numbers."""
    body = {"rows": [{"day": "2026-07-01", "station_id": '=HYPERLINK("http://x","y")', "mm": -3.0, "note": {"a": 1}}, {"day": "2026-07-02", "station_id": "+cmd", "mm": 1.0, "note": "-5"}]}
    r = await async_client.post("/api/validation/runs", files={"file": ("d.json", json.dumps(body).encode(), "application/json")}, data={"profile": "daily"})
    assert r.status_code == 201, r.text
    text = (await async_client.get(f"/api/validation/runs/{r.json()['id']}/export.csv")).text
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["station_id"].startswith("'=HYPERLINK") and rows[1]["station_id"] == "'+cmd"
    assert rows[0]["mm"] == "-3.0" and rows[1]["note"] == "-5"
    assert json.loads(rows[0]["note"]) == {"a": 1}


@pytest.mark.asyncio
async def test_open_live_run_is_never_pruned():
    async with async_session_factory() as s:
        live = ValidationRun(profile="reading", source="live", label="live", platform_version="t", git_commit="t", status="open", rain_day="2026-07-02")
        s.add(live)
        for i in range(52):
            s.add(ValidationRun(profile="daily", source="upload", label=f"r{i}", platform_version="t", git_commit="t", status="completed"))
        await s.commit()
        await svc.prune_runs(s)
        await s.commit()
        assert (await s.execute(select(func.count()).select_from(ValidationRun).where(ValidationRun.status == "open"))).scalar_one() == 1
        assert (await s.execute(select(func.count()).select_from(ValidationRun))).scalar_one() == 50


@pytest.mark.asyncio
async def test_live_run_is_one_per_rain_day_and_rescored_on_refresh():
    from datetime import date

    def rds(n, bad_last=False):
        out = []
        for i in range(n):
            acc = -1.0 if (bad_last and i == n - 1) else 0.0
            out.append(Reading("weather_union", "S1", T0 + timedelta(minutes=15 * i), acc, 0.0, "received", "cumulative", False, f"S1@{i}"))
        return out

    async with async_session_factory() as s:
        r1 = await svc.refresh_live_run(s, rds(4), date(2026, 7, 2), 15, "cumulative")
        r2 = await svc.refresh_live_run(s, rds(5, bad_last=True), date(2026, 7, 2), 15, "cumulative")
        assert r1.id == r2.id and r2.status == "open" and r2.n_rows == 5 and r2.settings["accumulation_mode_note"].endswith("UNCONFIRMED")
        n_rows = (await s.execute(select(func.count()).select_from(ValidationResult).where(ValidationResult.run_id == r2.id))).scalar_one()
        assert n_rows == 5 and r2.report["verdicts"].get("SUSPECT") == 1
        r3 = await svc.refresh_live_run(s, rds(2), date(2026, 7, 3), 15, "cumulative")      # next rain day: the old run closes
        await s.refresh(r2)
        assert r3.id != r2.id and r2.status == "completed" and r3.status == "open"
