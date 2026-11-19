"""qc.residual: neighbour-surprise and CUSUM on synthetic fields, and the wiring on the generated QC world."""
import numpy as np
import pytest

from qc import residual as R
from qc.scoring import make_block


def _field(rows=3000, n=40, seed=0):
    """Own values share a regional rain level; the neighbour median follows it, so the tables have something to learn."""
    rng = np.random.default_rng(seed)
    wet = rng.random(rows) < 0.45
    level = np.where(wet, rng.gamma(2.0, 8.0, rows), 0.0)
    own = np.where(wet[:, None] & (rng.random((rows, n)) < 0.98), level[:, None] * rng.gamma(8.0, 1 / 8.0, (rows, n)), 0.0)
    med = np.median(own, axis=1)[:, None] + np.zeros((rows, n))
    doy = np.arange(rows) % 365
    return own.astype(np.float32), med.astype(np.float32), doy, level


@pytest.fixture(scope="module")
def ref_and_field():
    own, med, doy, level = _field()
    return R.build_reference(own, med, doy, np.random.default_rng(1)), own, med, doy, level


def test_zeroed_among_wet_neighbours_is_surprising_and_dry_among_dry_is_not(ref_and_field):
    ref, own, med, doy, level = ref_and_field
    tab = R.table_index(med, doy)
    base = R.surprise(ref, own, med, tab)
    typical_hi = float(np.nanpercentile(base[np.isfinite(base)], 95))
    heavy = np.nonzero(med[:, 0] > 20.0)[0][:50]
    z = own.copy()
    z[heavy, 3] = 0.0
    s = R.surprise(ref, z, med, tab)
    assert np.mean(s[heavy, 3] > typical_hi) > 0.9
    dry_rows = np.nonzero(med[:, 0] < 0.05)[0][:200]
    assert np.mean(base[dry_rows][own[dry_rows] < 0.1] < 1.0) > 0.9


def test_scaled_up_value_is_surprising_in_both_directions(ref_and_field):
    ref, own, med, doy, level = ref_and_field
    tab = R.table_index(med, doy)
    base = R.surprise(ref, own, med, tab)
    hi95 = float(np.nanpercentile(base, 95))
    rows = np.nonzero((med[:, 0] > 5.0) & (med[:, 0] < 20.0))[0][:60]
    up, down = own.copy(), own.copy()
    up[rows, 5] = own[rows, 5] * 10.0 + 20.0
    down[rows, 6] = 0.02
    assert np.mean(R.surprise(ref, up, med, tab)[rows, 5] > hi95) > 0.9
    assert np.mean(R.surprise(ref, down, med, tab)[rows, 6] > hi95) > 0.9


def test_cells_without_enough_neighbours_get_no_judgement():
    rng = np.random.default_rng(0)
    own = rng.gamma(1.0, 5.0, (50, 4)).astype(np.float32)
    ring = np.array([[1, -1, -1], [0, 2, -1], [0, 1, 3], [0, 1, 2]])           # cells 0 and 1 have fewer than 3 usable neighbours
    med = R.neighbour_median(own, ring)
    assert np.isnan(med[:, 0]).all() and np.isnan(med[:, 1]).all() and np.isfinite(med[:, 2]).all()
    expect = np.nanmedian(np.stack([own[:, 0], own[:, 1], own[:, 3]], axis=1), axis=1)
    assert np.allclose(med[:, 2], expect, atol=1e-6)


def test_cusum_grows_under_drift_stays_low_under_noise_and_is_causal():
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 1, (400, 3)).astype(np.float32)
    assert float(cusum_max(noise)) < 12.0
    drift = noise.copy()
    drift[:, 1] += 1.0
    c = R.cusum(drift)
    assert c[-1, 1] > 40.0 and c[-1, 0] < 12.0
    assert np.array_equal(R.cusum(drift[:150])[:, 1], c[:150, 1])                 # later days never change earlier scores


def cusum_max(d):
    return R.cusum(d).max()


def test_reference_round_trips_through_a_file(ref_and_field, tmp_path):
    ref = ref_and_field[0]
    f = tmp_path / "r.npz"
    ref.save(f, [1990, 1991])
    back = R.Reference.load(f)
    assert np.array_equal(back.n, ref.n) and np.allclose(back.mu, ref.mu) and np.allclose(back.sd, ref.sd)
    assert all(np.array_equal(a, b) for a, b in zip(back.wet, ref.wet)) and back._years == [1990, 1991]


def test_residual_scores_feed_the_ablation_and_the_ceiling_check_without_trained_models(prepared, bench):
    from qc import ceiling
    from qc.ablate import ablation_store, run_ablation
    from qc.baselines import run_untrained
    run_untrained(prepared, ("val",))
    subset = ("rules", "slow", "nbr_surprise", "drift_cusum")
    rows = run_ablation(prepared, 0, 1.0, [subset])
    assert {r["variant"] for r in rows} == {"logistic", "boosted"}
    assert all(r.get("recall") is not None for r in rows)
    name = "abl_logistic_" + "+".join(subset) + "_s0"
    assert ablation_store(prepared).has(name, "val", prepared.split.years["threshold"][0])
    out = ceiling.run_ceiling(prepared, [name], 1.0, tag="resid_test")
    assert out[name]["overall"]["n"] > 0
    from qc import paths
    assert (paths.out_dir(prepared.cfg) / str(prepared.cfg.name) / "ceiling" / "ceiling_resid_test.md").is_file()


def test_functions_on_the_generated_world_fit_on_training_years_only(prepared, bench):
    p = prepared
    fns = R.residual_functions(p)
    assert set(fns) == set(R.RESIDUAL)
    ref = R.Reference.load(R.reference_path(p))
    assert ref._years == list(p.split.years["train"])
    block = make_block(p, p.split.years["val"][0], "val", int(p.cfg.components.history_days))
    sur, drift = fns["nbr_surprise"](block), fns["drift_cusum"](block)
    for a in (sur, drift):
        assert a.shape == (block.days, p.grid.n_land)
        assert (a[np.isfinite(a)] >= 0).all()
        assert np.array_equal(np.isfinite(a), np.isfinite(block.target))              # NaN exactly where the cell's own value is missing
    assert fns["nbr_surprise"](block) is not None and np.isfinite(sur).any()
