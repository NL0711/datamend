"""Station network: the map layers, and the per-station check -> flag -> audit summary.
Generated data only; a throwaway database; no network."""
import csv
import io
import math

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.rainfall.catalog import load_catalog
from backend.app.validation import stations as stations_svc
from backend.app.validation.models import Explanation, Review, ValidationCheckHit, ValidationResult, ValidationRun

TOKEN = "t" * 32
H = {"X-Admin-Token": TOKEN}


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


def daily_csv(station: str, values, extra_cols: str = "", extra_vals: str = "") -> bytes:
    lines = [f"day,station_id,mm{extra_cols}"]
    for i, v in enumerate(values):
        lines.append(f"2026-07-{i + 1:02d},{station},{v}{extra_vals}")
    return ("\n".join(lines) + "\n").encode()


async def upload(client: AsyncClient, content: bytes, **form):
    res = await client.post("/api/validation/runs", files={"file": ("d.csv", content, "text/csv")}, data={"profile": "daily", **form})
    assert res.status_code == 201, res.text
    return res.json()


async def cycle(client: AsyncClient):
    res = await client.get("/api/validation/stations")
    assert res.status_code == 200
    return {s["station_id"]: s for s in res.json()["stations"]}


# ---------------------------------------------------------------- the map layers
@pytest.mark.asyncio
async def test_map_layers_are_the_rf25_grid_with_eight_regions(async_client: AsyncClient):
    m = (await async_client.get("/api/places/map")).json()
    g = m["grid"]
    assert (g["n_lat"], g["n_lon"], g["row0"]) == (129, 135, "south")
    assert len(m["rows"]) == 129 and all(len(r) == 135 and set(r) <= set("012345678") for r in m["rows"])
    assert m["regions"] == [1, 2, 3, 4, 5, 6, 7, 8] and m["held_out_regions"] == [3, 6]
    assert 4000 < sum(ch != "0" for r in m["rows"] for ch in r) < 6000            # about 4,964 land cells
    assert "not IMD's own region boundaries" in m["note"]


# ---------------------------------------------------------------- the check -> flag -> audit cycle
def test_position_from_row_accepts_real_coordinates_only():
    assert stations_svc.position_from_row({"Latitude": "19.07", "LON": 72.88}) == (19.07, 72.88)
    for bad in ({}, {"lat": "x", "lon": "1"}, {"lat": 0, "lon": 0}, {"lat": 95, "lon": 10}, {"lat": 10}, {"lat": "nan", "lon": "5"}):
        assert stations_svc.position_from_row(bad) is None


@pytest.mark.asyncio
async def test_empty_platform_has_no_stations(async_client: AsyncClient):
    body = (await async_client.get("/api/validation/stations")).json()
    assert body["stations"] == [] and body["positioned"] == 0 and body["storage"] == "SQLite file"


@pytest.mark.asyncio
async def test_a_catalogue_station_is_positioned_and_flows_from_checked_to_flagged_to_audited(async_client: AsyncClient):
    sid = next(iter(load_catalog()))
    run = await upload(async_client, daily_csv(sid, [0, 1.2, 0.4, -3.0, 2.0, 0.0]))
    s = (await cycle(async_client))[sid]
    assert s["position_source"] == "catalogue" and s["place"] and s["latitude"] is not None
    assert (s["checked"], s["runs"], s["synthetic_rows"]) == (6, 1, 0) and s["latest_run_id"] == run["id"]
    assert s["flagged"] == s["suspect"] + s["uncertain"] >= 1 and s["audited"] == 0 and s["unaudited"] == s["flagged"]
    assert "impossible_value" in s["top_checks"]               # the daily profile's check for a negative total
    rows = (await async_client.get(f"/api/validation/runs/{run['id']}/rows?verdict=SUSPECT")).json()["rows"]
    url = f"/api/validation/runs/{run['id']}/rows/{rows[0]['id']}/review"
    assert (await async_client.post(url, json={"decision": "confirmed_fault", "reviewer": "asha"}, headers=H)).status_code == 201
    s = (await cycle(async_client))[sid]
    assert s["audited"] == 1 and s["unaudited"] == s["flagged"] - 1 and s["decisions"]["confirmed_fault"] == 1
    # the latest decision on a row is the one that counts, and an audit never changes the verdict
    assert (await async_client.post(url, json={"decision": "false_alarm"}, headers=H)).status_code == 201
    s = (await cycle(async_client))[sid]
    assert s["audited"] == 1 and s["decisions"]["false_alarm"] == 1 and s["decisions"]["confirmed_fault"] == 0
    assert s["suspect"] == (await cycle(async_client))[sid]["suspect"]


