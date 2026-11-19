"""Tests of the live rain-gauge path (backend/app/rainfall). Generated data and a mocked HTTP transport only: no network, no API quota."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from backend.app.rainfall.catalog import RAIN_GAUGE, load_catalog, neighbours
from backend.app.rainfall.daily import DailyAccumulator, rain_day, rain_day_bounds, total_for_day
from backend.app.rainfall.service import RainfallService, pick_cluster, safe_interval_seconds
from backend.app.rainfall.weather_union import (IST, BudgetExhausted, CallBudget, RainObservation, WeatherUnionClient,
                                                 parse_response)

T0 = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)


def obs(i, intensity=0.0, accum=0.0, sid="ZWL1", status="OK", step_min=15):
    return RainObservation(sid, T0 + timedelta(minutes=step_min * i), 2, intensity, accum, status)


def payload(intensity=0, accum=0, device=2, status="200"):
    return {"status": status, "message": "", "device_type": device,
            "locality_weather_data": {"temperature": None, "humidity": None, "wind_speed": None, "wind_direction": None,
                                      "rain_intensity": intensity, "rain_accumulation": accum, "aqi_pm_10": None, "aqi_pm_2_point_5": None}}


# ---- parsing --------------------------------------------------------------------------------------------------------
def test_parse_keeps_raw_values_and_never_invents():
    o = parse_response("Z", payload(1.5, 0.4), T0)
    assert (o.rain_intensity, o.rain_accumulation, o.status, o.device_type) == (1.5, 0.4, "OK", 2)


def test_parse_all_null_rain_is_no_rain_fields_not_zero():
    o = parse_response("Z", payload(None, None), T0)
    assert o.status == "NO_RAIN_FIELDS" and o.rain_intensity is None and o.rain_accumulation is None


def test_parse_non_numeric_and_bad_status():
    assert parse_response("Z", payload("x", None), T0).status == "NO_RAIN_FIELDS"
    assert parse_response("Z", payload(0, 0, status="500"), T0).status == "API_ERROR"


# ---- budget ---------------------------------------------------------------------------------------------------------
def test_budget_refuses_over_limit_and_resets_at_ist_midnight():
    now = [datetime(2026, 11, 19, 23, 59, tzinfo=IST)]
    b = CallBudget(limit=2, clock=lambda: now[0])
    b.take(); b.take()
    with pytest.raises(BudgetExhausted):
        b.take()
    now[0] = datetime(2026, 11, 20, 0, 1, tzinfo=IST)
    b.take()
    assert b.used == 1 and b.remaining == 1


def test_safe_interval_never_exceeds_budget():
    assert safe_interval_seconds(9, 900, 900) == 900          # 96 polls x 9 = 864 <= 900
    assert safe_interval_seconds(30, 900, 900) > 900          # too many stations: slowed down
    assert 86400 / safe_interval_seconds(30, 900, 900) * 30 <= 900


# ---- rain day and totals --------------------------------------------------------------------------------------------
def test_rain_day_is_03_to_03_utc_labelled_by_the_date_it_ends():
    assert rain_day(datetime(2026, 11, 19, 2, 59, tzinfo=timezone.utc)) == date(2026, 11, 19)
    assert rain_day(datetime(2026, 11, 19, 3, 0, tzinfo=timezone.utc)) == date(2026, 11, 20)
    start, end = rain_day_bounds(date(2026, 11, 19))
    assert (end - start) == timedelta(days=1) and start == datetime(2026, 11, 18, 3, tzinfo=timezone.utc) and end == datetime(2026, 11, 19, 3, tzinfo=timezone.utc)
    for ts in (start, end - timedelta(seconds=1)):                     # the bounds round-trip through the label
        assert rain_day(ts) == date(2026, 11, 19)
    assert rain_day(end) == date(2026, 11, 20)
    with pytest.raises(ValueError):
        rain_day(datetime(2026, 11, 19, 3, 0))


def test_cumulative_total_with_reset_and_labels():
    day = date(2026, 11, 19)
    s = [(T0 + timedelta(minutes=15 * i), v) for i, v in enumerate([0, 1.0, 3.0, 0.5, 2.5])]  # reset between 3.0 and 0.5
    t = total_for_day("Z", day, s, "cumulative")
    assert t.total_mm == pytest.approx(1.0 + 2.0 + 0.5 + 2.0) and t.n_resets == 1 and t.units_confirmed is False


def test_per_reading_total_is_the_sum():
    s = [(T0 + timedelta(minutes=15 * i), v) for i, v in enumerate([0.2, 0.0, 0.4])]
    assert total_for_day("Z", date(2026, 11, 19), s, "per_reading").total_mm == pytest.approx(0.6)


def test_no_usable_readings_gives_none_not_zero():
    assert total_for_day("Z", date(2026, 11, 19), [], "cumulative").total_mm is None
    assert total_for_day("Z", date(2026, 11, 19), [(T0, -1.0), (T0, float("nan"))], "cumulative").total_mm is None


def test_completeness_needs_full_coverage_and_small_gaps():
    day = date(2026, 11, 19)
    start, end = rain_day_bounds(day)
    full = [(start + timedelta(minutes=15 * i), 0.0) for i in range(96)]
    assert total_for_day("Z", day, full, "cumulative", now=end + timedelta(minutes=1)).complete is True
    gap = [p for p in full if not (40 <= full.index(p) <= 60)]
    assert total_for_day("Z", day, gap, "cumulative", now=end + timedelta(minutes=1)).complete is False
    assert total_for_day("Z", day, full, "cumulative", now=start + timedelta(hours=5)).complete is False  # day not over


def test_accumulator_ignores_bad_readings_and_prunes_old_days():
    a = DailyAccumulator("cumulative", keep_days=2)
    a.add(obs(0, accum=None, status="NO_RAIN_FIELDS"))
    assert a.days("ZWL1") == []
    for d in range(4):
        a.add(RainObservation("ZWL1", T0 + timedelta(days=d), 2, 0.0, 1.0))
    assert len(a.days("ZWL1")) == 2


# ---- live quality comes from the validation catalogue (the legacy one-gauge scorer is deleted) ---------------------------
# Each check's behaviour is covered by tests/test_validation_checks.py; here only the live adapter is tested.
def _service_with_history(per_station):
    stations = pick_cluster("Mumbai", len(per_station))
    svc = RainfallService(_client(lambda r: httpx.Response(200, json=payload(0, 0))), stations, 900.0, "cumulative")
    for st, rows in zip(stations, per_station):
        for i, (inten, acc) in enumerate(rows):
            svc.history[st.locality_id].append(obs(i, inten, acc, sid=st.locality_id))
    return svc, stations


def test_live_readings_are_platform_records_with_received_time_and_unconfirmed_units():
    svc, stations = _service_with_history([[(0.0, 0.0), (0.0, 0.0)]])
    rs = svc.readings()
    assert len(rs) == 2 and all(r.source == "weather_union" and r.time_basis == "received" and r.units_confirmed is False for r in rs)
    assert rs[0].latitude == stations[0].latitude and rs[0].row_ref.startswith(stations[0].locality_id + "@")


def test_live_station_report_uses_the_catalogue_and_labels_the_score():
    svc, stations = _service_with_history([[(0.0, 0.0), (900.0, 80.0)]])
    q = svc.station_report(stations[0].locality_id)["quality"]
    assert q["assessment"] == "SUSPECT" and q["score_kind"].startswith("rule score") and "not a trained model" in q["method"]
    assert {r["check"] for r in q["reasons"]} >= {"intensity_above_ceiling", "counter_jump"} and 0.9 < q["score"] <= 1.0
    assert any(n["check"] == "neighbour" for n in q["not_run"])           # one station polled: the neighbour check says why it did not run


# ---- catalogue ------------------------------------------------------------------------------------------------------
def test_catalog_loads_and_clusters():
    cat = load_catalog()
    assert len(cat) == 580 and sum(s.device_type == RAIN_GAUGE for s in cat.values()) == 267
    cluster = pick_cluster("Mumbai", 9)
    assert len(cluster) == 9 and all(s.city == "Mumbai" for s in cluster)
    assert neighbours(cluster[0], 10.0)  # a dense city: it has neighbours
    with pytest.raises(ValueError):
        pick_cluster("Atlantis", 3)


# ---- client and service (mocked transport) ---------------------------------------------------------------------------
def _client(handler, limit=900):
    return WeatherUnionClient("test-key", "https://example.test/v0", CallBudget(limit), transport=httpx.MockTransport(handler))


def test_client_sends_key_header_and_parses():
    seen = {}

    def handler(req: httpx.Request):
        seen["key"] = req.headers.get("x-zomato-api-key"); seen["id"] = req.url.params["locality_id"]
        return httpx.Response(200, json=payload(0.5, 1.2))

    o = asyncio.run(_client(handler).fetch_locality("ZWL9"))
    assert seen == {"key": "test-key", "id": "ZWL9"} and o.rain_accumulation == 1.2


def test_client_requires_key():
    with pytest.raises(ValueError):
        WeatherUnionClient("", "https://example.test")


def test_service_polls_stores_logs_and_reports(tmp_path):
    stations = pick_cluster("Mumbai", 4)
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.url.params["locality_id"])
        return httpx.Response(200, json=payload(0.0, 0.0))

    log = tmp_path / "raw.jsonl"
    svc = RainfallService(_client(handler), stations, 900.0, "cumulative", str(log))
    assert asyncio.run(svc.poll_once()) == 4 and sorted(calls) == sorted(s.locality_id for s in stations)
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    assert len(rows) == 4 and rows[0]["rain_accumulation"] == 0.0
    rep = svc.station_report(stations[0].locality_id)
    assert rep["quality"]["assessment"] == "OK" and rep["today"]["units_confirmed"] is False
    assert any("NOT documented" in c for c in svc.status()["caveats"])


def test_service_stops_at_budget_and_survives_http_errors():
    stations = pick_cluster("Mumbai", 3)
    svc = RainfallService(_client(lambda r: httpx.Response(200, json=payload(0, 0)), limit=2), stations, 900.0)
    assert asyncio.run(svc.poll_once()) == 2 and "budget" in svc.last_error
    svc2 = RainfallService(_client(lambda r: httpx.Response(500)), stations, 900.0)
    assert asyncio.run(svc2.poll_once()) == 0 and svc2.last_error


def test_api_returns_503_when_feed_is_disabled():
    from fastapi.testclient import TestClient
    from backend.app.api import rainfall as api
    from fastapi import FastAPI

    api._service = None
    app = FastAPI(); app.include_router(api.router)
    r = TestClient(app).get("/api/rainfall/status")
    assert r.status_code == 503 and "WEATHER_UNION_API_KEY" in r.json()["detail"]
