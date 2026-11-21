"""qc.sparse on a GENERATED 6 x 8 grid: gauge placement, the gauge file, the scoring pass (a fake score function, no torch) and the sparse masks."""
import json

import numpy as np
import pytest

from qc import sparse as S
from qc.grid import Grid
from qc.scoring import Block

LAT = np.arange(8.0, 9.5, 0.25)            # 6 rows, 0.25 degree steps
LON = np.arange(76.0, 78.0, 0.25)          # 8 columns


def grid():
    land = np.ones((6, 8), dtype=bool)
    land[0, 0] = False                      # one sea cell
    return Grid.from_land(LAT, LON, land)


def test_a_point_goes_to_the_cell_that_contains_it_and_the_edges_are_stated():
    g = grid()
    hit, why = S.cell_of(g, 8.60, 76.80)                    # inside the cell centred 8.5 / 76.75
    assert why is None and (hit.row, hit.col) == (2, 3) and hit.offset_deg == (0.10, 0.05)
    hit, _ = S.cell_of(g, 8.5, 76.75)
    assert hit.offset_deg == (0.0, 0.0)
    assert S.cell_of(g, 8.62, 76.75)[0].row == 2             # 0.12 above the centre: still this cell (half step is 0.125)
    assert S.cell_of(g, 8.64, 76.75)[0].row == 3             # 0.14 above: the next cell


def test_rejections_say_why():
    g = grid()
    assert S.cell_of(g, None, 77.0) == (None, "no coordinates")
    assert S.cell_of(g, float("nan"), 77.0)[1] == "no coordinates"
    assert S.cell_of(g, 20.0, 77.0)[1] == "outside the grid"
    assert S.cell_of(g, 8.0, 76.0)[1] == "on a sea cell (not land in the grid)"      # row 0, col 0 is the sea cell


def test_gauges_become_a_sparse_field_and_shared_cells_are_averaged():
    g = grid()
    periods = S.date_range("2026-03-01", "2026-03-03")
    a = S.Gauge("A", 8.5, 76.75, {"2026-03-01": 4.0, "2026-03-02": 0.0, "2026-03-03": None})
    b = S.Gauge("B", 8.55, 76.70, {"2026-03-01": 6.0, "2026-03-02": 2.0})               # same cell as A
    c = S.Gauge("C", 9.25, 77.75, {"2026-03-01": 1.0})
    far = S.Gauge("F", 40.0, 77.0, {"2026-03-01": 9.0})
    empty = S.Gauge("E", 8.75, 77.0, {"1999-01-01": 3.0})                                # no day inside the period
    obs, rep = S.gauges_to_obs(g, [a, b, c, far, empty], periods)
    assert obs.shape == (3, g.n_land) and rep["placed"] == 3 and rep["cells"] == 2
    ia = rep["placements"]["A"]["land_index"]
    assert rep["placements"]["B"]["land_index"] == ia and rep["shared_cells"] == {ia: ["A", "B"]}
    assert obs[0, ia] == 5.0 and obs[1, ia] == 1.0 and np.isnan(obs[2, ia])                # averaged; a day without data stays NaN
    assert rep["rejected"] == {"F": "outside the grid", "E": "no usable day inside the period"}
    assert int(np.isfinite(obs).sum()) == 3                                              # nothing outside the two gauge cells is filled in


def test_negative_and_non_finite_amounts_are_dropped():
    g = grid()
    obs, rep = S.gauges_to_obs(g, [S.Gauge("A", 8.5, 76.75, {"2026-03-01": -1.0, "2026-03-02": float("inf"), "2026-03-03": 2.0})], S.date_range("2026-03-01", "2026-03-03"))
    assert np.isnan(obs[0]).all() and np.isnan(obs[1]).all() and np.nanmax(obs[2]) == 2.0


def test_day_of_year_counts_from_zero_with_leap_years():
    assert S.doy0(["2026-01-01", "2026-12-31", "2024-12-31"]).tolist() == [0, 364, 365]


def test_gauge_file_parsing():
    text = json.dumps({"gauges": [{"station": "ZWL001", "lat": 8.5, "lon": 76.75, "days": {"2026-03-01": 1.5}}]})
    (g,) = S.parse_gauge_file(text)
    assert g.station == "ZWL001" and g.days["2026-03-01"] == 1.5
    for bad in ("not json", "{}", json.dumps({"gauges": [{"station": "", "days": {}}]}), json.dumps({"gauges": [{"station": "A", "days": []}]})):
        with pytest.raises(ValueError):
            S.parse_gauge_file(bad)


