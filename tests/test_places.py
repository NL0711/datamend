"""Place lookup and score-provider seam (spec slice 8). Grid tests carried over from the deleted Locations suite; no network, no database writes."""
import json
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from backend.app.db.database import async_session_factory
from backend.app.places import grid
from backend.app.places.lookup import locate
from backend.app.places.scores import FileScoreProvider, model_block
from backend.app.validation.models import Explanation, Review, ValidationCheckHit, ValidationResult, ValidationRun


# ---------------------------------------------------------------- grid (carried over)
def test_mumbai_is_four_land_cells_in_the_held_out_region():
    cells = grid.cells_for(19.0760, 72.8777, 15.0)
    assert [(grid.lat_of(r), grid.lon_of(c)) for r, c in cells] == [(19.0, 72.75), (19.0, 73.0), (19.25, 72.75), (19.25, 73.0)]
    for r, c in cells:
        d = grid.describe_cell(r, c)
        assert d["is_land"] is True and d["client"] == 6 and d["held_out"] is True


def test_cell_of_uses_the_southernmost_row_as_row_zero_and_rejects_points_outside():
    assert grid.cell_of(6.5, 66.5) == (0, 0)
    assert grid.cell_of(38.5, 100.0) == (128, 134)
    assert grid.cell_of(19.07, 72.88) == (50, 26)
    for lat, lon in ((5.0, 70.0), (20.0, 120.0), (45.0, 80.0)):
        with pytest.raises(grid.GridError, match="outside the grid"):
            grid.cell_of(lat, lon)


def test_a_point_always_includes_its_own_cell_and_huge_areas_are_refused():
    assert grid.cells_for(19.0, 72.75, 0.0) == [(50, 25)]
    with pytest.raises(grid.GridError, match="at most"):
        grid.cells_for(19.0, 73.0, 100.0)
    with pytest.raises(grid.GridError):
        grid.cells_for(19.0, 73.0, -1.0)


def test_sea_cells_are_marked_not_land():
    r, c = grid.cell_of(19.0, 72.5)                                   # Arabian Sea west of Mumbai
    assert grid.describe_cell(r, c)["is_land"] is False and grid.describe_cell(r, c)["client"] is None


# ---------------------------------------------------------------- locate
def test_locate_returns_cell_land_status_and_region_and_is_honest_about_imd():
    p = locate(19.0760, 72.8777)
    assert (p["cell"]["row"], p["cell"]["col"], p["cell"]["grid"]) == (50, 26, "RF25 0.25 degree")
    assert (p["cell"]["lat"], p["cell"]["lon"]) == (19.0, 73.0)
    assert p["is_land"] is True and p["client_region"] == 6
    assert p["imd_subdivision"]["status"] == "not_available" and "NOT IMPLEMENTED" in p["imd_subdivision"]["reason"]


def test_locate_sea_point_has_no_region_and_outside_the_grid_raises():
    p = locate(19.0, 72.5)
    assert p["is_land"] is False and p["client_region"] is None
    with pytest.raises(grid.GridError):
        locate(45.0, 80.0)
    with pytest.raises(grid.GridError):
        locate(float("nan"), 80.0)


# ---------------------------------------------------------------- score provider: never invented
def test_model_scores_are_never_invented(tmp_path):
    day = date(2026, 11, 16)
    assert model_block(None, 50, 25, day)["status"] == "not_available"
    prov = FileScoreProvider(tmp_path)
    assert model_block(prov, 50, 25, day)["status"] == "not_available"
    (tmp_path / "50_25.json").write_text(json.dumps({"model": "m", "version": "t", "label_tier": "synthetic",
                                                       "scores": {"2026-11-16": {"fault_scores": {"scale": 1.2}, "fused": 1.9, "calibrated": False}}}))
    got = model_block(prov, 50, 25, day)
    assert got["status"] == "ok" and got["scores"]["fused"] == 1.9 and got["label_tier"] == "synthetic"
    assert model_block(prov, 50, 25, date(2026, 11, 17))["status"] == "not_available"
    (tmp_path / "50_26.json").write_text("not json")
    assert model_block(prov, 50, 26, day)["status"] == "not_available"


# ---------------------------------------------------------------- API and the run report
@pytest_asyncio.fixture(autouse=True)
async def _clean():
    async with async_session_factory() as s:
        for m in (Review, Explanation, ValidationCheckHit, ValidationResult, ValidationRun):
            await s.execute(delete(m))
        await s.commit()
    yield


@pytest.mark.asyncio
async def test_locate_endpoint_is_stateless_and_validates(async_client: AsyncClient):
    ok = await async_client.get("/api/places/locate?lat=19.076&lon=72.8777")
    assert ok.status_code == 200 and ok.json()["client_region"] == 6
    assert (await async_client.get("/api/places/locate?lat=45&lon=80")).status_code == 422
    assert (await async_client.get("/api/places/locate?lat=abc&lon=80")).status_code == 422
    assert (await async_client.get("/api/places/locate?lat=91&lon=80")).status_code == 422
    assert (await async_client.get("/api/places/locate")).status_code == 422
    assert (await async_client.get("/api/locations")).status_code == 404            # the Locations feature is gone


@pytest.mark.asyncio
async def test_run_report_adds_cell_and_region_per_station_when_coordinates_are_given(async_client: AsyncClient):
    csv_text = "day,station_id,mm,latitude,longitude\n2026-07-01,PUNE,1.0,18.52,73.86\n2026-07-01,FAR,1.0,50.0,10.0\n2026-07-01,NOCOORD,1.0,,\n"
    r = await async_client.post("/api/validation/runs", files={"file": ("d.csv", csv_text.encode(), "text/csv")}, data={"profile": "daily"})
    assert r.status_code == 201, r.text
    st = r.json()["report"]["stations"]
    assert st["PUNE"]["place"]["is_land"] is True and st["PUNE"]["place"]["cell"]["row"] == 48
    assert st["FAR"]["place"]["cell"] is None and "outside the grid" in st["FAR"]["place"]["reason"]
    assert st["NOCOORD"]["place"] is None
