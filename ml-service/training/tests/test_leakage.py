"""Leakage tests: these fail if any fitted statistic uses validation/test years or future data."""

import numpy as np
import pytest
import xarray as xr

from ensemble.branches import RuleBranch, StatBranch
from ensemble.pipeline import FusionConfig, FusionPipeline
from training.leakage import ALLOWED_SPLIT, LeakageError, assert_no_leakage
from training.pipeline import make_sampler, prepare
from training.presets import make_config
from training.splits import YearSplit

YEARS = [2000, 2001, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010]   # 2002 missing
# with val_years=2, test_years=2 -> train 2000-2006 (6), val 2007-2008, test 2009-2010


def _write(path, year, scale, rng, days=60):
    rain = (rng.gamma(0.3, 8.0, size=(days, 8, 9)) * scale).astype("float32")
    rain[rng.random(rain.shape) < 0.6] = 0.0
    rain[:, :2] = np.nan
    xr.Dataset({"RAINFALL": (("TIME", "LATITUDE", "LONGITUDE"), rain)},
               coords={"TIME": np.datetime64(f"{year}-01-01") + np.arange(days),
                       "LATITUDE": np.linspace(7, 12, 8), "LONGITUDE": np.linspace(70, 75, 9)}
               ).to_netcdf(path, engine="scipy")


def _archive(root, scale_for):
    root.mkdir()
    for y in YEARS:
        _write(root / f"RF25_ind{y}_rfp25.nc", y, scale_for(y), np.random.default_rng(y))   # per-year RNG: same base data
    return root


@pytest.fixture()
def base(tmp_path):
    return prepare(_archive(tmp_path / "base", lambda y: 1.0), 2, 2, build_stat=True, log=lambda *_: None)


def test_split_is_what_we_think(base):
    assert base.split.train == [2000, 2001, 2003, 2004, 2005, 2006]
    assert base.split.val == [2007, 2008] and base.split.test == [2009, 2010]


def test_fitted_statistics_ignore_val_and_test_years(base, tmp_path):
    other = prepare(_archive(tmp_path / "wild", lambda y: 1.0 if y <= 2006 else 50.0), 2, 2, build_stat=True,
                    log=lambda *_: None)
    np.testing.assert_array_equal(base.clim, other.clim)                      # climatology: train only
    assert base.transform.scale == other.transform.scale                       # normalization: train only
    np.testing.assert_array_equal(base.stat_baseline.bound, other.stat_baseline.bound)  # stat baseline: train only
    assert base.stat_baseline.years == base.split.train


def test_fitted_statistics_do_change_when_train_years_change(base, tmp_path):
    other = prepare(_archive(tmp_path / "train_changed", lambda y: 3.0 if y <= 2006 else 1.0), 2, 2, build_stat=True,
                    log=lambda *_: None)
    assert not np.allclose(base.clim[:60], other.clim[:60], equal_nan=True)    # the check is not vacuous
    assert base.transform.scale != other.transform.scale
    assert not np.array_equal(base.stat_baseline.bound, other.stat_baseline.bound)


def test_provenance_guard_catches_val_test_and_unknown():
    split = YearSplit(train=[1, 2, 3], val=[4], test=[5])
    assert_no_leakage({"climatology": [1, 2], "threshold": [4], "stat_baseline": None}, split)
    with pytest.raises(LeakageError):
        assert_no_leakage({"climatology": [1, 4]}, split)           # validation year in a train-only statistic
    with pytest.raises(LeakageError):
        assert_no_leakage({"transform": [5]}, split)                # test year
    with pytest.raises(LeakageError):
        assert_no_leakage({"threshold": [1]}, split)                # threshold must come from validation years
    with pytest.raises(LeakageError):
        assert_no_leakage({"threshold": [4, 5]}, split)
    with pytest.raises(LeakageError):
        assert_no_leakage({"brand_new_statistic": [1]}, split)      # new statistics cannot skip the check
    assert set(ALLOWED_SPLIT.values()) == {"train", "val"}           # nothing is ever allowed to fit on test


def test_prepare_records_train_only_provenance(base):
    assert set(base.provenance) == {"transform", "climatology", "stat_baseline"}
    assert_no_leakage(base.provenance, base.split)


def test_rank_reference_ignores_val_and_test_year_data(base, tmp_path):
    """Normalizers fit on clean TRAIN-year windows must not move when val/test data change."""
    other = prepare(_archive(tmp_path / "wild2", lambda y: 1.0 if y <= 2006 else 50.0), 2, 2, build_stat=True,
                    log=lambda *_: None)
    cfg = make_config("smoke")

    def fit(prep):
        pipe = FusionPipeline([RuleBranch(), StatBranch(prep.stat_baseline)], FusionConfig())
        s = make_sampler(prep, cfg, prep.split.train, seed=5)
        pipe.fit_normalizers([s.batch(64, 0.0) for _ in range(2)])
        return pipe

    a, b = fit(base), fit(other)
    for k in a.rank:
        np.testing.assert_array_equal(a.rank[k].ref, b.rank[k].ref)


def test_threshold_uses_validation_years_only(base, tmp_path):
    other = prepare(_archive(tmp_path / "wild3", lambda y: 1.0 if y <= 2008 else 50.0), 2, 2, build_stat=True,
                    log=lambda *_: None)   # only TEST years differ
    cfg = make_config("smoke")

    def thr(prep):
        pipe = FusionPipeline([RuleBranch(), StatBranch(prep.stat_baseline)], FusionConfig())
        pipe.fit_normalizers([make_sampler(prep, cfg, prep.split.train, 1).batch(64, 0.0)])
        pipe.fit_threshold([make_sampler(prep, cfg, prep.split.val, 2).batch(64, 0.0) for _ in range(2)])
        return pipe.threshold_info["threshold"]

    assert thr(base) == thr(other)


def test_calibration_batches_must_be_clean(base):
    pipe = FusionPipeline([RuleBranch()], FusionConfig())
    s = make_sampler(base, make_config("smoke"), base.split.train, 3)
    with pytest.raises(ValueError):
        pipe.fit_normalizers([s.batch(64, 1.0)])
    pipe.fit_normalizers([s.batch(64, 0.0)])
    with pytest.raises(ValueError):
        pipe.fit_threshold([s.batch(64, 1.0)])
