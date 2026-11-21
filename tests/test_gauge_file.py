"""The gauge file: complete rain days only, per station, with coordinates; no network, no quota (a stub service over generated readings)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.rainfall.gauges import gauge_days, gauge_file
from backend.app.rainfall.weather_union import RainObservation

UTC = timezone.utc
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def full_day(sid, start, per_step=0.1, steps=95, accum_from=0.0, status="OK"):
    """96 cumulative readings, 15 minutes apart, from ``start`` (UTC) to 02:45 the next day, +per_step each time (the 03:00 reading would
    belong to the next rain day, so it is not part of this one)."""
    return [RainObservation(sid, start + timedelta(minutes=15 * i), 1, 0.0, accum_from + per_step * i, status) for i in range(steps + 1)]


DAY1 = datetime(2026, 3, 5, 3, 0, tzinfo=UTC)                 # rain day labelled 2026-03-06 starts at 03 UTC on the 5th


def test_complete_days_become_totals_and_gaps_are_left_out():
    complete = full_day("Z1", DAY1)                                                 # 96 steps of 0.1: a 9.5 mm day
    gappy = [o for i, o in enumerate(full_day("Z1", DAY1 + timedelta(days=1))) if not 20 <= i <= 60]    # a 10 hour hole
    got, left = gauge_days(complete + gappy, "cumulative", NOW, keep_days=90)
    assert got == {"2026-03-06": 9.5} and left == {"incomplete_days": 1, "no_usable_reading": 0}


def test_offline_readings_and_empty_input_give_nothing():
    off = full_day("Z1", DAY1, status="NO_RAIN_FIELDS")
    assert gauge_days(off, "cumulative", NOW, 90) == ({}, {"incomplete_days": 0, "no_usable_reading": 0})
    assert gauge_days([], "per_reading", NOW, 90)[0] == {}


def test_only_the_newest_days_are_kept():
    days = [o for k in range(4) for o in full_day("Z1", DAY1 - timedelta(days=3 - k), accum_from=100.0 * k)]
    got, _ = gauge_days(days, "cumulative", NOW, keep_days=2)
    assert list(got) == ["2026-03-05", "2026-03-06"]


class Store:
    def __init__(self, rows): self.rows, self.limits = rows, []
    async def recent(self, sid, limit):
        self.limits.append(limit)
        return self.rows.get(sid, [])
    def state(self):
        return SimpleNamespace(as_dict=lambda: {"available": True, "backend": "stub", "retention_days": 90})


def service(stations, store, mode="cumulative"):
    return SimpleNamespace(stations=stations, store=store, mode=mode, history={})


def st(place, lat, lon):
    return SimpleNamespace(place=place, city="Bengaluru", latitude=lat, longitude=lon)


@pytest.mark.asyncio
async def test_the_file_carries_coordinates_modes_and_what_was_left_out():
    store = Store({"Z1": full_day("Z1", DAY1), "Z2": [o for i, o in enumerate(full_day("Z2", DAY1)) if i < 10]})
    svc = service({"Z1": st("Indiranagar", 12.97, 77.64), "Z2": st("Koramangala", 12.93, 77.62), "Z3": st("Whitefield", 12.97, 77.75)}, store)
    f = await gauge_file(svc, days=30, now=NOW)
    assert f["stations_polled"] == 3 and f["stations_with_days"] == 1 and f["accumulation_mode"] == "cumulative"
    (g,) = f["gauges"]
    assert g["station"] == "Z1" and g["lat"] == 12.97 and g["lon"] == 77.64 and g["days"] == {"2026-03-06": 9.5}
    assert set(f["left_out"]) == {"Z2", "Z3"} and "ASSUMED" in f["units"] and f["history_kept"]["available"] is True
    assert store.limits == [30 * 300] * 3                                           # asked for enough readings, not a fixed handful


@pytest.mark.asyncio
async def test_without_a_store_the_held_memory_is_used():
    svc = service({"Z1": st("Indiranagar", 12.97, 77.64)}, None)
    svc.history = {"Z1": full_day("Z1", DAY1)}
    f = await gauge_file(svc, days=5, now=NOW)
    assert f["gauges"][0]["days"] == {"2026-03-06": 9.5} and f["history_kept"] is None


@pytest.mark.asyncio
async def test_the_route_answers_503_when_the_feed_is_off(async_client):
    r = await async_client.get("/api/rainfall/gauges")
    assert r.status_code == 503
    assert (await async_client.get("/api/rainfall/gauges", params={"days": 0})).status_code == 422
