"""The faster paths in `prepare` give exactly the same numbers as the slow ones."""

import numpy as np
import pytest

from ensemble.statbaseline import nanquantile0
from qc.grid import ContractError, check_contract


@pytest.mark.parametrize("shape", [(120, 50, 1), (90, 7, 5)])
def test_fast_quantile_equals_nanquantile_exactly(shape):
    rng = np.random.default_rng(0)
    x = rng.gamma(0.5, 8.0, shape).astype(np.float32)
    x[rng.random(shape) < 0.3] = 0.0
    x[3, 0, 0] = np.nan                                           # a column with a NaN takes the slow path
    x[:, 1, 0] = np.nan                                           # a column of NaN only
    x[10:50, 2, 0] = np.nan                                       # partly missing
    for q in (0.5, 0.99, 0.995):
        fast, slow = nanquantile0(x, q), np.nanquantile(x, q, axis=0)
        assert fast.dtype == slow.dtype and fast.shape == slow.shape
        assert np.array_equal(fast, slow, equal_nan=True)
    assert np.array_equal(nanquantile0(np.full((5, 3, 1), np.nan, np.float32), 0.9), np.full((3, 1), np.nan, np.float32), equal_nan=True)


def test_threaded_contract_check_matches_the_serial_one_and_reports_the_first_bad_year(world, cfg):
    from qc.prepare import all_years
    from qc import paths
    years = all_years(cfg)
    d = paths.rf25_dir(cfg)
    serial = check_contract(d, years, cfg.grid, workers=1)
    threaded = check_contract(d, years, cfg.grid, workers=4)
    for k in ("years", "days", "missing_on_land", "land_cells"):
        assert serial[k] == threaded[k]
    assert np.array_equal(serial["land"], threaded["land"]) and np.array_equal(serial["lat"], threaded["lat"])
    with pytest.raises(ContractError, match="missing"):
        check_contract(d, years + [2150], cfg.grid, workers=4)


def test_shared_block_scoring_writes_the_same_scores_and_leaves_the_block_untouched(world, cfg, prepared):
    from qc.baselines import score_functions
    from qc.benchmark import build_benchmark
    from qc.evaluate import compute_scores, compute_scores_many
    from qc.scoring import ScoreStore, make_block

    build_benchmark(prepared, splits=("val",), overwrite=True)
    fns = score_functions(prepared)
    a, b = ScoreStore(world / "scores_a"), ScoreStore(world / "scores_b")
    for name, fn in fns.items():
        compute_scores(prepared, name, fn, ("val",), a)
    compute_scores_many(prepared, fns, ("val",), b)
    years = [("val", y) for y in prepared.split.years["val"]] + [("clean", y) for y in prepared.split.years["threshold"]]
    for name in fns:
        for tag, y in years:
            assert np.array_equal(a.load(name, tag, y), b.load(name, tag, y), equal_nan=True), (name, tag, y)
    y0 = prepared.split.years["val"][0]
    blk = make_block(prepared, y0, "val", int(prepared.cfg.components.history_days))
    before = blk.obs.copy()
    for fn in fns.values():
        fn(blk)
    assert np.array_equal(before, blk.obs, equal_nan=True)                          # scorers do not modify the shared block
    mtime = b.path("rules", "val", y0).stat().st_mtime_ns
    compute_scores_many(prepared, fns, ("val",), b)                                   # existing files are skipped
    assert b.path("rules", "val", y0).stat().st_mtime_ns == mtime
