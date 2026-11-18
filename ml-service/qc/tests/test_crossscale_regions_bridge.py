"""qc.crossscale, qc.regions and qc.bridge on small generated arrays (no RF25 needed)."""

import numpy as np
import pytest

from qc import bridge as B
from qc import crossscale as X
from qc import regions as G
from qc.grid import Grid


# ------------------------------------------------------------------------------------------ cross-scale
def test_reference_needs_enough_clean_scores():
    rng = np.random.default_rng(0)
    assert X.reference(rng.random(1000)) > 0.99
    with pytest.raises(ValueError, match="need at least"):
        X.reference(rng.random(20))
    with pytest.raises(ValueError, match="not positive"):
        X.reference(np.zeros(500))


def test_align_to_days_maps_each_day_to_its_period():
    scores = np.arange(12, dtype=np.float32)[:, None] + np.zeros((12, 3), np.float32)
    d = X.align_to_days(scores, 2001, "monthly")
    assert d.shape == (365, 3) and d[0, 0] == 0 and d[31, 0] == 1 and d[-1, 0] == 11
    s = X.align_to_days(np.full((1, 3), 7.0, np.float32), 2001, "seasonal")
    assert np.isnan(s[0]).all() and (s[200] == 7.0).all()                     # July is inside the season, January is not
    assert X.align_to_days(scores, 2000, "monthly").shape[0] == 366


def _parts():
    T, n = 5, 4
    daily = np.full((T, n), 1.0, np.float32)
    monthly = np.full((T, n), 2.0, np.float32)
    yearly = np.full((T, n), np.nan, np.float32)
    daily[1, 0] = 30.0
    monthly[2, 1] = 40.0
    yearly[3, 2] = 50.0
    return {"daily": daily, "monthly": monthly, "yearly": yearly}, {"daily": 10.0, "monthly": 20.0, "yearly": 25.0}


def test_max_fusion_gives_the_largest_ratio_and_its_driver():
    parts, refs = _parts()
    f = X.fuse_scales(parts, refs, "max")
    assert f.names == ["daily", "monthly", "yearly"]
    assert f.score[1, 0] == pytest.approx(3.0) and f.driver[1, 0] == 0
    assert f.score[2, 1] == pytest.approx(2.0) and f.driver[2, 1] == 1
    assert f.score[3, 2] == pytest.approx(2.0) and f.driver[3, 2] == 2          # a scale that is NaN elsewhere still drives where present
    assert f.score[0, 0] == pytest.approx(0.1) and f.driver[0, 0] == 1 or f.driver[0, 0] in (0, 1)


def test_noisy_or_is_the_sum_of_ratios_and_nan_scales_are_ignored():
    parts, refs = _parts()
    f = X.fuse_scales(parts, refs, "noisy_or")
    assert f.score[0, 3] == pytest.approx(1.0 / 10 + 2.0 / 20)                  # the yearly NaN does not count
    only_nan = {"a": np.full((2, 2), np.nan, np.float32), "b": np.full((2, 2), np.nan, np.float32)}
    g = X.fuse_scales(only_nan, {"a": 1.0, "b": 1.0})
    assert np.isnan(g.score).all() and (g.driver == -1).all()


def test_coherent_extreme_rule_lowers_the_score_only_inside_protected_cells():
    parts, refs = _parts()
    prot = np.zeros((5, 4), bool)
    prot[1, 0] = True
    plain = X.fuse_scales(parts, refs, "max")
    f = X.fuse_scales(parts, refs, "max", protected=prot, protected_factor=0.25)
    assert f.score[1, 0] == pytest.approx(plain.score[1, 0] * 0.25)
    assert np.array_equal(np.delete(f.score.ravel(), 4), np.delete(plain.score.ravel(), 4), equal_nan=True)