@pytest.mark.asyncio
async def test_an_uploaded_station_is_drawn_only_if_the_file_gives_coordinates(async_client: AsyncClient):
    await upload(async_client, daily_csv("NOPOS", [0, 1, 2]))
    await upload(async_client, daily_csv("HASPOS", [0, 1, 2], ",latitude,longitude", ",19.2,72.9"))
    c = await cycle(async_client)
    assert c["NOPOS"]["latitude"] is None and c["NOPOS"]["position_source"] is None
    assert (c["HASPOS"]["latitude"], c["HASPOS"]["longitude"], c["HASPOS"]["position_source"]) == (19.2, 72.9, "upload")
    body = (await async_client.get("/api/validation/stations")).json()
    assert body["count"] == 2 and body["positioned"] == 1


@pytest.mark.asyncio
async def test_a_review_of_a_row_that_is_no_longer_flagged_does_not_count_as_an_audit(async_client: AsyncClient):
    """A live run re-scores its rows and reviews survive that: the audit count must not let an old review hide an unaudited flag."""
    run = await upload(async_client, daily_csv("RESCORED", [0, -5, 1, -2]))
    rows = (await async_client.get(f"/api/validation/runs/{run['id']}/rows?verdict=SUSPECT")).json()["rows"]
    assert len(rows) == 2
    url = f"/api/validation/runs/{run['id']}/rows/{rows[0]['id']}/review"
    assert (await async_client.post(url, json={"decision": "confirmed_fault"}, headers=H)).status_code == 201
    assert (await cycle(async_client))["RESCORED"]["audited"] == 1
    async with async_session_factory() as s:                                   # the reviewed row is re-scored to OK
        row = await s.get(ValidationResult, rows[0]["id"])
        row.verdict = "OK"
        await s.commit()
    c = (await cycle(async_client))["RESCORED"]
    assert (c["flagged"], c["audited"], c["unaudited"]) == (1, 0, 1)           # the other flagged row is still awaiting audit


@pytest.mark.asyncio
async def test_positions_from_uploads_are_batched_and_a_cap_is_reported(async_client: AsyncClient, monkeypatch):
    body = "day,station_id,mm,latitude,longitude\n" + "\n".join(f"2026-07-01,U{i},1.0,{19 + i / 10},{72.8 + i / 10}" for i in range(5)) + "\n"
    await upload(async_client, body.encode())
    full = (await async_client.get("/api/validation/stations")).json()
    assert full["positioned"] == 5 and full["positions_truncated"] is False
    monkeypatch.setattr(stations_svc, "UPLOAD_POSITION_LOOKUPS", 2)
    cut = (await async_client.get("/api/validation/stations")).json()
    assert cut["positioned"] == 2 and cut["positions_truncated"] is True


@pytest.mark.asyncio
async def test_the_station_list_is_capped_with_the_busiest_audit_backlog_first(async_client: AsyncClient, monkeypatch):
    await upload(async_client, daily_csv("OKAY", [0, 1, 2]))
    await upload(async_client, daily_csv("FLAGGED", [0, -1, 2]))
    monkeypatch.setattr(stations_svc, "STATION_CAP", 1)
    body = (await async_client.get("/api/validation/stations")).json()
    assert (body["count"], body["shown"], body["truncated"]) == (2, 1, True) and body["stations"][0]["station_id"] == "FLAGGED"


@pytest.mark.asyncio
async def test_synthetic_rows_are_counted_apart(async_client: AsyncClient):
    await upload(async_client, daily_csv("LAB1", [0, 1, 2, 3]), synthetic="true")
    await upload(async_client, daily_csv("LAB1", [0, 1]))
    s = (await cycle(async_client))["LAB1"]
    assert (s["checked"], s["synthetic_rows"], s["runs"]) == (6, 4, 2)


@pytest.mark.asyncio
async def test_the_audit_queue_can_be_limited_to_one_station(async_client: AsyncClient):
    await upload(async_client, daily_csv("ST-A", [0, -5, 1]))
    await upload(async_client, daily_csv("ST-B", [0, -2, -1]))
    everyone = (await async_client.get("/api/validation/review/queue")).json()
    one = (await async_client.get("/api/validation/review/queue?station=ST-B")).json()
    assert everyone["total"] == 3 and one["total"] == 2 and {r["station_id"] for r in one["rows"]} == {"ST-B"}
    assert (await async_client.get("/api/validation/review/queue?station=NOPE")).json()["total"] == 0


@pytest.mark.asyncio
async def test_stations_with_unaudited_flags_come_first(async_client: AsyncClient):
    await upload(async_client, daily_csv("CLEAN", [0, 1, 2, 1]))
    await upload(async_client, daily_csv("BAD", [0, -5, 1, -2]))
    ids = [s["station_id"] for s in (await async_client.get("/api/validation/stations")).json()["stations"]]
    assert ids.index("BAD") < ids.index("CLEAN")
