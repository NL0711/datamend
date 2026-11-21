"""Feed history (rainfall/history.py): a store apart from the runs database. Generated readings and throwaway SQLite files only."""
from __future__ import annotations

import asyncio
import httpx
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.rainfall.history import SqlFeedHistory, build_feed_history
from backend.app.rainfall.service import RainfallService, pick_cluster
from backend.app.rainfall.weather_union import CallBudget, RainObservation, WeatherUnionClient

T0 = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)


def obs(i, sid="ZWL1", accum=0.0, status="OK"):
    return RainObservation(sid, T0 + timedelta(minutes=15 * i), 2, 0.0, accum, status)


def store(tmp_path, days=90) -> SqlFeedHistory:
    return SqlFeedHistory("sqlite+aiosqlite:///" + (tmp_path / "h.db").as_posix(), days)


def run(coro):
    return asyncio.run(coro)


def test_append_then_recent_returns_oldest_first_and_keeps_the_rain_fields():
    async def go(tmp_path):
        s = store(tmp_path)
        await s.append([obs(i, accum=i * 0.5) for i in range(5)])
        got = await s.recent("ZWL1", 3)
        await s.close()
        return got, s.state()
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        got, state = run(go(pathlib.Path(d)))
    assert [o.rain_accumulation for o in got] == [1.0, 1.5, 2.0]            # the newest 3, oldest first
    assert got[0].observed_at.tzinfo is not None and got[0].device_type == 2 and got[0].raw == {}      # no raw response is kept
    assert state.available and state.backend == "local SQLite file" and state.retention_days == 90


def test_appending_the_same_reading_twice_stores_it_once(tmp_path):
    async def go():
        s = store(tmp_path)
        await s.append([obs(0), obs(1)])
        await s.append([obs(1), obs(2)])
        n = len(await s.recent("ZWL1", 10))
        await s.close()
        return n
    assert run(go()) == 3


def test_readings_are_kept_per_station(tmp_path):
    async def go():
        s = store(tmp_path)
        await s.append([obs(0, "A"), obs(0, "B"), obs(1, "A")])
        a, b = await s.recent("A", 10), await s.recent("B", 10)
        await s.close()
        return len(a), len(b)
    assert run(go()) == (2, 1)


def test_prune_deletes_only_readings_older_than_the_retention_window(tmp_path):
    async def go():
        s = store(tmp_path, days=90)
        now = datetime.now(timezone.utc)
        old = RainObservation("A", now - timedelta(days=91), 2, 0.0, 1.0)
        edge = RainObservation("A", now - timedelta(days=89), 2, 0.0, 2.0)
        await s.append([old, edge])                                     # the first append also prunes
        after_append = [o.rain_accumulation for o in await s.recent("A", 10)]
        removed = await s.prune(now + timedelta(days=2))                # two days later the 89-day-old reading is past the window
        after_prune = await s.recent("A", 10)
        await s.close()
        return after_append, removed, after_prune
    after_append, removed, after_prune = run(go())
    assert after_append == [2.0] and removed == 1 and after_prune == []


def test_an_unreachable_store_is_reported_and_never_raises(tmp_path):
    async def go():
        s = SqlFeedHistory("sqlite+aiosqlite:///" + (tmp_path / "no" / "such" / "dir" / "h.db").as_posix())
        await s.append([obs(0)])                                       # must not raise
        recent = await s.recent("ZWL1", 5)
        await s.close()
        return recent, s.state()
    recent, state = run(go())
    assert recent == [] and state.available is False and state.reason


def test_a_store_that_comes_back_reports_available_again(tmp_path):
    async def go():
        folder = tmp_path / "later"
        s = SqlFeedHistory("sqlite+aiosqlite:///" + (folder / "h.db").as_posix())
        await s.append([obs(0)])
        down = s.state().available
        folder.mkdir()
        await s.append([obs(1)])
        up = s.state().available
        await s.close()
        return down, up
    assert run(go()) == (False, True)


def test_build_feed_history_uses_a_local_file_when_no_url_is_set(tmp_path):
    s = build_feed_history("", 30, (tmp_path / "data" / "feed.db").as_posix())
    assert s.retention_days == 30 and s.state().backend == "local SQLite file" and (tmp_path / "data").is_dir()
    run(s.close())


def test_build_feed_history_takes_a_postgres_url_without_connecting():
    s = build_feed_history("postgresql+asyncpg://u:p@db.example.com:5432/tsdb?ssl=require", 90, "unused.db")
    assert s._dialect == "postgresql" and s.state().available is False       # nothing contacted yet
    run(s.close())


# ---- the live service uses it ---------------------------------------------------------------------------------------
def _client(handler, limit=900):
    return WeatherUnionClient("key", "https://example.test", CallBudget(limit), transport=httpx.MockTransport(handler))


def _payload(accum):
    return {"status": "200", "message": "", "device_type": 2,
            "locality_weather_data": {"rain_intensity": 0, "rain_accumulation": accum}}


def test_polled_readings_are_stored_and_a_restarted_service_restores_them(tmp_path):
    stations = pick_cluster("Mumbai", 2)

    async def go():
        s = store(tmp_path)
        svc = RainfallService(_client(lambda r: httpx.Response(200, json=_payload(1.0))), stations, 900.0, "cumulative", store=s)
        await svc.poll_once()
        await svc.poll_once()
        assert s.state().available
        s2 = store(tmp_path)                                            # a restart: new service, empty memory, same store
        svc2 = RainfallService(_client(lambda r: httpx.Response(200, json=_payload(1.0))), stations, 900.0, "cumulative", store=s2)
        assert all(len(h) == 0 for h in svc2.history.values())
        loaded = await svc2.restore_history()
        await s.close()
        await s2.close()
        return loaded, svc2.status()["history"], {sid: len(h) for sid, h in svc2.history.items()}
    loaded, hist, per_station = run(go())
    assert loaded == 4 and all(n == 2 for n in per_station.values())
    assert hist["available"] is True and hist["retention_days"] == 90


def test_a_failing_store_does_not_stop_polling(tmp_path):
    stations = pick_cluster("Mumbai", 2)
    broken = SqlFeedHistory("sqlite+aiosqlite:///" + (tmp_path / "x" / "y" / "h.db").as_posix())

    async def go():
        svc = RainfallService(_client(lambda r: httpx.Response(200, json=_payload(0.0))), stations, 900.0, "cumulative", store=broken)
        n = await svc.poll_once()
        status = svc.status()["history"]
        await broken.close()
        return n, status
    n, status = run(go())
    assert n == 2 and status["available"] is False and status["reason"]       # the feed carried on from memory


def test_status_has_no_history_entry_without_a_store():
    svc = RainfallService(_client(lambda r: httpx.Response(200, json=_payload(0))), pick_cluster("Mumbai", 1), 900.0)
    assert svc.status()["history"] is None
