"""Unit tests of the temperature, pressure and humidity checks (validation/weather_checks.py) and of how the stream scoring uses them.
All data is generated here (a seeded smooth series); nothing is measured data and no network or database is used."""
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from backend.app.stream.scoring import NO_CHECKS, climate_sample, score_reading
from backend.app.stream.types import StreamReading
from backend.app.validation import checks as cat
from backend.app.validation import weather_checks as wc
from backend.app.validation.weather_checks import ClimateHistory, ClimateSample, dew_point_c, run_weather_checks

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def series(n=120, step_s=60.0, t=22.0, p=990.0, rh=55.0, seed=0, start=T0):
    """A clean, slowly varying synthetic series of n readings, oldest first, with small noise."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        out.append(ClimateSample(start + timedelta(seconds=i * step_s), round(t + 0.002 * i + float(rng.normal(0, 0.15)), 2),
                                 round(p - 0.001 * i + float(rng.normal(0, 0.1)), 2), round(rh - 0.003 * i + float(rng.normal(0, 0.5)), 2)))
    return out


def after(hist, seconds=60.0):
    return hist[-1].timestamp + timedelta(seconds=seconds)


def names(res):
    return {h.check for h in res.hits}


def run(hist, t=None, p=None, rh=None, seconds=60.0):
    return run_weather_checks({"temperature": t, "pressure": p, "humidity": rh}, after(hist, seconds), hist)


def next_values(hist):
    last = hist[-1]
    return last.temperature, last.pressure, last.humidity


def verdict(res):
    return cat._verdict(res.hits, not res.has_data)


# ---------------------------------------------------------------------------------------------------- catalogue
def test_checks_are_registered_in_the_catalogue_with_needs_kind_and_weight():
    new = {s.name for s in wc.CATALOGUE_SPECS}
    assert new <= set(cat.CATALOGUE)
    for name in new:
        spec = cat.CATALOGUE[name]
        assert spec.needs and spec.kind in ("fault", "uncertain", "info") and 0 < spec.weight <= 1 and spec.profile == "stream"
    assert {"negative_value", "frozen_intensity", "climatology_upper_tail"} <= set(cat.CATALOGUE)       # rainfall checks are untouched
    assert cat.CATALOGUE["extreme_value"].kind == "uncertain" and cat.CATALOGUE["rate_of_change"].kind == "uncertain"


def test_every_threshold_in_the_evidence_is_tagged_assumed_and_every_number_has_a_basis():
    hist = series()
    t, p, rh = next_values(hist)
    res = run(hist, t + 30, p, rh)
    assert res.hits
    for h in res.hits:
        assert h.evidence["threshold"]["basis"] == "assumed"
        assert h.evidence["observed"]["basis"] in ("measured", "assumed", "derived")
        assert h.evidence["profile"] == "stream" and h.evidence["variable"]
    dp = run(series(), 40.0, 990.0, 105.0)       # derived values say so
    assert any(h.check == "dewpoint_above_temperature" and h.evidence["dew_point"]["basis"] == "derived" for h in dp.hits)


# ---------------------------------------------------------------------------------------------------- a clean reading
def test_a_clean_series_raises_nothing_and_every_check_ran():
    hist = series()
    t, p, rh = next_values(hist)
    res = run(hist, t + 0.1, p - 0.05, rh + 0.2)
    assert res.hits == [] and res.not_run == [] and verdict(res) == "OK"


# ---------------------------------------------------------------------------------------------------- physical bounds
@pytest.mark.parametrize("v,x,expect", [
    ("temperature", 60.0, False), ("temperature", 60.1, True), ("temperature", -90.0, False), ("temperature", -90.5, True),
    ("pressure", 300.0, False), ("pressure", 299.9, True), ("pressure", 1100.0, False), ("pressure", 1100.5, True),
    ("humidity", 0.0, False), ("humidity", -0.1, True), ("humidity", 100.5, False), ("humidity", 105.0, False), ("humidity", 105.5, True)])
def test_physical_bounds_edges(v, x, expect):
    res = run_weather_checks({v: x}, T0)                    # no history needed
    assert ("value_out_of_range" in names(res)) is expect
    if expect:
        assert verdict(res) == "SUSPECT" and res.hits[0].evidence["observed"]["value"] == x


@pytest.mark.parametrize("bad", [9999.9, -999.0, float("nan"), float("inf")])
def test_corrupt_values_are_faults_and_not_counted_twice_as_out_of_range(bad):
    res = run_weather_checks({"temperature": bad}, T0)
    assert names(res) == {"corrupt_value"} and verdict(res) == "SUSPECT"


def test_an_extreme_temperature_without_corroboration_is_uncertain_never_a_fault():
    res = run_weather_checks({"temperature": 55.0}, T0)                     # in range, rare, nothing else says anything
    assert names(res) == {"extreme_value"} and verdict(res) == "UNCERTAIN"
    assert "not a fault" in res.hits[0].reason
    assert verdict(run_weather_checks({"temperature": -45.0}, T0)) == "OK"


def test_pressure_has_no_absolute_extreme_band_because_the_station_elevation_is_unknown():
    for p in (560.0, 850.0, 1075.0):                                        # a mountain station and a deep low are both inside the limits
        assert verdict(run_weather_checks({"pressure": p}, T0)) == "OK"


# ---------------------------------------------------------------------------------------------------- rate of change
def test_rate_of_change_edge_and_cadence_awareness():
    hist = series(30)
    t, p, rh = next_values(hist)
    limit = wc.RATE_FLOOR["temperature"] + wc.RATE_PER_MIN["temperature"] * 1.0
    assert "rate_of_change" not in names(run(hist, t + limit - 0.05, p, rh))
    hit = run(hist, t + limit + 0.2, p, rh)
    assert "rate_of_change" in names(hit)
    h = next(x for x in hit.hits if x.check == "rate_of_change")
    assert h.kind == "uncertain" and h.evidence["elapsed"]["basis"] == "derived" and h.evidence["change"]["basis"] == "derived"
    # the same change over half an hour is not fast (cadence-aware): the check allows more
    slow = run_weather_checks({"temperature": t + limit + 0.2, "pressure": p, "humidity": rh}, hist[-1].timestamp + timedelta(minutes=30), hist)
    assert "rate_of_change" not in names(slow)


def test_a_fast_change_alone_is_uncertain_not_suspect():
    hist = [ClimateSample(s.timestamp, s.temperature, None, None) for s in series(5)]    # short, temperature only: only the rate check can speak
    res = run(hist, hist[-1].temperature + 6.0)
    assert names(res) == {"rate_of_change"} and verdict(res) == "UNCERTAIN"


# ---------------------------------------------------------------------------------------------------- frozen
def test_frozen_needs_eight_identical_readings_over_two_minutes():
    hist = series(40, step_s=60.0)
    last = hist[-1]
    for k in range(1, 7):                                                   # 7 identical readings in total (6 priors + this one): not yet
        hist.append(ClimateSample(after(hist), last.temperature, hist[-1].pressure, hist[-1].humidity))
    res = run_weather_checks({"temperature": last.temperature}, after(hist), hist)
    assert "frozen_value" in names(res)                                     # 8 in a row now (the original + 6 appended + this one)
    hist2 = hist[:-1]
    assert "frozen_value" not in names(run_weather_checks({"temperature": last.temperature}, after(hist2), hist2))     # only 7
    h = next(x for x in res.hits if x.check == "frozen_value")
    assert h.kind == "fault" and verdict(res) == "SUSPECT" and h.evidence["observed"]["value"] == last.temperature


def test_frozen_at_a_fast_cadence_waits_for_the_time_span_and_says_why():
    hist = series(40, step_s=5.0)
    v = hist[-1].temperature
    for _ in range(9):
        hist.append(ClimateSample(after(hist, 5.0), v, None, None))
    res = run_weather_checks({"temperature": v}, after(hist, 5.0), hist)
    assert "frozen_value" not in names(res)
    assert any(n["check"] == "frozen_value" and "span only" in n["reason"] for n in res.not_run)
    for _ in range(30):
        hist.append(ClimateSample(after(hist, 5.0), v, None, None))
    assert "frozen_value" in names(run_weather_checks({"temperature": v}, after(hist, 5.0), hist))


def test_saturated_humidity_is_not_called_frozen():
    hist = [ClimateSample(T0 + timedelta(minutes=i), 12.0 + 0.01 * i, 1000.0 + 0.01 * i, 100.0) for i in range(30)]
    res = run_weather_checks({"humidity": 100.0}, after(hist), hist)
    assert "frozen_value" not in names(res) and any("saturation" in n["reason"] for n in res.not_run)


# ---------------------------------------------------------------------------------------------------- spike, genuine extreme versus fault
def test_isolated_spike_is_a_fault_when_history_exists_and_not_run_when_it_does_not():
    hist = series(60)
    t, p, rh = next_values(hist)
    res = run(hist, t, p + 12.0, rh)
    assert "spike_vs_history" in names(res) and verdict(res) == "SUSPECT"
    spike = next(h for h in res.hits if h.check == "spike_vs_history")
    assert spike.evidence["corroboration"]["coherent"] is False
    assert "nothing else moves with it" in spike.reason and "genuine-extreme" not in spike.reason
    short = series(6)
    res = run(short, short[-1].temperature, short[-1].pressure + 12.0, short[-1].humidity)
    assert "spike_vs_history" not in names(res)
    assert any(n["check"] == "spike_vs_history" and "needed" in n["reason"] for n in res.not_run)


def _rh_for_dew_point(t, dp):
    return 100.0 * math.exp(wc.MAGNUS_B * dp / (wc.MAGNUS_C + dp) - wc.MAGNUS_B * t / (wc.MAGNUS_C + t))


def test_a_squall_front_is_a_genuine_extreme_candidate_uncertain_not_a_fault():
    hist = series(60, t=25.0, rh=50.0)
    t, p, rh = next_values(hist)
    dp = dew_point_c(t, rh)
    res = run(hist, t - 8.0, p - 14.0, _rh_for_dew_point(t - 8.0, dp))      # temperature and pressure fall, humidity rises, the dew point holds
    spikes = [h for h in res.hits if h.check == "spike_vs_history"]
    assert len(spikes) == 3 and all(h.evidence["corroboration"]["coherent"] for h in spikes)
    assert all(h.kind == "uncertain" for h in res.hits) and verdict(res) == "UNCERTAIN"
    assert "genuine-extreme candidate" in spikes[0].reason and "nothing else moves" not in spikes[0].reason
    assert "other variables moved with it" in spikes[0].reason
    out = score_reading(StreamReading("S", after(hist), "x", t - 8.0, p - 14.0, _rh_for_dew_point(t - 8.0, dp)), (), hist)
    assert out.status == "UNCERTAIN" and out.genuine_extreme and out.flagged and out.rule_score > 0       # (several UNCERTAIN hits can still band high: the band is of the score only)


def test_warmer_and_much_more_humid_at_once_is_a_fault():
    hist = series(60, t=25.0, rh=50.0)
    t, p, rh = next_values(hist)
    res = run(hist, t + 12.0, p, min(100.0, rh + 35.0))
    assert verdict(res) == "SUSPECT" and not any(h.evidence.get("corroboration", {}).get("coherent") for h in res.hits)
    assert "dewpoint_jump" in names(res)                                    # the derived dew point jumped as well


def test_slow_drift_is_found_as_a_level_shift_which_is_uncertain():
    hist = series(100)
    t, p, rh = next_values(hist)
    for k in range(1, 61):                                                  # a linear ramp of 6 C over 60 readings, one reading per minute
        hist.append(ClimateSample(after(hist), t + 6.0 * k / 60.0, p + 0.01 * (k % 3), rh + 0.1 * (k % 4)))     # p and rh wobble so they are not frozen
    res = run_weather_checks({"temperature": t + 6.0, "pressure": p, "humidity": rh}, after(hist), hist)
    assert "level_shift" in names(res) and not any(h.kind == "fault" for h in res.hits if h.check == "level_shift")
    assert next(h for h in res.hits if h.check == "level_shift").evidence["shift"]["basis"] == "derived"
    flat = series(100)
    assert "level_shift" not in names(run_weather_checks({"temperature": t + 0.1, "pressure": p, "humidity": rh}, after(flat), flat))


# ---------------------------------------------------------------------------------------------------- dew point
def test_magnus_dew_point_values():
    assert dew_point_c(20.0, 100.0) == pytest.approx(20.0, abs=1e-6)
    assert dew_point_c(20.0, 50.0) == pytest.approx(9.3, abs=0.2)
    assert dew_point_c(20.0, 0.0) is None


def test_dew_point_above_temperature_is_a_fault_and_below_the_tolerance_is_not():
    assert "dewpoint_above_temperature" in names(run_weather_checks({"temperature": 20.0, "humidity": 105.0}, T0))
    assert "dewpoint_above_temperature" not in names(run_weather_checks({"temperature": 20.0, "humidity": 101.0}, T0))
    res = run_weather_checks({"temperature": 20.0}, T0)                     # humidity absent: the check says why it did not run
    assert any(n["check"] == "dewpoint_above_temperature" and "humidity" in n["reason"] for n in res.not_run)


# ---------------------------------------------------------------------------------------------------- dropout, gap, absent variables
def test_dropout_of_a_variable_the_station_reported_is_a_fault():
    hist = series(40)
    t, p, rh = next_values(hist)
    res = run(hist, t, None, rh)
    assert names(res) == {"dropout"} and verdict(res) == "SUSPECT" and res.hits[0].evidence["variable"] == "pressure"


def test_a_variable_the_station_never_reports_is_not_run_with_a_reason_and_never_scored():
    hist = [ClimateSample(s.timestamp, s.temperature, None, s.humidity) for s in series(40)]       # a Weather Union style station: no pressure
    t, _, rh = next_values(hist)
    res = run_weather_checks({"temperature": t, "pressure": None, "humidity": rh}, after(hist), hist)
    assert res.hits == [] and verdict(res) == "OK"
    pr = [n for n in res.not_run if n["check"] == "pressure"]
    assert len(pr) == 1 and "not reported" in pr[0]["reason"]


def test_a_reporting_gap_is_uncertain_and_needs_the_cadence():
    hist = series(30)
    t, p, rh = next_values(hist)
    res = run(hist, t, p, rh, seconds=60.0 * 10)
    assert names(res) == {"reporting_gap"} and verdict(res) == "UNCERTAIN"
    assert res.hits[0].evidence["cadence"]["basis"] == "derived"
    res = run(series(3), 22.0, 990.0, 55.0)
    assert any(n["check"] == "reporting_gap" and "needed" in n["reason"] for n in res.not_run)


def test_a_long_gap_drops_the_history_checks_and_says_so():
    hist = series(60)
    t, p, rh = next_values(hist)
    res = run(hist, t + 20.0, p, rh, seconds=60.0 * 300)                    # five hours later: the old readings are no context
    assert "rate_of_change" not in names(res) and "spike_vs_history" not in names(res)
    assert any(n["check"] == "rate_of_change" and "context limit" in n["reason"] for n in res.not_run)


# ---------------------------------------------------------------------------------------------------- empty, short, None, nan
def test_empty_input_and_none_values():
    res = run_weather_checks({"temperature": None, "pressure": None, "humidity": None}, T0)
    assert res.hits == [] and res.has_data is False and verdict(res) == "NO_DATA"
    res = run_weather_checks({}, T0, [])
    assert res.has_data is False
    res = run_weather_checks({"temperature": 20.0}, T0, [])                  # first reading ever: history checks list their reasons
    assert verdict(res) == "OK" and {n["check"] for n in res.not_run} >= {"rate_of_change", "spike_vs_history", "frozen_value", "level_shift"}
    assert all(n["reason"] for n in res.not_run)


def test_nan_in_history_is_ignored_as_context():
    hist = series(40)
    hist[10] = ClimateSample(hist[10].timestamp, float("nan"), None, 9999.9)
    res = run(hist, *next_values(hist))
    assert verdict(res) == "OK"


def test_a_timestamp_not_after_the_previous_reading_runs_no_history_check():
    hist = series(40)
    res = run_weather_checks({"temperature": 90.0 - 40.0}, hist[-1].timestamp, hist)         # same timestamp
    assert any("not after" in n["reason"] for n in res.not_run) and "rate_of_change" not in names(res)


# ---------------------------------------------------------------------------------------------------- causal and bounded
def test_the_result_never_depends_on_later_readings():
    full = series(100)
    for k in (30, 60, 99):
        a = run_weather_checks({"temperature": 80.0, "pressure": 990.0, "humidity": 50.0}, full[k].timestamp, full[:k])
        b = run_weather_checks({"temperature": 80.0, "pressure": 990.0, "humidity": 50.0}, full[k].timestamp, full[:k])
        assert [h.check for h in a.hits] == [h.check for h in b.hits]
    # the stream scoring path: each reading is scored before it is added, so a later spike changes no earlier verdict
    h = ClimateHistory()
    verdicts = []
    for s in series(60):
        r = StreamReading("A", s.timestamp, "x", s.temperature, s.pressure, s.humidity)
        verdicts.append(score_reading(r, (), h.recent("A")).status)
        h.add("A", climate_sample(r))
    assert set(verdicts) == {"OK"}
    r = StreamReading("A", series(1)[0].timestamp, "x", 59.0, 990.0, 50.0)       # a hot first reading: nothing before it to compare, only absolute checks speak
    assert score_reading(r, (), ClimateHistory().recent("A")).status == "UNCERTAIN"


def test_history_is_bounded_per_station_and_in_station_count_and_ignores_old_timestamps():
    h = ClimateHistory(max_len=5, max_stations=3)
    for i in range(20):
        h.add("A", ClimateSample(T0 + timedelta(seconds=i), 1.0, 2.0, 3.0))
    assert len(h.recent("A")) == 5 and h.recent("A")[-1].timestamp == T0 + timedelta(seconds=19)
    h.add("A", ClimateSample(T0, 9.0, 9.0, 9.0))                             # older than the newest: ignored
    assert h.recent("A")[-1].temperature == 1.0
    for s in "BCD":
        h.add(s, ClimateSample(T0, 1.0, 2.0, 3.0))
    assert len(h) == 3 and "A" not in h
    assert wc.HISTORY_MAX >= wc.SHIFT_N and wc.MAX_STATIONS > 0


# ---------------------------------------------------------------------------------------------------- scoring integration
def test_climate_readings_get_a_verdict_a_score_and_evidence_instead_of_no_checks():
    hist = series(60)
    t, p, rh = next_values(hist)
    ok = score_reading(StreamReading("S", after(hist), "x", t, p, rh), (), hist)
    assert ok.status == "OK" and ok.rule_score == 0.0 and ok.ran and not ok.flagged and ok.hits == [] and ok.severity is None
    bad = score_reading(StreamReading("S", after(hist), "x", t, p, 9999.9), (), hist)
    assert bad.status == "SUSPECT" and bad.flagged and bad.rule_score > 0.8 and bad.severity == "high" and bad.variable == "humidity"
    assert bad.hits[0]["check"] == "corrupt_value" and bad.hits[0]["evidence"]["observed"]["basis"] == "measured"
    assert score_reading(StreamReading("S", T0, "x", 20.0, 1000.0, 50.0)).status == "OK"          # first reading: absolute checks only, the rest "not run"
    first = score_reading(StreamReading("S", T0, "x", 20.0, 1000.0, 50.0))
    assert {n["check"] for n in first.not_run} >= {"rate_of_change", "spike_vs_history"}


def test_nothing_to_check_stays_no_checks_and_rain_keeps_its_own_path():
    nothing = score_reading(StreamReading("S", T0, "x"))
    assert nothing.status == NO_CHECKS and nothing.rule_score is None and not nothing.ran
    rain = score_reading(StreamReading("S", T0, "x", rain_mm=-2.0))
    assert rain.status == "SUSPECT" and rain.hits[0]["check"] == "negative_value" and rain.variable == "rain"
    assert not any(n["check"] in ("temperature", "pressure", "humidity") for n in rain.not_run)    # a rain gauge is not accused of lacking T/P/RH
    both = score_reading(StreamReading("S", T0, "x", 20.0, 1000.0, 50.0, rain_mm=-2.0))
    assert both.status == "SUSPECT" and both.variable == "rain"
    both2 = score_reading(StreamReading("S", T0, "x", 20.0, 1000.0, 9999.9, rain_mm=-2.0))
    assert {h["check"] for h in both2.hits} == {"negative_value", "corrupt_value"} and both2.variable == "multiple"
    assert both2.rule_score > both.rule_score


def test_all_variables_missing_with_history_is_no_data_not_a_verdict():
    hist = series(40)
    out = score_reading(StreamReading("S", after(hist), "x"), (), hist)
    assert out.status == "NO_DATA" and not out.flagged and out.rule_score == 0.0
    assert {h["check"] for h in out.hits} == {"dropout"}                       # still reported as evidence
