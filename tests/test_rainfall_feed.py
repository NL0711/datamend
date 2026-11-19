"""Tests of the live rain-gauge path (backend/app/rainfall). Generated data and a mocked HTTP transport only: no network, no API quota."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from backend.app.rainfall.catalog import RAIN_GAUGE, load_catalog, neighbours
from backend.app.rainfall.daily import DailyAccumulator, rain_day, rain_day_bounds, total_for_day
from backend.app.rainfall.scorer import score_reading
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
def test_rain_day_is_03_to_03_utc():
    assert rain_day(datetime(2026, 11, 19, 2, 59, tzinfo=timezone.utc)) == date(2026, 11, 18)
    assert rain_day(datetime(2026, 11, 19, 3, 0, tzinfo=timezone.utc)) == date(2026, 11, 19)
    start, end = rain_day_bounds(date(2026, 11, 19))
    assert (end - start) == timedelta(days=1) and start.hour == 3
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


# ---- scorer ---------------------------------------------------------------------------------------------------------
def test_scorer_ok_for_quiet_dry_station():
    r = score_reading([obs(i) for i in range(5)])
    assert r.assessment == "OK" and r.score == 0.0 and "not a trained model" in r.method


def test_scorer_no_data_when_station_offline():
    r = score_reading([obs(0), obs(1, None, None, status="NO_RAIN_FIELDS")])
    assert r.assessment == "NO_DATA"


def test_scorer_flags_negative_and_implausible_intensity():
    assert score_reading([obs(0), obs(1, -1.0, 0.0)]).assessment == "SUSPECT"
    r = score_reading([obs(0), obs(1, 900.0, 0.0)])
    assert r.assessment == "SUSPECT" and r.reasons[0]["check"] == "INTENSITY_IMPLAUSIBLE"


def test_scorer_flags_accumulation_jump_but_not_a_normal_increase():
    assert score_reading([obs(0, accum=0.0), obs(1, 1.0, 2.0)]).assessment == "OK"
    r = score_reading([obs(0, accum=0.0), obs(1, 1.0, 80.0)])
    assert r.assessment == "SUSPECT" and any(x["check"] == "ACCUMULATION_JUMP" for x in r.reasons)


def test_scorer_counter_reset_alone_is_not_suspect():
    r = score_reading([obs(0, accum=5.0), obs(1, 0.0, 0.0)])
    assert r.assessment == "OK" and r.reasons[0]["check"] == "COUNTER_RESET"


def test_scorer_flags_frozen_nonzero_intensity():
    r = score_reading([obs(i, 2.0, float(i)) for i in range(6)])
    assert any(x["check"] == "FROZEN_INTENSITY" for x in r.reasons) and r.assessment == "SUSPECT"
    assert score_reading([obs(i, 0.0, 0.0) for i in range(6)]).assessment == "OK"  # frozen at zero is just a dry day


def test_scorer_flags_intensity_without_counter_movement():
    r = score_reading([obs(i, 1.0 + i * 0.1, 3.0) for i in range(4)])
    assert any(x["check"] == "INTENSITY_ACCUMULATION_MISMATCH" for x in r.reasons)


def test_isolated_wet_is_uncertain_not_a_fault():
    me = [obs(0), obs(1, 3.0, 1.0)]
    buddies = {f"B{i}": [obs(0, sid=f"B{i}"), obs(1, 0.0, 0.0, sid=f"B{i}")] for i in range(4)}
    r = score_reading(me, buddies)
    assert r.assessment == "UNCERTAIN" and r.n_neighbours_used == 4 and 0 < r.score < 0.5


def test_buddy_check_needs_enough_neighbours_and_agreement():
    me = [obs(0), obs(1, 3.0, 1.0)]
    two = {f"B{i}": [obs(0), obs(1, 0.0, 0.0)] for i in range(2)}
    assert score_reading(me, two).assessment == "OK"
    mixed = {f"B{i}": [obs(0), obs(1, 2.0 if i < 2 else 0.0, 1.0)] for i in range(4)}
    assert score_reading(me, mixed).assessment == "OK"


def test_score_is_bounded_and_combines_evidence():
    r = score_reading([obs(0, accum=0.0), obs(1, 900.0, 80.0)])
    assert 0.9 < r.score <= 1.0
    with pytest.raises(ValueError):
        score_reading([])


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
