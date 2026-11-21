"""qc.changepoint on generated series (no RF25 needed)."""

import numpy as np
import pytest

from qc import changepoint as C

N_YEARS = 40


def test_snht_and_pettitt_find_a_step_and_its_year():
    rng = np.random.default_rng(0)
    z = rng.normal(size=N_YEARS)
    z[22:] += 2.5
    for f in (C.snht, C.pettitt):
        stat, k = f(z)
        assert stat > 0 and abs(k - 22) <= 2
    flat = rng.normal(size=N_YEARS)
    assert C.snht(flat)[0] < C.snht(z)[0] and C.pettitt(flat)[0] < C.pettitt(z)[0]


def test_degenerate_series_do_not_break_the_statistics():
    assert C.snht(np.ones(30)) == (0.0, None)
    assert C.snht(np.ones(3)) == (0.0, None)
    assert C.pettitt(np.ones(2)) == (0.0, None)


def test_critical_value_controls_the_false_alarm_rate_on_break_free_series():
    crit = C.simulated_critical("snht", N_YEARS, alpha=0.05, n_sim=3000, rng=np.random.default_rng(1))
    rng = np.random.default_rng(2)
    rate = np.mean([C.snht(rng.normal(size=N_YEARS))[0] > crit for _ in range(2000)])
    assert 0.02 < rate < 0.09                                       # near the nominal 5% on fresh series
    assert C.simulated_critical("pettitt", N_YEARS, 0.05, 500, np.random.default_rng(3)) > 0
    with pytest.raises(ValueError, match="at least"):
        C.simulated_critical("snht", 10)
    with pytest.raises(ValueError):
        C.simulated_critical("snht", N_YEARS, alpha=0.7)
    with pytest.raises(ValueError):
        C.simulated_critical("nope", N_YEARS)


def test_step_power_rises_with_the_step_size():
    p = C.step_power(N_YEARS, (0.0, 1.0, 3.0), "snht", alpha=0.05, n_sim=300, rng=np.random.default_rng(4))
    assert p[0.0] < 0.12 and p[3.0] > 0.9 and p[0.0] <= p[1.0] <= p[3.0]


def test_neighbour_difference_removes_a_shared_signal_and_keeps_a_local_step():
    rng = np.random.default_rng(5)
    Y, n, K = 30, 12, 6
    shared = rng.normal(0, 0.3, (Y, 1))
    an = shared + rng.normal(0, 0.05, (Y, n))
    an[15:, 0] += 1.0                                              # a local step in cell 0 only
    idx = np.array([[(i + k + 1) % n for k in range(K)] for i in range(n)])
    idx[3, :] = -1                                                 # cell 3 has no neighbours
    d = C.neighbour_difference(an.astype(np.float32), idx)
    assert np.isnan(d[:, 3]).all()
    assert abs(d[:, 5].mean()) < 0.1 and d[15:, 0].mean() - d[:15, 0].mean() > 0.8
    assert d[:, 5].std() < an[:, 5].std() + 0.01 and d[:, 5].std() < 0.15                   # the shared year effect is gone


def test_detect_breaks_flags_the_stepped_cell_only_and_skips_cells_with_gaps():
    rng = np.random.default_rng(6)
    Y, n = N_YEARS, 20
    z = rng.normal(0, 1, (Y, n))
    z[20:, 4] += 3.0
    z[7, 9] = np.nan                                               # a missing year: not filled, not tested
    years = list(range(1960, 1960 + Y))
    out = C.detect_breaks(z, years, "snht", alpha=0.001, rng=np.random.default_rng(7))
    assert out["flagged"][4] and abs(out["break_year"][4] - 1980) <= 2 and out["shift"][4] > 2.0
    assert not out["tested"][9] and not out["flagged"][9]
    assert out["flagged"].sum() <= 2 and "not distinguishable" in out["meaning"]
    fixed = C.detect_breaks(z, years, "pettitt", critical=1e9)
    assert not fixed["flagged"].any() and fixed["critical"] == 1e9
    with pytest.raises(ValueError):
        C.detect_breaks(z, years[:-1])
