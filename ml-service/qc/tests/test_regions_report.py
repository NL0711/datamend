"""qc.regions_report on small arrays and on the generated QC world (own run folder, name xreg)."""

import csv
import json

import numpy as np
import pytest

from qc import regions_report as RR
from qc.baselines import run_untrained
from qc.config import load_config
from qc.grid import Grid
from qc.prepare import prepare
from qc.regions import RegionMap, cell_weights, region_map_from_clients
from qc.runs import write_json
from qc.testscore import lock_path as daily_lock_path


def test_largest_cluster_counts_eight_connected_cells():
    g = np.zeros((6, 6), bool)
    assert RR.largest_cluster(g) == 0
    g[1, 1] = g[2, 2] = g[3, 3] = True                     # a diagonal chain is one cluster under 8-connectivity
    g[5, 0] = True
    assert RR.largest_cluster(g) == 3


def test_unit_day_series_shares_clusters_and_drivers():
    lat, lon = np.linspace(8, 30, 6), np.linspace(70, 90, 8)
    grid = Grid.from_land(lat, lon, np.ones((6, 8), bool))
    n = grid.n_land
    rmap = RegionMap("t", np.where(grid.cols < 4, 1, 2), {1: "west", 2: "east"})
    T = 3
    score = np.zeros((T, n), np.float32)
    west = np.nonzero(grid.cols < 4)[0]
    score[1, west[:5]] = 10.0                                # day 1: five cells of the west are very high (a mix of final and review)
    score[2, west] = 3.0                                     # day 2: the whole west is above the review threshold only
    truth = np.zeros((T, n), bool)
    truth[1, west[:2]] = True
    driver = np.full((T, n), -1, np.float32)
    driver[1, west[:5]] = 1.0
    s = RR.unit_day_series(score, 2.0, 5.0, rmap, cell_weights(grid), grid, truth, driver, n_scales=2)
    w, e = s[1], s[2]
    assert w["final_cells"].tolist() == [0, 5, 0] and w["review_cells"].tolist() == [0, 5, 24]      # the west is 6 rows x 4 columns = 24 cells
    assert w["review_share"][2] == pytest.approx(1.0) and w["final_share"][2] == pytest.approx(0.0)
    assert w["largest_final_cluster"][1] >= 1 and w["largest_final_cluster"][0] == 0
    assert w["driver"].tolist() == [-1, 1, -1]
    assert np.nanmax(w["injected_fault_share"]) > 0 and np.nanmax(e["final_share"]) == 0.0


@pytest.fixture(scope="module")
def pr(world, bench):
    p = prepare(load_config(world / "test.yaml", ["name=xreg"]), check_data=False)
    run_untrained(p, ("val", "test"))
    return p


@pytest.fixture(autouse=True)
def no_daily_lock(pr):
    f = daily_lock_path(pr)
    if f.is_file():
        f.unlink()
    yield
    if f.is_file():
        f.unlink()


BUDGETS = {"final_per_1000": 1.0, "review_per_1000": 5.0, "applies_to": "rules"}


def test_validation_output_is_written_with_provenance_and_daily_rows(pr, tmp_path):
    maps = {"client region (stand-in, not IMD)": region_map_from_clients(pr.cell_client)}
    out = RR.build_regional_output(pr, "rules", "val", maps, tmp_path, BUDGETS)
    doc = json.loads(out["json"].read_text(encoding="utf-8"))
    prov = doc["provenance"]
    assert "SYNTHETIC" in prov["label"] and prov["component"] == "rules" and prov["budgets_apply_to"] == "rules"
    assert prov["thresholds"]["final"] > prov["thresholds"]["review"] > 0 and prov["benchmark_hash"]
    n_units = len(maps["client region (stand-in, not IMD)"].names)
    assert len(doc["units"]) == n_units
    days = sum(366 if y % 4 == 0 else 365 for y in pr.split.years["val"])
    rows = list(csv.DictReader(open(out["csv"], encoding="utf-8")))
    assert len(rows) == n_units * days
    shares = [float(r["final_share"]) for r in rows if r["final_share"] != ""]
    assert shares and 0.0 <= min(shares) and max(shares) <= 1.0
    assert any(float(r["injected_fault_share"]) > 0 for r in rows if r["injected_fault_share"] != "")      # the benchmark has faults in it
    u0 = doc["units"][0]
    total_days = sum(r["days_with_final_flag"] for r in u0["monthly"])
    csv_days = sum(1 for r in rows if r["unit_id"] == str(u0["unit_id"]) and int(r["final_cells"]) > 0)
    assert total_days == csv_days                                                                           # the monthly roll-up matches the daily rows
    assert sum(r["final_cell_days"] for r in u0["monthly"]) == sum(int(r["final_cells"]) for r in rows if r["unit_id"] == str(u0["unit_id"]))


def test_test_and_stress_years_wait_for_the_daily_test_pass(pr, tmp_path):
    maps = {"client region (stand-in, not IMD)": region_map_from_clients(pr.cell_client)}
    with pytest.raises(RuntimeError, match="only after the daily test pass is finished"):
        RR.build_regional_output(pr, "rules", "test", maps, tmp_path, BUDGETS)
    write_json(daily_lock_path(pr), {"status": "started"})
    with pytest.raises(RuntimeError, match="only after the daily test pass is finished"):
        RR.build_regional_output(pr, "rules", "test", maps, tmp_path, BUDGETS)
    write_json(daily_lock_path(pr), {"status": "done"})
    out = RR.build_regional_output(pr, "rules", "test", maps, tmp_path, BUDGETS)
    assert out["json"].name == "regional_test.json" and out["csv"].is_file()
    with pytest.raises(ValueError, match="split must be"):
        RR.build_regional_output(pr, "rules", "all", maps, tmp_path, BUDGETS)
