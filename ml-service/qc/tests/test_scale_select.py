"""qc.scale_select: metrics, selection rule and an end-to-end run on small generated data."""

import numpy as np
import pytest

from qc import resolution as R
from qc import scale_select as SS
from qc.grid import Grid
from qc.period_benchmark import PeriodYear, build_period_benchmark
from qc.scale_scorers import make_context
from qc.splits import Split

H, W = 12, 14


def _py(rng, fault_share=0.05, P=12, n=60, year=2000):
    tot = rng.gamma(4.0, 20.0, (P, n)).astype(np.float32)
    clean = R.Periods("monthly", year, tot, np.ones((P, n), np.float32), tot / 5, np.full(P, 30, np.int32), np.ones((P, n), bool))
    fault = rng.random((P, n)) < fault_share
    bad = clean.copy()
    bad.total[fault] *= 5.0
    z = np.zeros((P, n), bool)
    return PeriodYear(year, "monthly", clean, bad, fault, np.zeros((P, n), bool), np.full((P, n), -1, np.int8), z, z, np.ones((P, n), bool))


def test_runs_group_consecutive_faulty_periods_per_cell():
    f = np.zeros((6, 3), bool)
    f[1:4, 0] = True
    f[0, 1] = f[2, 1] = True
    ids = SS._runs(f)
    assert len(set(ids[1:4, 0])) == 1 and ids[1, 0] > 0
    assert ids[0, 1] != ids[2, 1] and (ids[~f] == 0).all()
    assert ids.max() == 3


def test_evaluate_scores_perfect_and_blind_scorers():
    rng = np.random.default_rng(0)
    years = {y: _py(rng, year=y) for y in range(2000, 2008)}
    perfect = {y: py.fault * 10.0 + rng.random(py.fault.shape) for y, py in years.items()}
    blind = {y: rng.random(py.fault.shape) for y, py in years.items()}
    good = SS.evaluate_scores(perfect, years, [2006, 2007], (1.0, 5.0), np.random.default_rng(1), 100)
    bad = SS.evaluate_scores(blind, years, [2006, 2007], (1.0, 5.0), np.random.default_rng(1), 100)
    g, b = good["budgets"]["1.0"], bad["budgets"]["1.0"]
    assert g["recall"] > 0.99 and g["event_recall"] > 0.99 and good["pr_auc"] > 0.95
    assert b["recall"] < 0.1 and bad["pr_auc"] < 0.2
    assert g["recall_ci"] is not None and g["recall_ci"][0] <= g["recall"] <= g["recall_ci"][1] + 1e-9    # 8 years: an interval exists
    assert good["out_of_sample_years"] == [2000, 2001, 2002, 2003, 2004, 2005]
    assert g["false_per_1000_out_of_sample"] is not None and g["false_per_1000_all_years"] is not None


def test_no_interval_with_fewer_than_five_years():
    rng = np.random.default_rng(1)
    years = {y: _py(rng, year=y) for y in range(2000, 2004)}
    sc = {y: py.fault * 10.0 + rng.random(py.fault.shape) for y, py in years.items()}
    r = SS.evaluate_scores(sc, years, [2002, 2003], (1.0,), np.random.default_rng(0), 100)
    assert r["budgets"]["1.0"]["recall_ci"] is None and r["budgets"]["1.0"]["false_per_1000_out_of_sample_ci"] is None


def test_threshold_years_must_exist_and_have_enough_clean_periods():
    rng = np.random.default_rng(2)
    years = {2000: _py(rng, year=2000, P=1, n=10)}
    sc = {2000: rng.random((1, 10))}
    with pytest.raises(ValueError):
        SS.evaluate_scores(sc, years, [1999], (1.0,))
    with pytest.raises(ValueError, match="cannot set a budget threshold"):
        SS.evaluate_scores(sc, years, [2000], (1.0,))


def _agg(recall, se, fa=0.5, budget="1.0"):
    return {"budgets": {budget: {"recall": recall, "recall_se": se, "false_per_1000_out_of_sample": fa}}}