def test_score_gauges_scores_every_day_keeps_only_gauge_cells_and_starts_with_empty_history():
    g = grid()
    seen = {}

    def fake(block: Block):
        seen["pad"], seen["rows"], seen["split"] = block.pad, block.obs.shape[0], block.split
        seen["history_empty"] = bool(np.isnan(block.obs[:block.pad]).all())
        out = np.where(np.isfinite(block.target), block.target * 10.0, np.nan).astype(np.float32)        # scores only where there is a reading
        return out

    gauges = [S.Gauge("A", 8.5, 76.75, {"2026-03-01": 1.0, "2026-03-03": 3.0}), S.Gauge("C", 9.25, 77.75, {"2026-03-02": 2.0})]
    res = S.score_gauges(g, gauges, fake, history_days=5)
    assert res["periods"] == ["2026-03-01", "2026-03-02", "2026-03-03"]
    assert seen == {"pad": 5, "rows": 8, "split": "live", "history_empty": True}
    assert res["scores"].shape == (3, 2) and len(res["lat"]) == 2
    assert sorted(np.round(res["lat"], 2).tolist()) == [8.5, 9.25]
    assert np.isfinite(res["scores"]).sum() == 3                                         # 3 readings, 3 scores: a gap day stays NaN


def test_scores_are_withheld_until_a_cell_has_enough_days_of_its_own():
    g = grid()
    days = {f"2026-03-{d:02d}": 1.0 for d in range(1, 11)}                              # 10 observed days
    gauges = [S.Gauge("A", 8.5, 76.75, days)]
    keep_all = S.score_gauges(g, gauges, lambda b: np.where(np.isfinite(b.target), 1.0, np.nan).astype(np.float32), 5)
    assert np.isfinite(keep_all["scores"]).sum() == 10 and keep_all["report"]["withheld_scores"] == 0
    cut = S.score_gauges(g, gauges, lambda b: np.where(np.isfinite(b.target), 1.0, np.nan).astype(np.float32), 5, min_history_days=4)
    assert np.isfinite(cut["scores"]).sum() == 6 and cut["report"]["withheld_scores"] == 4      # days 1-4 have fewer than 4 days before them
    assert np.isnan(cut["scores"][:4]).all() and np.isfinite(cut["scores"][4:]).all()
    with pytest.raises(ValueError, match="first 20 days"):
        S.score_gauges(g, gauges, lambda b: np.where(np.isfinite(b.target), 1.0, np.nan).astype(np.float32), 5, min_history_days=20)


def test_score_gauges_refuses_an_empty_or_unplaceable_file():
    g = grid()
    with pytest.raises(ValueError, match="no rain day"):
        S.score_gauges(g, [S.Gauge("A", 8.5, 76.75, {})], lambda b: b.target, 3)
    with pytest.raises(ValueError, match="no gauge could be placed"):
        S.score_gauges(g, [S.Gauge("A", 50.0, 76.75, {"2026-03-01": 1.0})], lambda b: b.target, 3)
    with pytest.raises(ValueError, match="no finite score"):
        S.score_gauges(g, [S.Gauge("A", 8.5, 76.75, {"2026-03-01": 1.0})], lambda b: np.full(b.target.shape, np.nan, np.float32), 3)


def test_sparse_keep_is_deterministic_land_only_and_the_right_size():
    g = grid()
    k1, k2 = S.sparse_keep(g, 10, seed=7), S.sparse_keep(g, 10, seed=7)
    assert (k1 == k2).all() and int(k1.sum()) == 10 and not k1[0, 0] and not (k1 & ~g.land).any()
    assert not (S.sparse_keep(g, 10, seed=8) == k1).all()
    for bad in (0, g.n_land + 1):
        with pytest.raises(ValueError):
            S.sparse_keep(g, bad, 1)


def test_sparse_functions_hide_cells_from_the_scorer_and_do_not_touch_the_block():
    g = grid()
    obs = np.ones((4, g.n_land), dtype=np.float32)
    block = Block(2014, "val", obs, 1, np.arange(4, dtype=np.int16), None)
    seen = {}

    def base(b: Block):
        seen["valid"] = int(np.isfinite(b.obs).any(axis=0).sum())
        return np.where(np.isfinite(b.target), 1.0, np.nan).astype(np.float32)

    ((name, fn),) = S.sparse_functions({"stnet_fault_s42": base}, g, 6, seed=3, only="stnet_fault_s42").items()
    assert name == "stnet_fault_sparse6_s42"
    out = fn(block)
    assert seen["valid"] == 6 and int(np.isfinite(out).any(axis=0).sum()) == 6
    assert np.isfinite(block.obs).all()                                                   # the original block is untouched
    with pytest.raises(KeyError):
        S.sparse_functions({}, g, 6, 1, "missing")


def test_the_markdown_table_reads_the_metrics_defensively():
    res = {"seed": 42, "label_tier": "SYNTHETIC faults, validation years only", "caveats": ["x"], "budgets_per_1000": [1.0],
           "rows": [{"cells": None, "label": "full field", "component": "c", "metrics": {"groups": {"seen": {"budgets": {"1.0": {"recall": 0.65, "event_recall": 0.7}}}}}},
                    {"cells": 20, "label": "20 cells", "component": "d", "metrics": {"unexpected": True}}]}
    md = S.to_markdown(res)
    assert "| full field | 0.650 | 0.700 |" in md and "| 20 cells | n/a | n/a |" in md
