"""Insights: each of the five views on generated rain days (pure functions), and the route against stored runs."""
import math
from datetime import date, timedelta

import pytest

from backend.app.db.database import async_session_factory
from backend.app.validation import insights as ins
from backend.app.validation.insights import Day
from backend.app.validation.models import ValidationResult, ValidationRun


def span(station, start, n, f, verdict="OK"):
    d0 = date.fromisoformat(start)
    return [Day(station, (d0 + timedelta(days=i)).isoformat(), f(i), verdict) for i in range(n)]


def years(station, first, last, per_day):
    """Every day of the years first..last at a constant per_day (a callable of the year)."""
    out = []
    for y in range(first, last + 1):
        out += span(station, f"{y}-01-01", 366 if y % 4 == 0 else 365, lambda i, y=y: per_day(y))
    return out


# ---- 1 anomaly ----
def test_anomaly_is_the_departure_from_the_stations_own_complete_year_normal():
    days = years("A", 2019, 2022, lambda y: 3.0 if y == 2022 else 1.0)
    r = ins.anomaly(days, "year")
    assert r["enough"] is True
    pts = {p["period"]: p for p in r["series"][0]["points"]}
    assert set(pts) == {"2019", "2020", "2021", "2022"}
    assert pts["2022"]["anomaly_mm"] > 0 > pts["2019"]["anomaly_mm"]
    assert math.isclose(sum(p["anomaly_mm"] for p in pts.values()), 0, abs_tol=0.5)       # departures from a mean sum to about zero


def test_anomaly_refuses_short_history_and_ignores_incomplete_periods():
    one_year = years("A", 2021, 2021, lambda y: 1.0)
    r = ins.anomaly(one_year, "year")
    assert r["enough"] is False and "3 complete years" in r["reason"] and "A" in r["skipped"]
    partial = years("B", 2019, 2021, lambda y: 1.0)[:-5]                                  # the last year is missing five days
    r = ins.anomaly(partial, "year")
    assert r["enough"] is False                                                           # only 2 complete years are left


def test_anomaly_marks_flagged_days_and_rejects_a_bad_granularity():
    days = years("A", 2019, 2022, lambda y: 1.0)
    days[400] = Day("A", days[400].day, days[400].mm, "SUSPECT")
    r = ins.anomaly(days, "year")
    assert sum(p["flagged_days"] for p in r["series"][0]["points"]) == 1
    with pytest.raises(ValueError):
        ins.anomaly(days, "week")


# ---- 2 correlation ----
def test_correlation_is_one_for_identical_stations_and_minus_one_for_opposite_ones():
    a = span("A", "2024-01-01", 60, lambda i: float(i % 7))
    b = span("B", "2024-01-01", 60, lambda i: float(i % 7))
    c = span("C", "2024-01-01", 60, lambda i: 10.0 - float(i % 7))
    r = ins.correlation(a + b + c)
    ix = {s: i for i, s in enumerate(r["stations"])}
    assert r["matrix"][ix["A"]][ix["B"]] == 1.0 and r["matrix"][ix["A"]][ix["C"]] == -1.0
    assert r["matrix"][ix["A"]][ix["A"]] == 1.0


def test_correlation_needs_shared_days_and_variation():
    a = span("A", "2024-01-01", 60, lambda i: float(i % 5))
    b = span("B", "2024-03-01", 60, lambda i: float(i % 5))                                # overlap is 0 days
    assert ins.correlation(a + b)["enough"] is False
    flat = span("F", "2024-01-01", 60, lambda i: 2.0)
    r = ins.correlation(a + flat)
    assert r["enough"] is False                                                           # a constant series has no correlation
    assert ins.correlation(a)["enough"] is False                                          # one station


# ---- 3 climate ----
def test_climate_bands_follow_the_annual_total_and_short_stations_are_listed():
    dry = span("D", "2023-01-01", 365, lambda i: 0.5)                                     # ~183 mm a year
    wet = span("W", "2023-01-01", 365, lambda i: 6.0)                                     # ~2190 mm a year
    short = span("S", "2023-01-01", 40, lambda i: 1.0)
    r = ins.climate(dry + wet + short)
    by = {s["station"]: s for s in r["stations"]}
    assert by["D"]["band"] == "dry" and by["W"]["band"] == "wet" and r["too_short"] == ["S"]
    assert by["D"]["wet_day_share"] == 0.0 and by["W"]["wet_day_share"] == 1.0
    assert ins.band_of(500.0) == "moderate" and ins.band_of(499.9) == "dry" and ins.band_of(1500.0) == "wet"
    assert ins.climate(short)["enough"] is False


# ---- 4 verdict mix ----
def test_verdict_mix_shares_sum_to_one_per_period():
    days = span("A", "2024-01-01", 31, lambda i: 1.0) + [Day("A", "2024-02-01", 1.0, "SUSPECT"), Day("A", "2024-02-02", 1.0, "OK")]
    r = ins.verdict_mix(days, "month")
    jan, feb = r["periods"]
    assert jan["period"] == "2024-01" and jan["share_OK"] == 1.0
    assert feb["SUSPECT"] == 1 and feb["share_SUSPECT"] == 0.5 and feb["rows"] == 2
    assert math.isclose(sum(feb[f"share_{v}"] for v in ins.VERDICTS), 1.0)
    assert ins.verdict_mix([], "month")["enough"] is False


