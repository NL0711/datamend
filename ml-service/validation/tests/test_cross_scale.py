import numpy as np
import pandas as pd
import pytest

from validation.cross_scale import cross_scale_flags, monthly_clim_range, severity_per_day

DATES = pd.date_range("2001-06-01", "2001-07-31", freq="D")        # June (30 d) + July (31 d)


def _daily(value=2.0):
    return np.full(len(DATES), value)


def names(flags):
    return [f.name for f in flags]


def test_consistent_totals_raise_no_flags():
    d = _daily(2.0)                                                  # June 60 mm, July 62 mm
    flags = cross_scale_flags(d, DATES, monthly_totals={"2001-06": 60.0, "2001-07": 62.0})
    assert flags == []


def test_monthly_mismatch_flag_has_named_numeric_severity():
    d = _daily(2.0)
    flags = cross_scale_flags(d, DATES, monthly_totals={"2001-06": 120.0})   # daily sums to 60
    assert names(flags) == ["monthly_total_mismatch"]
    f = flags[0]
    assert 0 < f.severity <= 1 and f.start == 0 and f.end == 29
    assert f.detail["daily_sum"] == pytest.approx(60.0) and f.detail["provided"] == 120.0
    bigger = cross_scale_flags(d, DATES, monthly_totals={"2001-06": 600.0})[0]
    assert bigger.severity > f.severity                              # larger discrepancy -> higher severity


def test_tolerance_is_respected():
    d = _daily(2.0)
    assert cross_scale_flags(d, DATES, monthly_totals={"2001-06": 62.0}, tol_rel=0.05) == []   # 60 vs 62 within 5%
    assert names(cross_scale_flags(d, DATES, monthly_totals={"2001-06": 62.0}, tol_rel=0.0, tol_abs=0.5)) == ["monthly_total_mismatch"]


def test_pentad_mismatch_and_daily_exceeding_period_total():
    d = _daily(1.0)
    d[12] = 90.0                                                     # one huge day inside pentad index 2 (days 11-15)
    year_pent = {(2001, (pd.Timestamp("2001-06-13").dayofyear - 1) // 5): 8.0}
    flags = cross_scale_flags(d, DATES, pentad_totals=year_pent)
    assert "pentad_total_mismatch" in names(flags) and "daily_exceeds_period_total" in names(flags)
    over = [f for f in flags if f.name == "daily_exceeds_period_total"][0]
    assert over.start == over.end == 12 and over.severity == 1.0


def test_aggregate_out_of_climatological_range():
    d = _daily(2.0)                                                  # June sum 60
    flags = cross_scale_flags(d, DATES, monthly_range={6: (200.0, 900.0), 7: (10.0, 500.0)})
    assert names(flags) == ["monthly_aggregate_out_of_range"]
    assert flags[0].detail["period"] == "2001-06" and 0 < flags[0].severity <= 1
    assert cross_scale_flags(d, DATES, monthly_range={6: (10.0, 100.0)}) == []


def test_missing_days_make_a_total_unreconcilable_not_a_false_mismatch():
    d = _daily(2.0)
    d[3] = np.nan
    flags = cross_scale_flags(d, DATES, monthly_totals={"2001-06": 60.0})
    assert names(flags) == ["period_incomplete"] and flags[0].severity == pytest.approx(0.2)


def test_without_any_provided_aggregate_nothing_fires():
    assert cross_scale_flags(_daily(5.0), DATES) == []


def test_severity_per_day_and_input_validation():
    flags = cross_scale_flags(_daily(2.0), DATES, monthly_totals={"2001-06": 600.0})
    sev = severity_per_day(flags, len(DATES))
    assert sev.shape == (len(DATES),) and (sev[:30] > 0).all() and (sev[30:] == 0).all()
    with pytest.raises(ValueError):
        cross_scale_flags(np.zeros(3), DATES)


def test_monthly_range_is_built_from_the_series_it_is_given():
    years = []
    for y, level in [(2000, 1.0), (2001, 2.0), (2002, 3.0)]:
        dates = pd.date_range(f"{y}-01-01", f"{y}-12-31", freq="D")
        years.append((dates, np.full(len(dates), level)))
    rng6 = monthly_clim_range(years)[6]
    assert rng6[0] >= 30 and rng6[1] <= 90                          # June 30 d x levels {1,2,3}
    assert monthly_clim_range(years[:1]) == {}                      # one year is not enough for a range
