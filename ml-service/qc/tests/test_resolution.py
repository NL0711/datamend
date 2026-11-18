"""qc.resolution on small generated arrays (no RF25 needed)."""

import numpy as np
import pytest

from qc import resolution as R
from qc.splits import LeakageError, Split

N = 6


def _split(train=(2000, 2001, 2002), val=(2003,)):
    return Split(client_map=np.zeros((1, N), np.int8), roles=np.zeros((1, N), np.int8), heldout=[], buffer_cells=0,
                 years={"train": list(train), "val": list(val), "test": [2004], "fusion_fit": list(val),
                        "threshold": list(val), "stress": []})


def _block(year, seed=0):
    rng = np.random.default_rng(seed + year)
    d = R.days_in_year(year)
    return np.where(rng.random((d, N)) < 0.4, rng.gamma(1.5, 6.0, (d, N)), 0.0).astype(np.float32)


def test_days_in_year_and_period_ids():
    assert R.days_in_year(2000) == 366 and R.days_in_year(1900) == 365 and R.days_in_year(2001) == 365
    ids = R.period_ids(2000, 366, "monthly")
    counts = np.bincount(ids, minlength=12)
    assert counts.tolist() == [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    assert R.period_ids(2001, 365, "monthly").tolist().count(1) == 28
    seas = R.period_ids(2001, 365, "seasonal")
    assert int((seas == 0).sum()) == 30 + 31 + 31 + 30
    assert R.period_ids(2001, 365, "yearly").max() == 0


def test_wrong_length_and_unknown_scale_are_refused():
    with pytest.raises(ValueError, match="refusing to align"):
        R.period_ids(2001, 366, "monthly")
    with pytest.raises(ValueError, match="unknown scale"):
        R.aggregate(_block(2001), 2001, "decadal")
    with pytest.raises(ValueError):
        R.n_periods("daily")


def test_aggregate_matches_manual_sums():
    b = _block(2001)
    m = R.aggregate(b, 2001, "monthly")
    assert m.total.shape == (12, N) and m.valid.all()
    assert np.allclose(m.total[0], b[:31].sum(axis=0), rtol=1e-5)
    assert np.allclose(m.total[1], b[31:59].sum(axis=0), rtol=1e-5)
    assert np.allclose(m.total.sum(axis=0), b.sum(axis=0), rtol=1e-5)
    assert m.n_days.tolist() == [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    y = R.aggregate(b, 2001, "yearly")
    assert np.allclose(y.total[0], b.sum(axis=0), rtol=1e-5)
    assert np.allclose(y.max_mm[0], b.max(axis=0))
    assert np.array_equal(y.wet_days[0], (b > R.WET_MM).sum(axis=0).astype(np.float32))
    s = R.aggregate(b, 2001, "seasonal")
    jun1 = 31 + 28 + 31 + 30 + 31
    assert np.allclose(s.total[0], b[jun1:jun1 + 122].sum(axis=0), rtol=1e-5)
    assert s.n_days.tolist() == [122]


def test_daily_scale_is_identity():
    b = _block(2001)
    d = R.aggregate(b, 2001, "daily")
    assert d.total.shape == b.shape and np.array_equal(d.total, b)
    assert d.n_days.tolist() == [1] * 365


def test_missing_days_are_never_filled():
    b = _block(2001)
    b[10, 0] = np.nan                      # one missing day in January, cell 0
    m = R.aggregate(b, 2001, "monthly")
    assert np.isnan(m.total[0, 0]) and not m.valid[0, 0] and m.valid[0, 1]
    assert np.isnan(m.wet_days[0, 0]) and np.isnan(m.max_mm[0, 0])
    assert m.valid[1, 0]                    # other months are fine
    lenient = R.aggregate(b, 2001, "monthly", min_valid_frac=0.9)
    assert lenient.valid[0, 0]
    assert np.isclose(lenient.total[0, 0], np.nansum(b[:31, 0]), rtol=1e-5)    # sum of the finite days, not scaled up
    allnan = np.full((365, N), np.nan, np.float32)
    assert not R.aggregate(allnan, 2001, "yearly").valid.any()


def test_labels_visible_only_when_the_total_changes():
    clean = _block(2001)
    bad = clean.copy()
    lab = np.zeros(clean.shape, bool)
    bad[40, 2] += 120.0                    # day 40 = February: a big change
    lab[40, 2] = True
    bad[200, 3] += 0.05                    # tiny change, below the tolerance
    lab[200, 3] = True
    mon = R.aggregate_labels(clean, bad, lab, 2001, "monthly")
    assert mon.present[1, 2] and mon.visible[1, 2] and mon.fault_days[1, 2] == 1
    assert mon.present.sum() == 2 and mon.visible.sum() == 1
    yr = R.aggregate_labels(clean, bad, lab, 2001, "yearly")
    assert yr.visible[0, 2] and yr.present[0, 3] and not yr.visible[0, 3]
    daily = R.aggregate_labels(clean, bad, lab, 2001, "daily")
    assert daily.visible[40, 2]
    with pytest.raises(ValueError):
        R.aggregate_labels(clean, bad, lab[:-1], 2001, "monthly")


def test_scale_stats_use_training_years_only_and_describe_the_climatology():
    split = _split()
    years = [2000, 2001, 2002]
    pby = {y: R.aggregate(_block(y), y, "monthly") for y in years + [2003]}
    cc = np.zeros(N, int) + 1
    st = R.fit_scale_stats(pby, years, split, cc, "monthly")
    stack = np.stack([pby[y].total for y in years])
    assert np.allclose(st.clim_mean, stack.mean(axis=0), rtol=1e-5)
    assert (st.clim_spread > 0).all() and np.isfinite(st.clim_spread).all()
    assert st.norm_scale.shape == (N,) and (st.norm_scale > 0).all()
    z = st.zscore(pby[2001])
    assert z.shape == (12, N) and np.isfinite(z).all()
    with pytest.raises(LeakageError):
        R.fit_scale_stats(pby, years + [2003], split, cc, "monthly")
    with pytest.raises(ValueError, match="stats are for scale"):
        st.zscore(R.aggregate(_block(2001), 2001, "yearly"))
    with pytest.raises(ValueError, match="daily"):
        R.fit_scale_stats(pby, years, split, cc, "daily")


def test_scale_stats_per_client_normalisation_and_roundtrip(tmp_path):
    split = _split()
    years = [2000, 2001, 2002]
    pby = {y: R.aggregate(_block(y), y, "yearly") for y in years}
    cc = np.array([1, 1, 1, 2, 2, 2])
    pby[2000].total[0, 3:] *= 5.0          # make client 2 much wetter in one year
    st = R.fit_scale_stats(pby, years, split, cc, "yearly")
    assert st.norm_scale[0] == st.norm_scale[1] and st.norm_scale[3] == st.norm_scale[5]
    assert st.norm_scale[3] != st.norm_scale[0]
    st.save(tmp_path / "s.npz")
    back = R.ScaleStats.load(tmp_path / "s.npz")
    assert back.scale == "yearly" and back.years == st.years
    assert np.array_equal(back.clim_mean, st.clim_mean) and np.array_equal(back.norm_scale, st.norm_scale)
    assert np.all(st.normalize(np.array([0.0, 100.0, -5.0])[:, None] + np.zeros((3, N))) >= 0)


def test_corrupt_periods_labels_only_real_changes_and_does_not_mutate():
    p = R.aggregate(_block(2001), 2001, "monthly")
    p.total[3, 0] = 0.0                    # an already dry period
    p.wet_days[3, 0] = 0.0
    p.max_mm[3, 0] = 0.0
    before = p.total.copy()
    out, f = R.corrupt_periods(p, np.random.default_rng(1), rate=1.0, kinds=("dropout",))
    assert np.array_equal(p.total, before)                         # input untouched
    assert (out.total[f.labels] != p.total[f.labels]).all()
    assert not f.labels[3, 0]                                      # dropping a dry period changes nothing: not a fault
    assert (out.total[p.valid] == 0).all()
    assert (out.wet_days[p.valid] == 0).all()
    assert (f.factor[f.labels] == 0).all()
    out2, f2 = R.corrupt_periods(p, np.random.default_rng(2), rate=0.5, kinds=("scale",))
    ratio = out2.total[f2.labels] / p.total[f2.labels]
    assert np.allclose(ratio, f2.factor[f2.labels], rtol=1e-4)
    assert ((ratio >= 0.4 - 1e-6) & (ratio <= 0.8 + 1e-6) | (ratio >= 1.25 - 1e-6) & (ratio <= 2.5 + 1e-6)).all()
    a, fa = R.corrupt_periods(p, np.random.default_rng(7), rate=0.3)
    b, fb = R.corrupt_periods(p, np.random.default_rng(7), rate=0.3)
    assert np.array_equal(fa.labels, fb.labels) and np.array_equal(a.total, b.total, equal_nan=True)
    none, fn = R.corrupt_periods(p, np.random.default_rng(3), rate=0.0)
    assert not fn.labels.any() and np.array_equal(none.total, p.total, equal_nan=True)
    with pytest.raises(ValueError):
        R.corrupt_periods(p, np.random.default_rng(0), kinds=("spike",))


def test_invalid_periods_are_never_corrupted():
    b = _block(2001)
    b[:, 1] = np.nan
    p = R.aggregate(b, 2001, "yearly")
    _, f = R.corrupt_periods(p, np.random.default_rng(0), rate=1.0)
    assert not f.labels[:, 1].any()


def test_yearly_to_decades():
    years = list(range(1990, 2011))        # 1990-1999 (10 years), 2000-2009 (10), 2010 (1)
    tot = np.arange(len(years), dtype=np.float32)[:, None] + np.zeros((len(years), 3), np.float32)
    tot[5, 1] = np.nan                     # one missing year in the 1990s for cell 1
    starts, means = R.yearly_to_decades(years, tot, min_years=10)
    assert starts.tolist() == [1990, 2000, 2010]
    assert np.isclose(means[0, 0], np.mean(np.arange(10)))
    assert np.isnan(means[0, 1])           # only 9 finite years: not interpolated
    assert np.isclose(means[1, 2], np.mean(np.arange(10, 20)))
    assert np.isnan(means[2]).all()        # a single year is not a decade
    _, lenient = R.yearly_to_decades(years, tot, min_years=9)
    assert np.isfinite(lenient[0, 1])
    with pytest.raises(ValueError):
        R.yearly_to_decades(years, tot[:-1])