# ---- 5 heavy rain ----
def test_heavy_days_use_the_stations_own_percentile_and_unflagged_is_not_confirmed():
    days = span("A", "2024-01-01", 100, lambda i: 1.0 + i)                                # 1 .. 100 mm, all wet
    days[-1] = Day("A", days[-1].day, 100.0, "SUSPECT")                                    # the biggest day is flagged
    r = ins.heavy_rain(days)
    st = r["stations"][0]
    assert st["heavy_days"] == 5 and st["flagged"] == 1 and st["not_flagged"] == 4
    assert r["heavy_verdicts"]["SUSPECT"] == 1 and r["heavy_verdicts"]["OK"] == 4
    assert "not 'confirmed'" in r["note"] and all(p["heavy"] for p in r["points"][:5]) and not r["points"][5]["heavy"]


def test_heavy_rain_skips_stations_with_too_few_wet_days():
    dry = span("D", "2024-01-01", 100, lambda i: 0.0) + span("E", "2024-01-01", 10, lambda i: 5.0)
    r = ins.heavy_rain(dry)
    assert r["enough"] is False and set(r["too_short"]) == {"D", "E"}                     # D has no wet day, E has too few


def test_a_later_run_wins_for_the_same_station_and_day():
    old = [Day("A", "2024-01-01", 5.0, "OK")]
    new = [Day("A", "2024-01-01", 9.0, "SUSPECT")]
    assert ins.by_station(old + new)["A"]["2024-01-01"].mm == 9.0


# ---- the route ----
async def store_run(synthetic=False, profile="daily", rows=()):
    async with async_session_factory() as s:
        run = ValidationRun(profile=profile, source="upload", label="t", n_rows=len(rows), n_stations=1, settings={}, platform_version="t",
                            git_commit="t", status="completed", synthetic=synthetic)
        s.add(run)
        await s.flush()
        for i, (st, tk, mm, v) in enumerate(rows):
            s.add(ValidationResult(run_id=run.id, position=i, row_ref=str(i), station_id=st, time_key=tk, mm=mm, verdict=v, rule_score=0.0,
                                   original_row={}, issues=[]))
        await s.commit()
        return run.id


@pytest.mark.asyncio
async def test_route_scopes_real_synthetic_and_one_run(async_client):
    rows = [("A", f"2024-01-{d:02d}", 2.0, "OK") for d in range(1, 11)]
    real = await store_run(False, rows=rows)
    fake = await store_run(True, rows=[("Z", f"2024-01-{d:02d}", 9.0, "SUSPECT") for d in range(1, 6)])
    reading = await store_run(False, profile="reading", rows=[("R", "2024-01-01T00:00:00Z", None, "OK")])
    r = (await async_client.get("/api/validation/insights", params={"run_id": real})).json()
    assert r["selection"]["stations"] == 1 and r["selection"]["rows_used"] == 10 and r["selection"]["synthetic"] is False
    r = (await async_client.get("/api/validation/insights", params={"run_id": fake})).json()
    assert r["selection"]["synthetic"] is True
    r = (await async_client.get("/api/validation/insights", params={"run_id": reading})).json()
    assert r["selection"]["rows_used"] == 0 and r["selection"]["rows_without_mm"] == 1 and r["verdict_mix"]["enough"] is False
    everything = (await async_client.get("/api/validation/insights")).json()["selection"]
    assert "Z" not in str(everything) and everything["scope"] == "every real run"
    with_syn = (await async_client.get("/api/validation/insights", params={"include_synthetic": "true"})).json()["selection"]
    assert with_syn["synthetic"] is True and with_syn["stations"] >= everything["stations"] + 1


@pytest.mark.asyncio
async def test_route_filters_by_station_and_period_and_validates_input(async_client):
    rid = await store_run(False, rows=[("A", f"2024-01-{d:02d}", 1.0, "OK") for d in range(1, 11)] + [("B", f"2024-02-{d:02d}", 1.0, "OK") for d in range(1, 6)])
    r = (await async_client.get("/api/validation/insights", params={"run_id": rid, "station": "B"})).json()["selection"]
    assert r["stations"] == 1 and r["rows_used"] == 5
    r = (await async_client.get("/api/validation/insights", params={"run_id": rid, "start": "2024-01-04", "end": "2024-01-06"})).json()["selection"]
    assert r["rows_used"] == 3 and r["first_day"] == "2024-01-04" and r["last_day"] == "2024-01-06"
    assert (await async_client.get("/api/validation/insights", params={"granularity": "week"})).status_code == 422
    assert (await async_client.get("/api/validation/insights", params={"start": "last week"})).status_code == 422
    assert (await async_client.get("/api/validation/insights", params={"run_id": 999999})).status_code == 404
