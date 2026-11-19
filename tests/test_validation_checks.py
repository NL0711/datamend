"""Check catalogue conformance suite (spec slice 4): each check fires on a minimal generated case and stays silent on a clean one.

Pass or fail only; this says nothing about recall or precision. All data is generated.
"""
from datetime import date, datetime, timedelta, timezone

from backend.app.validation.checks import CATALOGUE, run_checks, run_daily_checks, run_reading_checks
from backend.app.validation.records import DailyTotal, Reading, RowIssue

T0 = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)


def rd(sid, i, acc=None, inten=None, lat=None, lon=None, mode="cumulative", step=15, basis="observed", confirmed=True):
    return Reading("upload", sid, T0 + timedelta(minutes=step * i), acc, inten, basis, mode if acc is not None else None, confirmed,
                   row_ref=f"{sid}{i}", latitude=lat, longitude=lon)


def series(sid, accs=None, intens=None, n=None, **kw):
    n = n or len(accs or intens)
    return [rd(sid, i, accs[i] if accs else None, intens[i] if intens else None, **kw) for i in range(n)]


def names(res, i):
    return [h.check for h in res.results[i].hits]


def verdicts(res):
    return [r.verdict for r in res.results]


# ---------------------------------------------------------------- reading profile
def test_clean_reading_series_is_all_ok_with_zero_score():
    res = run_reading_checks(series("A", accs=[0, 0, 0.2, 0.2, 0.4, 0.4], intens=[0, 0, 1, 0, 1, 0]), interval_minutes=15)
    assert verdicts(res) == ["OK"] * 6 and all(r.rule_score == 0 and r.severity is None for r in res.results)


def test_negative_value_is_suspect_and_high_severity():
    res = run_reading_checks(series("A", accs=[0, -2.0]))
    assert "negative_value" in names(res, 1) and res.results[1].verdict == "SUSPECT" and res.results[1].severity == "high"


def test_intensity_above_ceiling_is_suspect():
    res = run_reading_checks(series("A", intens=[1.0, 301.0]))
    assert "intensity_above_ceiling" in names(res, 1) and res.results[1].verdict == "SUSPECT"
    assert verdicts(run_reading_checks(series("A", intens=[1.0, 300.0])))[1] == "OK"


def test_counter_jump_suspect_reset_info_only():
    res = run_reading_checks(series("A", accs=[0, 10, 70]))
    assert names(res, 2) == ["counter_jump"] and res.results[2].verdict == "SUSPECT"
    res = run_reading_checks(series("A", accs=[10, 5]))
    assert names(res, 1) == ["counter_reset"] and res.results[1].verdict == "OK" and res.results[1].rule_score == 0.1


def test_counter_checks_do_not_run_in_per_reading_mode():
    res = run_reading_checks(series("A", accs=[0, 70], mode="per_reading"))
    assert names(res, 1) == []


def test_frozen_nonzero_intensity_after_six_identical_readings_not_five():
    assert verdicts(run_reading_checks(series("A", intens=[2.0] * 5)))[-1] == "OK"
    res = run_reading_checks(series("A", intens=[2.0] * 6))
    assert "frozen_intensity" in names(res, 5) and res.results[5].verdict == "SUSPECT"
    assert verdicts(run_reading_checks(series("A", intens=[0.0] * 6)))[-1] == "OK"       # a dry gauge is not frozen


def test_intensity_with_a_flat_counter_is_a_mismatch():
    res = run_reading_checks(series("A", accs=[5, 5, 5, 5], intens=[0, 1, 1, 1]))
    assert "intensity_counter_mismatch" in names(res, 3) and res.results[3].verdict == "SUSPECT"


def test_missing_values_are_no_data_never_ok():
    res = run_reading_checks([rd("A", 0, 0.0, 0.0), Reading("upload", "A", T0 + timedelta(minutes=15), None, None, row_ref=2, issues=[RowIssue("missing_value", "empty")])])
    assert verdicts(res) == ["OK", "NO_DATA"]


