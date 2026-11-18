"""Whole-year bootstrap intervals (qc.metrics.year_bootstrap_ci) on small arrays."""

import numpy as np
import pytest

from qc.metrics import MIN_YEARS_FOR_CI, year_bootstrap_ci


def test_too_few_years_gives_no_interval():
    rng = np.random.default_rng(0)
    n = np.full(MIN_YEARS_FOR_CI - 1, 100.0)
    assert year_bootstrap_ci(n * 0.5, n, rng, 200) is None
    assert year_bootstrap_ci(n * 0.5, n, rng, 200, min_years=2) is not None


def test_zero_resamples_gives_none_and_mismatch_raises():
    rng = np.random.default_rng(0)
    n = np.full(8, 100.0)
    assert year_bootstrap_ci(n * 0.5, n, rng, 0) is None
    with pytest.raises(ValueError):
        year_bootstrap_ci(n[:7], n, rng, 100)


def test_interval_contains_the_estimate_and_is_reproducible():
    n = np.full(8, 200.0)
    k = np.array([150, 120, 160, 100, 140, 155, 130, 145], float)
    a = year_bootstrap_ci(k, n, np.random.default_rng(3), 400)
    b = year_bootstrap_ci(k, n, np.random.default_rng(3), 400)
    assert a == b and a[0] <= k.sum() / n.sum() <= a[1] and a[0] < a[1]


def test_year_effects_widen_the_interval_over_independent_events():
    n = np.full(8, 1000.0)
    flat = np.full(8, 500.0)
    varying = np.array([300, 700, 350, 650, 400, 600, 320, 680], float)      # same mean 500, strong year effect
    w_flat = np.diff(year_bootstrap_ci(flat, n, np.random.default_rng(1), 500))[0]
    w_var = np.diff(year_bootstrap_ci(varying, n, np.random.default_rng(1), 500))[0]
    assert w_flat < 1e-9                                                     # no year-to-year spread, no interval width
    iid_half = 1.96 * np.sqrt(0.25 / n.sum())                                # width an event-level bootstrap would report
    assert w_var > 5 * 2 * iid_half


def test_years_with_no_events_do_not_break_it():
    rng = np.random.default_rng(2)
    num = np.array([0, 5, 0, 8, 6, 7], float)
    den = np.array([0, 10, 0, 10, 10, 10], float)
    ci = year_bootstrap_ci(num, den, rng, 300)
    assert ci is not None and 0 <= ci[0] <= ci[1] <= 1