def test_fusion_input_checks():
    parts, refs = _parts()
    with pytest.raises(ValueError):
        X.fuse_scales(parts, {"daily": 1.0})
    with pytest.raises(ValueError):
        X.fuse_scales(parts, refs, "mean")
    with pytest.raises(ValueError):
        X.fuse_scales({**parts, "monthly": parts["monthly"][:3]}, refs)
    with pytest.raises(ValueError):
        X.fuse_scales(parts, refs, protected=np.zeros((1, 1), bool))
    with pytest.raises(ValueError):
        X.fuse_scales(parts, refs, protected_factor=2.0)


# ---------------------------------------------------------------------------------------------- regions
def _grid():
    lat, lon = np.linspace(8, 30, 6), np.linspace(70, 90, 8)
    land = np.ones((6, 8), bool)
    land[0, 0] = False
    return Grid.from_land(lat, lon, land)


def test_client_stand_in_is_labelled_and_summary_counts_by_region():
    grid = _grid()
    client = np.where(grid.cols < 4, 1, 2)
    rm = G.region_map_from_clients(client)
    assert "NOT IMD" in rm.label and sorted(rm.names) == [1, 2]
    w = G.cell_weights(grid)
    assert (w > 0).all() and w[grid.rows == 0].mean() > w[grid.rows == 5].mean()          # cos(lat): the south is weighted more
    X_, n = 3, grid.n_land
    scored = np.ones((X_, n), bool)
    review = np.zeros((X_, n), bool)
    final = np.zeros((X_, n), bool)
    review[1, client == 1] = True                       # the whole of region 1 is in review in period 1
    final[1, (client == 1) & (grid.rows == 3)] = True
    drv = np.zeros((X_, n), np.int8)
    drv[:, :] = 1
    rows = G.regional_summary(review, final, scored, rm, w, drv, ["daily", "monthly"])
    r1, r2 = rows
    assert r1["review_share_max"] == pytest.approx(1.0) and r2["review_share_max"] == pytest.approx(0.0)
    assert 0 < r1["final_share_max"] < 1 and r1["strongest_scale"] == "monthly"
    assert r1["review_cell_periods"] == int((client == 1).sum()) and r2["strongest_scale"] is None
    with pytest.raises(ValueError):
        G.regional_summary(review[:1], final, scored, rm, w)


def test_area_share_assignment_gives_each_cell_to_its_largest_share():
    grid = _grid()
    names = {1: "west", 2: "east"}
    dlon = abs(grid.lon[1] - grid.lon[0])
    cut = grid.lon[3] + 0.3 * dlon                     # the border lies 0.3 cell east of the centre of column 3: column 3 is mostly west

    def locate(lon, lat):
        out = np.where(lon < cut, 1, 2)
        return np.where(lat > 28.0, 0, out)            # the northernmost row is in no region

    rm = G.assign_by_area_share(grid, locate, names, sub=9)
    north = rm.cell_region[grid.rows == grid.rows.max()]
    assert set(rm.cell_region[(grid.cols == 3) & (grid.rows < grid.rows.max())]) == {1}
    assert set(rm.cell_region[(grid.cols == 4) & (grid.rows < grid.rows.max())]) == {2}
    assert (north == 0).all() and rm.names == names
    with pytest.raises(ValueError, match="not in names"):
        G.assign_by_area_share(grid, lambda lon, lat: np.full(lon.shape, 9), names)
    with pytest.raises(ValueError):
        G.assign_by_area_share(grid, locate, names, sub=0)


def test_homogeneous_regions_are_unions_of_sub_divisions():
    grid = _grid()
    sub = G.RegionMap("subs", np.where(grid.cols < 2, 1, np.where(grid.cols < 4, 2, np.where(grid.cols < 6, 3, 4))),
                      {1: "a", 2: "b", 3: "c", 4: "d"})
    big = G.derive_regions(sub, {10: [1, 2], 20: [3, 4]}, {10: "north", 20: "south"})
    assert set(big.cell_region[grid.cols < 4]) == {10} and set(big.cell_region[grid.cols >= 4]) == {20}
    assert big.names == {10: "north", 20: "south"} and "unions" in big.label
    with pytest.raises(ValueError, match="more than one"):
        G.derive_regions(sub, {10: [1, 2], 20: [2, 3]}, {10: "x", 20: "y"})
    with pytest.raises(ValueError, match="not in the base"):
        G.derive_regions(sub, {10: [1, 9]}, {10: "x"})
    with pytest.raises(ValueError, match="same region ids"):
        G.derive_regions(sub, {10: [1]}, {11: "x"})