def test_row_without_timestamp_is_kept_as_no_data_in_input_order():
    bad = Reading("upload", "A", None, 1.0, None, row_ref=9, issues=[RowIssue("bad_timestamp", "x")])
    res = run_reading_checks([rd("A", 1, 0.0), bad, rd("A", 0, 0.0)])
    assert [r.row_ref for r in res.results] == ["A1", 9, "A0"] and res.results[1].verdict == "NO_DATA"


def test_duplicate_row_is_uncertain_not_suspect():
    r = rd("A", 0, 0.0, 0.0)
    r.issues.append(RowIssue("duplicate_timestamp", "2 rows share this station and timestamp"))
    res = run_reading_checks([r])
    assert names(res, 0) == ["duplicate_row"] and res.results[0].verdict == "UNCERTAIN"


def cluster(wet_flags, n_steps=3, mode="cumulative"):
    """Stations ~1 km apart; wet_flags[station] = whether the station is wet in the LAST step."""
    out = []
    for k, (sid, wet) in enumerate(wet_flags.items()):
        for i in range(n_steps):
            acc = 0.0 if i < n_steps - 1 else (1.0 if wet else 0.0)
            out.append(rd(sid, i, acc, None, lat=19.0 + 0.001 * k, lon=72.8, mode=mode))
    return out


def test_isolated_wet_with_enough_dry_neighbours_is_uncertain_never_suspect():
    res = run_reading_checks(cluster({"A": True, "B": False, "C": False, "D": False}), interval_minutes=15)
    last_a = next(i for i, r in enumerate(res.results) if r.station_id == "A" and r.row_ref == "A2")
    assert "neighbour_isolated_wet" in names(res, last_a) and res.results[last_a].verdict == "UNCERTAIN"
    assert res.results[last_a].rule_score == 0.3 and res.results[last_a].severity == "medium"


def test_isolated_dry_and_agreeing_neighbours():
    res = run_reading_checks(cluster({"A": False, "B": True, "C": True, "D": True}), interval_minutes=15)
    a = next(i for i, r in enumerate(res.results) if r.row_ref == "A2")
    assert "neighbour_isolated_dry" in names(res, a)
    quiet = run_reading_checks(cluster({"A": True, "B": True, "C": True, "D": True}), interval_minutes=15)
    assert all(not any(h.check.startswith("neighbour") for h in r.hits) for r in quiet.results)


def test_neighbour_check_is_not_run_with_too_few_stations_or_no_coordinates():
    res = run_reading_checks(cluster({"A": True, "B": False, "C": False}), interval_minutes=15)       # only 2 neighbours
    assert {n["station_id"] for n in res.not_run if n["check"] == "neighbour"} == {"A", "B", "C"}
    assert all("3 needed" in n["reason"] for n in res.not_run)
    res = run_reading_checks(series("A", accs=[0, 0]))
    assert res.not_run == [{"check": "neighbour", "station_id": "A", "reason": "no coordinates for this station"}]


def test_evidence_carries_basis_tags_and_assumed_units_on_live_data():
    res = run_reading_checks(series("A", intens=[1.0, 400.0], basis="received", confirmed=False))
    ev = res.results[1].hits[0].evidence
    assert ev["observed"] == {"value": 400.0, "unit": "mm/h", "basis": "assumed"}
    assert ev["threshold"]["basis"] == "assumed" and ev["time_basis"] == "received" and ev["row_ref"] == "A1"


# ---------------------------------------------------------------- daily profile
D0 = date(2026, 7, 1)


def dt(sid, i, mm, lat=None, lon=None, complete=None):
    return DailyTotal("upload", sid, D0 + timedelta(days=i), mm, complete, True, row_ref=f"{sid}{i}", latitude=lat, longitude=lon)


def test_clean_daily_series_is_ok():
    res = run_daily_checks([dt("A", i, v) for i, v in enumerate([0.0, 1.2, 0.0, 3.4, 0.5])])
    assert verdicts(res) == ["OK"] * 5


def test_impossible_daily_values_are_suspect():
    res = run_daily_checks([dt("A", 0, -1.0), dt("A", 1, 1000.5), dt("A", 2, 1000.0)])
    assert verdicts(res) == ["SUSPECT", "SUSPECT", "OK"]


