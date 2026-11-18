"""qc.period_benchmark: the pure step on small arrays, and the file build on the generated QC world."""

import numpy as np
import pytest

from qc import period_benchmark as PB
from qc.grid import ContractError

N = 8
YEAR = 2001


def _arrays(seed=0):
    rng = np.random.default_rng(seed)
    clean = np.where(rng.random((365, N)) < 0.4, rng.gamma(1.5, 6.0, (365, N)), 0.0).astype(np.float32)
    bad = clean.copy()
    lab = np.zeros(clean.shape, bool)
    bad[40, 2] += 150.0                      # a big daily fault in February, cell 2
    lab[40, 2] = True
    bad[200, 3] += 0.01                      # a change too small to show at a coarser scale
    lab[200, 3] = True
    return clean, bad, lab


def test_daily_fault_is_visible_at_coarser_scales_only_when_it_moves_the_total():
    clean, bad, lab = _arrays()
    none = np.zeros(clean.shape, bool)
    for scale in ("monthly", "yearly"):
        py = PB.make_period_year(clean, bad, lab, none, none, YEAR, scale, np.random.default_rng(1), rate=0.0)
        assert py.from_daily.sum() == 1 and py.fault.sum() == 1
    py = PB.make_period_year(clean, bad, lab, none, none, YEAR, "monthly", np.random.default_rng(1), rate=0.0)
    assert py.fault[1, 2] and not py.fault[:, 3].any()
    seasonal = PB.make_period_year(clean, bad, lab, none, none, YEAR, "seasonal", np.random.default_rng(1), rate=0.0)
    assert not seasonal.fault.any()           # a February fault is outside the June-September season


def test_period_level_faults_are_added_labelled_and_never_on_protected_periods():
    clean, _, _ = _arrays()
    none = np.zeros(clean.shape, bool)
    prot = np.zeros(clean.shape, bool)
    prot[170:180, :] = True                   # June holds a protected extreme in every cell
    py = PB.make_period_year(clean, clean.copy(), none, prot, none, YEAR, "monthly", np.random.default_rng(5), rate=0.6)
    assert py.fault.any() and (py.period_kind[py.fault] >= 0).all() and not py.from_daily.any()
    june = 5
    assert py.protected[june].all() and not py.fault[june].any()
    assert np.array_equal(py.corrupted.total[june], py.clean.total[june])       # untouched
    changed = np.abs(py.corrupted.total - py.clean.total) > 1e-6
    assert np.array_equal(changed & py.valid, py.fault & py.valid)               # labelled exactly where the total moved
    again = PB.make_period_year(clean, clean.copy(), none, prot, none, YEAR, "monthly", np.random.default_rng(5), rate=0.6)
    assert np.array_equal(again.fault, py.fault)                                 # reproducible


def test_clean_mask_excludes_faults_protected_and_ambiguous():
    clean, bad, lab = _arrays()
    amb = np.zeros(clean.shape, bool)
    amb[100, 5] = True
    prot = np.zeros(clean.shape, bool)
    prot[10, 6] = True
    py = PB.make_period_year(clean, bad, lab, prot, amb, YEAR, "monthly", np.random.default_rng(0), rate=0.0)
    cm = py.clean_mask
    assert not cm[1, 2] and not cm[3, 5] and not cm[0, 6] and cm[0, 0]


def test_bad_scale_is_refused():
    clean, bad, lab = _arrays()
    with pytest.raises(ValueError):
        PB.make_period_year(clean, bad, lab, lab, lab, YEAR, "daily", np.random.default_rng(0))


def test_save_and_load_round_trip(tmp_path):
    clean, bad, lab = _arrays()
    none = np.zeros(clean.shape, bool)
    py = PB.make_period_year(clean, bad, lab, none, none, YEAR, "monthly", np.random.default_rng(2), rate=0.2)
    PB.save_period_year(tmp_path, "val", py)
    back = PB.load_period_year(tmp_path, "monthly", "val", YEAR)
    for a in ("fault", "from_daily", "period_kind", "protected", "ambiguous", "valid"):
        assert np.array_equal(getattr(back, a), getattr(py, a))
    assert np.allclose(back.corrupted.total, py.corrupted.total, equal_nan=True)
    assert np.allclose(back.clean.total, py.clean.total, equal_nan=True)


def test_splits_can_be_added_later_without_touching_the_ones_built(prepared, bench):
    first = PB.build_period_benchmark(prepared, splits=("val",), overwrite=True)
    assert first["splits"] == ["val"] and set(first["split_hashes"]) == {"val"}
    both = PB.build_period_benchmark(prepared, splits=("test",))                 # added without overwrite
    assert both["splits"] == ["test", "val"] and both["split_hashes"]["val"] == first["split_hashes"]["val"]
    assert both["hash"] != first["hash"] and set(both["summary"]) == {f"{s}/{c}" for s in ("val", "test") for c in PB.SCALES}
    with pytest.raises(FileExistsError, match="already holds"):
        PB.build_period_benchmark(prepared, splits=("test",))
    with pytest.raises(ValueError, match="other settings"):
        PB.build_period_benchmark(prepared, splits=("stress",), rate=0.5)
    full = PB.build_period_benchmark(prepared, splits=("val", "test"), overwrite=True)
    assert full["hash"] == both["hash"]                                           # the same content gives the same hash either way


def test_build_on_the_generated_world(prepared, bench, tmp_path):
    m = PB.build_period_benchmark(prepared, splits=("val", "test"), overwrite=True)
    assert m["daily_benchmark_hash"] and len(m["hash"]) == 16
    assert set(m["summary"]) == {f"{s}/{c}" for s in ("val", "test") for c in PB.SCALES}
    assert all(v["fault_periods"] > 0 for v in m["summary"].values())
    from qc.benchmark import bench_dir
    root = PB.period_dir(bench_dir(prepared.cfg))
    py = PB.load_period_year(root, "monthly", "val", prepared.split.years["val"][0])
    assert py.fault.any() and py.clean_mask.any()
    again = PB.build_period_benchmark(prepared, splits=("val", "test"), overwrite=True)
    assert again["hash"] == m["hash"]                                           # deterministic
    with pytest.raises(FileExistsError):
        PB.build_period_benchmark(prepared, splits=("val", "test"))
    assert PB.check_period_benchmark(prepared)["hash"] == m["hash"]
    with pytest.raises(ContractError, match="refusing to score"):
        PB.check_period_benchmark(prepared, expected_hash="0000000000000000")