def test_unscored_cells_do_not_count():
    grid = _grid()
    rm = G.region_map_from_clients(np.ones(grid.n_land, int))
    scored = np.zeros((2, grid.n_land), bool)
    z = np.zeros_like(scored)
    row = G.regional_summary(z, z, scored, rm, G.cell_weights(grid))[0]
    assert row["review_share_max"] is None and row["final_share_mean"] is None


def test_region_file_is_required_and_validated(tmp_path):
    grid = _grid()
    with pytest.raises(FileNotFoundError, match="not in the repository"):
        G.load_region_map(tmp_path / "missing.csv", grid)
    f = tmp_path / "r.csv"
    f.write_text("region_id,name,row,col\n1,A,1,1\n1,A,1,2\n2,B,2,2\n", encoding="utf-8")
    rm = G.load_region_map(f, grid)
    assert rm.names == {1: "A", 2: "B"} and int((rm.cell_region == 1).sum()) == 2 and int((rm.cell_region == 0).sum()) == grid.n_land - 3
    f.write_text("region_id,name,row,col\n1,A,0,0\n", encoding="utf-8")                 # (0, 0) is sea
    with pytest.raises(ValueError, match="not a land cell"):
        G.load_region_map(f, grid)
    f.write_text("region_id,name,row,col\n1,A,1,1\n2,B,1,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="two regions"):
        G.load_region_map(f, grid)
    f.write_text("id,name\n1,A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="needs the columns"):
        G.load_region_map(f, grid)


# ----------------------------------------------------------------------------------------------- bridge
def _rain(T=200, n=30, seed=0):
    rng = np.random.default_rng(seed)
    return np.where(rng.random((T, n)) < 0.4, rng.gamma(1.2, 8.0, (T, n)), 0.0).astype(np.float32)


def test_pick_lag_finds_a_one_day_shift():
    ref = _rain()
    product = np.roll(ref, -1, axis=0)                # product[t] = ref[t+1]: the reference's day t is the product's day t-1
    out = B.pick_lag(product, ref, np.ones(ref.shape[1]))
    assert out["best_lag"] == -1 and out["correlation_by_lag"][-1] > 0.99      # convention: product day t+lag matches reference day t
    same = B.pick_lag(ref, ref, np.ones(ref.shape[1]))
    assert same["best_lag"] == 0
    with pytest.raises(ValueError):
        B.pick_lag(ref[:10], ref, np.ones(ref.shape[1]))


def test_agreement_perfect_and_noisy():
    ref = _rain()
    perfect = B.agreement(ref, ref)
    assert perfect["pss"] == pytest.approx(1.0) and perfect["far"] == 0 and perfect["bias_pct"] == pytest.approx(0.0, abs=1e-6)
    rng = np.random.default_rng(1)
    noisy = B.agreement(np.clip(ref * 0.3 + rng.normal(0, 2, ref.shape), 0, None), ref)
    assert noisy["bias_pct"] < -30 and noisy["pss"] < 1.0 and noisy["pct_rmse"] > 20
    with pytest.raises(ValueError):
        B.agreement(np.full((3, 3), np.nan), np.full((3, 3), np.nan))


def test_model_shift_detects_a_scaled_score_distribution():
    rng = np.random.default_rng(2)
    a = rng.gamma(2.0, 1.0, 5000)
    same = B.model_shift(a, rng.gamma(2.0, 1.0, 5000))
    shifted = B.model_shift(a, a * 2.0)
    assert not same["shifted"] and shifted["shifted"] and shifted["ks"] > same["ks"]
    with pytest.raises(ValueError):
        B.model_shift(a[:10], a)


def test_bridge_requires_the_owner_to_confirm_the_rule_first():
    ref = _rain()
    with pytest.raises(PermissionError):
        B.run_bridge(ref, ref, np.ones(ref.shape[1]), B.AcceptanceRule(), [2016])


def test_bridge_refuses_years_outside_the_validation_window_and_all_test_years():
    ref = _rain()
    rule = B.AcceptanceRule(confirmed_by_owner=True)
    for bad in ([2015], [2016, 2018], [2025]):
        with pytest.raises(ValueError, match="not allowed"):
            B.run_bridge(ref, ref, np.ones(ref.shape[1]), rule, bad)
    assert B.run_bridge(ref, ref, np.ones(ref.shape[1]), rule, [2016, 2017])["years"] == [2016, 2017]


def test_rule_from_config_dict():
    r = B.rule_from_dict({"min_pss": 0.5, "report_rain_mm": [2.5], "allowed_years": [2016, 2017], "confirmed_by_owner": True,
                          "p99_ratio_band": [0.8, 1.25], "frozen_on": "2026-11-18"})
    assert r.confirmed_by_owner and r.allowed_years == (2016, 2017) and r.report_rain_mm == (2.5,) and r.primary_rain_mm == 0.5
    with pytest.raises(ValueError, match="unknown bridge settings"):
        B.rule_from_dict({"max_pss": 1})


def test_a_model_shift_is_a_warning_not_a_failure():
    ref = _rain()
    rule = B.AcceptanceRule(confirmed_by_owner=True)
    a = np.random.default_rng(4).gamma(2.0, 1.0, 4000)
    out = B.run_bridge(ref.copy(), ref, np.ones(ref.shape[1]), rule, [2016], a, a * 2.0)
    assert out["model_shift"]["shifted"] and out["decision"]["passed"]
    assert out["decision"]["warnings"] and "recalibrate" in out["decision"]["warnings"][0]


def test_bridge_passes_for_a_near_copy_and_fails_for_a_bad_product():
    ref = _rain()
    rule = B.AcceptanceRule(confirmed_by_owner=True)
    rng = np.random.default_rng(3)
    good = np.clip(ref + rng.normal(0, 0.3, ref.shape), 0, None)
    yrs = [2016, 2017]
    ok = B.run_bridge(good, ref, np.ones(ref.shape[1]), rule, yrs, rng.gamma(2, 1, 3000), rng.gamma(2, 1, 3000))
    assert ok["decision"]["passed"] and ok["lag_used"] == 0 and ok["decision"]["rule_confirmed_by_owner"]
    assert ok["agreement"]["rain_mm"] == 0.5 and "2.5" in ok["agreement_reported_only"]        # 0.5 mm decides, 2.5 mm is only reported
    assert ok["agreement_reported_only"]["2.5"]["rain_mm"] == 2.5 and ok["area_mean_correlation_reported_only"] > 0.9
    bad = np.clip(ref * 0.3 + rng.gamma(1.0, 3.0, ref.shape), 0, None)
    no = B.run_bridge(bad, ref, np.ones(ref.shape[1]), rule, yrs)
    assert not no["decision"]["passed"] and no["decision"]["failures"]
    shifted = np.roll(ref, -1, axis=0)
    assert B.run_bridge(shifted, ref, np.ones(ref.shape[1]), rule, yrs)["lag_used"] == -1
    assert B.run_bridge(shifted, ref, np.ones(ref.shape[1]), rule, yrs, frozen_lag=0)["lag_used"] == 0      # a frozen lag is not searched again


def test_the_imd_binary_reader_is_not_faked():
    with pytest.raises(NotImplementedError):
        B.read_imd_merged_binary("x")