def test_repeated_positive_value_needs_three_days_and_ignores_zeros_and_incomplete_days():
    res = run_daily_checks([dt("A", i, 5.0) for i in range(3)])
    assert names(res, 2) == ["repeated_value"] and res.results[2].verdict == "SUSPECT" and names(res, 1) == []
    assert verdicts(run_daily_checks([dt("A", i, 0.0) for i in range(5)])) == ["OK"] * 5
    assert verdicts(run_daily_checks([dt("A", 0, 5.0), dt("A", 1, 5.0, complete=False), dt("A", 2, 5.0)])) == ["OK"] * 3


def wet_years(sid, heavy, lat=None, lon=None):
    """Five earlier Julys (1 to 20 July, wet every day, 2 to 6 mm) and then 21 July 2025 with value `heavy`: 100 earlier wet days
    fall inside the 15-day window, which a single year cannot supply."""
    rows, k = [], 0
    for year in range(2020, 2025):
        for d in range(1, 21):
            rows.append(DailyTotal("upload", sid, date(year, 7, d), 2.0 + (k % 5), None, True, row_ref=f"{sid}{k}", latitude=lat, longitude=lon))
            k += 1
    rows.append(DailyTotal("upload", sid, date(2025, 7, 21), heavy, None, True, row_ref=f"{sid}last", latitude=lat, longitude=lon))
    return rows


def test_climatology_tail_is_uncertain_for_a_lone_gauge_not_suspect():
    res = run_daily_checks(wet_years("A", 400.0))
    assert names(res, 100) == ["climatology_upper_tail"] and res.results[100].verdict == "UNCERTAIN"
    assert res.results[100].hits[0].evidence["tail_probability"]["basis"] == "derived"
    assert verdicts(run_daily_checks(wet_years("A", 5.0)))[100] == "OK"


def test_climatology_is_not_run_before_thirty_wet_days():
    res = run_daily_checks([dt("A", i, 2.0 + i % 3) for i in range(10)] + [dt("A", 10, 400.0)])
    assert res.results[10].verdict == "OK"
    clim = [n for n in res.not_run if n["check"] == "climatology_upper_tail"]
    assert clim == [{"check": "climatology_upper_tail", "station_id": "A", "reason": "never reached 30 earlier wet days near the day of year (most: 10)"}]


def test_heavy_value_corroborated_by_wet_neighbours_does_not_change_the_verdict():
    recs = []
    for k, sid in enumerate("ABCD"):
        recs += wet_years(sid, 400.0, lat=19.0 + 0.001 * k, lon=72.8)
    res = run_daily_checks(recs)
    a = next(i for i, r in enumerate(res.results) if r.row_ref == "Alast")
    hit = next(h for h in res.results[a].hits if h.check == "climatology_upper_tail")
    assert hit.kind == "info" and "corroborated" in hit.reason and res.results[a].verdict == "OK"


def test_daily_isolated_wet_day_with_dry_neighbours_is_uncertain():
    recs = []
    for k, sid in enumerate("ABCD"):
        recs += [DailyTotal("upload", sid, D0 + timedelta(days=i), (25.0 if (sid == "A" and i == 2) else 0.0), None, True, row_ref=f"{sid}{i}",
                            latitude=19.0 + 0.001 * k, longitude=72.8) for i in range(4)]
    res = run_daily_checks(recs)
    a2 = next(i for i, r in enumerate(res.results) if r.row_ref == "A2")
    assert "neighbour_isolated_wet" in names(res, a2) and res.results[a2].verdict == "UNCERTAIN"


def test_missing_daily_value_is_no_data_and_dispatch_by_profile():
    res = run_checks([dt("A", 0, None), dt("A", 1, 0.0)], "daily")
    assert verdicts(res) == ["NO_DATA", "OK"] and res.method.startswith("rules")
    assert run_checks(series("A", accs=[0, 0]), "reading").profile == "reading"


def test_catalogue_declares_needs_for_every_check():
    assert CATALOGUE and all(c.needs and c.kind in ("fault", "uncertain", "info") and 0 <= c.weight <= 1 for c in CATALOGUE.values())