def test_selection_prefers_the_simplest_within_one_standard_error():
    res = {"simple": _agg(0.70, 0.02), "mid": _agg(0.74, 0.02), "best": _agg(0.75, 0.03)}
    cx = {"simple": 0, "mid": 2, "best": 3}
    s = SS.select_simplest(res, cx, "1.0")
    assert s["best"] == "best" and s["chosen"] == "mid"            # floor 0.72: simple is too far below, mid is the simplest inside
    res["simple"] = _agg(0.73, 0.02)
    assert SS.select_simplest(res, cx, "1.0")["chosen"] == "simple"


def test_selection_excludes_candidates_that_break_the_false_alarm_guard():
    res = {"simple": _agg(0.60, 0.02, fa=0.5), "best": _agg(0.95, 0.02, fa=9.0)}
    s = SS.select_simplest(res, {"simple": 0, "best": 3}, "1.0")
    assert s["chosen"] == "simple"                                  # 9 per 1,000 against a budget of 1 is more than 3x
    assert SS.select_simplest({"x": _agg(None, 0.0)}, {"x": 0}, "1.0")["chosen"] is None


def _world(n_years=10):
    lat, lon = np.linspace(8, 30, H), np.linspace(70, 90, W)
    land = np.ones((H, W), bool)
    grid = Grid.from_land(lat, lon, land)
    n = grid.n_land
    rng = np.random.default_rng(3)
    base = 60 + 30 * np.sin(grid.rows / 3.0) + 20 * np.cos(grid.cols / 4.0)
    allp = {}
    for i in range(n_years):
        y = 1980 + i
        yr = rng.normal(0, 0.2)
        tot = np.stack([rng.gamma(8.0, base * (0.3 + 1.4 * np.exp(-((m - 6.5) / 1.8) ** 2)) * np.exp(yr) / 8.0) for m in range(12)]).astype(np.float32)
        allp[y] = R.Periods("monthly", y, tot, (tot > 1).astype(np.float32), tot / 8, np.full(12, 30, np.int32), np.ones((12, n), bool))
    client = np.where(grid.cols < 7, 1, 2)
    return grid, client, allp


def test_run_selection_end_to_end(tmp_path):
    grid, client, allp = _world(24)
    train_y, val_y = list(range(1980, 1992)), list(range(1992, 2004))
    split = Split(np.zeros((H, W), np.int8), np.zeros((H, W), np.int8), [], 0,
                  {"train": train_y, "val": val_y, "test": [], "fusion_fit": val_y, "threshold": val_y[-3:], "stress": []})
    stats = R.fit_scale_stats({y: allp[y] for y in train_y}, train_y, split, client, "monthly")
    ctx = make_context(grid, client, stats)
    years = {}
    for y in val_y:
        bad, pf = R.corrupt_periods(allp[y], np.random.default_rng(y), 0.04)
        z = np.zeros(pf.labels.shape, bool)
        years[y] = PeriodYear(y, "monthly", allp[y], bad, pf.labels, z, pf.kind, z, z, allp[y].valid & bad.valid)
    out = SS.run_selection(["gamma_zero", "loo_median", "gbm_neighbour"], {y: allp[y] for y in train_y}, ctx, years,
                           split.years["threshold"], (1.0, 5.0), seeds=(0, 1), n_boot=50)
    assert out["scale"] == "monthly" and "SYNTHETIC" in out["label"]
    assert out["candidates"]["gamma_zero"]["seeds"] == 1 and out["candidates"]["gbm_neighbour"]["seeds"] == 2
    assert out["selection"]["chosen"] in out["candidates"]
    assert out["candidates"]["loo_median"]["budgets"]["5.0"]["recall"] > 0.3                 # scaled and dropped periods are found
    md = SS.write_selection(tmp_path, out)
    text = md.read_text(encoding="utf-8")
    assert "gamma_zero" in text and "SYNTHETIC" in text and (tmp_path / "selection_monthly.json").is_file()
    with pytest.raises(KeyError):
        SS.run_selection(["nope"], {}, ctx, years, split.years["threshold"])


def test_run_for_prepared_on_the_generated_qc_world(prepared, bench, tmp_path):
    build_period_benchmark(prepared, splits=("val", "test"), overwrite=True)
    out = SS.run_for_prepared(prepared, "monthly", ["gamma_zero", "loo_median"], tmp_path, seeds=(0,), n_boot=20)
    assert out["selection"]["chosen"] in ("gamma_zero", "loo_median", None)
    assert out["years"] == list(prepared.split.years["val"])
    assert (tmp_path / "selection_monthly.md").is_file()
