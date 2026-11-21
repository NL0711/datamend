"""The real stream sources (slice S3b) against MOCKED transports only: recorded-shape Open-Meteo and Weather Union answers, a fake MQTT transport.
Never the real APIs, never a broker. The ESP32 source is NOT verified on a real device; these tests only exercise it against a fake."""
import asyncio
import json
import sys
from datetime import datetime, timezone

import httpx
import pytest

from backend.app.rainfall import weather_union as wu
from backend.app.rainfall.providers import OpenMeteoError, WeatherUnionProvider
from backend.app.rainfall.weather_union import BudgetExhausted, CallBudget, WeatherUnionClient
from backend.app.stream.esp32 import Esp32Source, parse_packet
from backend.app.stream.manager import StreamManager
from backend.app.stream.mqtt_transport import MqttUnavailable, PahoTransport
from backend.app.stream.open_meteo import OpenMeteoSource, parse_current
from backend.app.stream.types import BadPacket, SourceNotRunning, SourceStartFailed, StationInfo, UnknownStation
from backend.app.stream.wu_source import WeatherUnionSource, default_client

NOW = datetime(2026, 11, 21, 10, 20, tzinfo=timezone.utc)
A = StationInfo("ZWL005764", "Delhi NCR Sarita Vihar", 28.5318, 77.2940)
B = StationInfo("ZWL008752", "Delhi NCR Faridabad", 28.4609, 77.3048)
C = StationInfo("ZWL005996", "Delhi NCR New Friends Colony", 28.5653, 77.2750)


async def until(check, timeout=5.0):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        got = check()
        if got:
            return got
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached in time")


class Collector:
    def __init__(self):
        self.items = []

    async def __call__(self, reading):
        self.items.append(reading)


# ------------------------------------------------------------------------------------------------ Open-Meteo
def om_item(t="2026-11-21T10:15", temp=24.1, rh=61, p=912.4):
    return {"latitude": 28.5, "longitude": 77.3, "current_units": {"temperature_2m": "°C"},
            "current": {"time": t, "interval": 900, "temperature_2m": temp, "relative_humidity_2m": rh, "surface_pressure": p}}


class OmServer:
    """Mocked Open-Meteo: records every request, answers what the test sets."""

    def __init__(self):
        self.requests = []
        self.answer = lambda n: [om_item() for _ in range(n)]
        self.status = 200

    def transport(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if self.status != 200:
                return httpx.Response(self.status, json={"error": True, "reason": "boom"})
            n = len(request.url.params["latitude"].split(","))
            body = self.answer(n)
            return httpx.Response(200, json=body[0] if n == 1 else body)
        return httpx.MockTransport(handler)


def om_source(server, **kw):
    src = OpenMeteoSource(transport=server.transport(), **kw)
    src.configure([A, B], 0.05)
    return src


def test_open_meteo_mapping_of_a_recorded_shape_answer():
    body = [om_item(), om_item(temp=19.0, rh=None, p=1008.2)]
    readings, notes = parse_current(body, [A, B])
    assert notes == [] and [r.station_id for r in readings] == [A.station_id, B.station_id]
    r0, r1 = readings
    assert (r0.temperature_c, r0.humidity_pct, r0.pressure_hpa, r0.rain_mm, r0.source) == (24.1, 61.0, 912.4, None, "open_meteo")
    assert r0.timestamp == datetime(2026, 11, 21, 10, 15, tzinfo=timezone.utc)
    assert r1.humidity_pct is None and r1.temperature_c == 19.0                     # a null stays null, nothing is filled


def test_open_meteo_all_null_station_gives_no_reading_and_a_wrong_shape_raises():
    readings, notes = parse_current([om_item(), om_item(temp=None, rh=None, p=None)], [A, B])
    assert len(readings) == 1 and "all current values null" in notes[0]
    with pytest.raises(ValueError):
        parse_current([om_item()], [A, B])                     # one answer for two stations
    with pytest.raises(ValueError):
        parse_current({"error": True, "reason": "bad"}, [A])
    r, n = parse_current({"current": {"time": "2026-11-21T10:15", "temperature_2m": "x"}}, [A])
    assert r == [] and n                                       # a non-number is not a value


@pytest.mark.asyncio
async def test_open_meteo_one_multi_location_keyless_request_per_poll():
    server = OmServer()
    src = om_source(server)
    got = Collector()
    await src.poll_once(got)
    assert len(server.requests) == 1
    p = server.requests[0].url.params
    assert p["latitude"] == "28.5318,28.4609" and p["longitude"] == "77.2940,77.3048"
    assert p["current"] == "temperature_2m,relative_humidity_2m,surface_pressure" and "apikey" not in p
    assert str(server.requests[0].url).startswith("https://api.open-meteo.com/v1/forecast")
    assert len(got.items) == 2 and all(r.source == "open_meteo" for r in got.items)
    await src.release()


@pytest.mark.asyncio
async def test_open_meteo_does_not_store_the_same_model_time_twice():
    server = OmServer()
    src = om_source(server)
    got = Collector()
    await src.poll_once(got)
    await src.poll_once(got)                                   # same model time: no new value
    assert len(got.items) == 2
    server.answer = lambda n: [om_item(t="2026-11-21T10:30", temp=25.0) for _ in range(n)]
    await src.poll_once(got)
    assert len(got.items) == 4 and got.items[-1].temperature_c == 25.0
    await src.release()


@pytest.mark.asyncio
async def test_open_meteo_budget_is_respected_and_nothing_is_sent_when_it_is_used_up():
    server = OmServer()
    src = om_source(server, budget=CallBudget(3))
    await src.poll_once(Collector())                           # 2 locations = 2 calls
    with pytest.raises(BudgetExhausted):
        await src.poll_once(Collector())                       # 1 left, 2 needed
    assert len(server.requests) == 1
    await src.release()


@pytest.mark.asyncio
async def test_open_meteo_failed_poll_is_disconnected_never_a_reading_and_it_recovers():
    server = OmServer()
    server.status = 500
    src = om_source(server)
    manager = StreamManager(watch_interval_s=0.02)
    manager.register(src)
    seen = []
    sub = manager.subscribe()
    await manager.select("open_meteo")
    await until(lambda: manager.status().state == "disconnected")
    st = manager.status()
    assert st.packet_count == 0 and "boom" in (st.last_error or "") and st.last_reading_at is None
    server.status = 200
    await until(lambda: manager.status().state == "running" and manager.status().packet_count >= 2)
    while not sub.queue.empty():
        seen.append(sub.queue.get_nowait())
    assert any(f["type"] == "observation" and f["data"]["temperature"] == 24.1 and f["data"]["rain_mm"] is None for f in seen)
    await manager.shutdown()
    assert manager.status().state == "stopped"


@pytest.mark.asyncio
async def test_open_meteo_start_refuses_a_bad_station_set_and_http_errors_are_typed():
    src = OpenMeteoSource(transport=OmServer().transport())
    with pytest.raises(SourceStartFailed):
        await src.start(Collector())                           # no stations configured
    src.configure([], 900, "unknown station 'X'")
    with pytest.raises(SourceStartFailed, match="unknown station"):
        await src.start(Collector())
    server = OmServer()
    server.status = 429
    s2 = om_source(server)
    with pytest.raises(OpenMeteoError):
        await s2.fetch_current()
    await s2.release()


# ------------------------------------------------------------------------------------------------ Weather Union
def wu_answer(temp=None, hum=None, acc=None, inten=None, device="1", wind=3.2, status="200"):
    return {"status": status, "message": "", "device_type": device,
            "locality_weather_data": {"temperature": temp, "humidity": hum, "wind_speed": wind, "wind_direction": 90.0, "rain_intensity": inten,
                                      "rain_accumulation": acc, "aqi_pm_2_point_5": None, "aqi_pm_10": None}}


class WuServer:
    def __init__(self, answers):
        self.answers, self.requests = answers, []

    def client(self, limit=900):
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request.url.params["locality_id"])
            a = self.answers[request.url.params["locality_id"]]
            if isinstance(a, int):
                return httpx.Response(a, json={})
            return httpx.Response(200, json=a)
        return WeatherUnionClient("k" * 12, "https://wu.example/v0", CallBudget(limit), transport=httpx.MockTransport(handler))


def wu_source(server, stations=(A, B, C), mode="per_reading", limit=900, interval=900.0):
    client = server.client(limit)
    src = WeatherUnionSource(client_factory=lambda key: (client, True))
    src.configure(list(stations), interval, "k" * 12, mode)
    return src, client


@pytest.mark.asyncio
async def test_weather_union_stores_what_each_live_response_holds_and_fills_nothing(monkeypatch):
    server = WuServer({A.station_id: wu_answer(24.5, 61.0, acc=0.0, inten=0.0, device="1"),
                       B.station_id: wu_answer(acc=1.2, inten=0.4, device="2"),                        # rain only: temperature and humidity null
                       C.station_id: wu_answer(device="2")})                                            # offline: everything null
    src, client = wu_source(server)
    got = Collector()
    await src.prepare()
    note = await src.poll_once(got)
    by = {r.station_id: r for r in got.items}
    assert set(by) == {A.station_id, B.station_id}                         # the all-null station gives no reading
    a, b = by[A.station_id], by[B.station_id]
    assert (a.temperature_c, a.humidity_pct, a.rain_mm, a.pressure_hpa, a.source) == (24.5, 61.0, 0.0, None, "weather_union")
    assert (b.temperature_c, b.humidity_pct, b.rain_mm, b.pressure_hpa) == (None, None, 1.2, None)       # no fill, no pressure, ever
    assert src.last_fields[A.station_id] == ["temperature", "humidity", "rain_accumulation", "rain_intensity"]
    assert src.last_fields[C.station_id] == [] and note is None
    assert client.budget.used == 3 == len(server.requests)


@pytest.mark.asyncio
async def test_weather_union_cumulative_rain_is_the_increase_and_the_first_poll_stores_none():
    server = WuServer({A.station_id: wu_answer(20.0, 50.0, acc=2.0)})
    src, client = wu_source(server, stations=(A,), mode="cumulative")
    got = Collector()
    await src.prepare()
    await src.poll_once(got)
    server.answers[A.station_id] = wu_answer(20.0, 50.0, acc=2.5)
    await src.poll_once(got)
    server.answers[A.station_id] = wu_answer(20.0, 50.0, acc=0.3)           # a drop is a reset: the new value counts
    await src.poll_once(got)
    assert [r.rain_mm for r in got.items] == [None, 0.5, 0.3]


@pytest.mark.asyncio
async def test_weather_union_budget_is_respected_and_the_interval_never_exceeds_it():
    server = WuServer({s.station_id: wu_answer(20.0, 50.0, acc=0.1) for s in (A, B, C)})
    src, client = wu_source(server, limit=2)
    await src.prepare()
    assert src.interval_s >= 86400 * 3 / 2                                  # 3 stations on 2 calls a day: one round a day at most
    got = Collector()
    note = await src.poll_once(got)
    assert client.budget.used == 2 and len(server.requests) == 2 and len(got.items) == 2
    assert "budget" in note
    with pytest.raises(RuntimeError, match="budget"):
        await src.poll_once(got)                                            # nothing answered: the round fails, no call was sent
    assert len(server.requests) == 2


@pytest.mark.asyncio
async def test_weather_union_all_stations_failing_is_disconnected_and_emits_nothing():
    server = WuServer({A.station_id: 500, B.station_id: 500})
    src, _ = wu_source(server, stations=(A, B), interval=0.05)
    manager = StreamManager(watch_interval_s=0.02)
    manager.register(src)
    await manager.select("weather_union")
    await until(lambda: manager.status().state == "disconnected")
    assert manager.status().packet_count == 0 and "HTTP 500" in manager.status().last_error
    await manager.shutdown()


@pytest.mark.asyncio
async def test_weather_union_needs_a_key_and_catalogue_stations():
    src = WeatherUnionSource(client_factory=lambda key: (None, False))
    src.configure([A], 900, "", "cumulative")
    with pytest.raises(SourceStartFailed, match="key"):
        await src.start(Collector())
    src.configure([StationInfo("KTLX", "sim", 35.0, -97.0)], 900, "k" * 12, "cumulative")
    with pytest.raises(SourceStartFailed, match="not Weather Union"):
        await src.start(Collector())


def test_weather_union_shares_one_budget_and_the_running_feeds_client(monkeypatch):
    assert wu.shared_budget(900) is wu.shared_budget(850) and wu.shared_budget(850).limit == 850
    wu.shared_budget(900)
    from backend.app.api import rainfall as rainfall_api
    feed_client = WeatherUnionClient("k" * 12, "https://wu.example/v0", wu.shared_budget(900))

    class Svc:
        provider = WeatherUnionProvider(feed_client)
    monkeypatch.setattr(rainfall_api, "_service", Svc())
    client, owned = default_client("k" * 12)
    assert client is feed_client and owned is False                          # shared outright, not ours to close
    monkeypatch.setattr(rainfall_api, "_service", None)
    client2, owned2 = default_client("k" * 12)
    assert owned2 is True and client2.budget is wu.shared_budget(900)


# ------------------------------------------------------------------------------------------------ ESP32 / MQTT (FAKE transport, NOT a real device)
class FakeTransport:
    """TEST FAKE of the MQTT transport."""
    instances = []

    def __init__(self, fail=False):
        self.fail, self.filters, self.connected_with, self.closed = fail, [], None, False
        self.on_message = self.on_connection = None
        FakeTransport.instances.append(self)

    def set_handlers(self, on_message, on_connection):
        self.on_message, self.on_connection = on_message, on_connection

    async def connect(self, host, port, username, password, tls):
        if self.fail:
            raise ConnectionRefusedError("broker down")
        self.connected_with = (host, port, username, password, tls)

    async def subscribe(self, filters):
        self.filters = list(filters)

    async def disconnect(self):
        self.closed = True

    def deliver(self, topic, payload):
        self.on_message(topic, payload if isinstance(payload, bytes) else json.dumps(payload).encode())


def esp_source(host="broker.example", fail_first=False):
    FakeTransport.instances = []
    made = []

    def factory():
        t = FakeTransport(fail=fail_first and not made)
        made.append(t)
        return t
    src = Esp32Source(transport_factory=factory, retry_s=0.02)
    src.configure(["ESP32-001", "ESP32-002"], 12.97, 77.59, 60.0, host, 1883, "skyguard/aws", "user", "secret-pass", False)
    return src, made


def test_parse_packet_keeps_nulls_rejects_bad_values_and_never_invents():
    r = parse_packet("ESP32-001", {"temperature_c": 21.5, "humidity": 55, "pressure_hpa": None, "timestamp": "2026-11-21T10:00:00Z"}, NOW)
    assert (r.temperature_c, r.humidity_pct, r.pressure_hpa, r.rain_mm, r.source) == (21.5, 55.0, None, None, "esp32")
    assert r.timestamp == datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
    assert parse_packet("S", {"rain_mm": 0.2}, NOW).timestamp == NOW                 # no timestamp: the time of receipt
    assert parse_packet("S", {"temperature_c": 999.0}, NOW).temperature_c == 999.0   # out of range is kept as sent for the checks to judge
    for bad in ([], {"temperature_c": "21.5"}, {"temperature_c": True}, {"temperature_c": float("inf")}, {}, {"pressure_hpa": None}, {"temperature_c": 1, "timestamp": "yesterday"}):
        with pytest.raises(BadPacket):
            parse_packet("S", bad, NOW)


@pytest.mark.asyncio
async def test_esp32_subscribes_to_the_topics_and_stores_telemetry_as_sent():
    src, made = esp_source()
    got = Collector()
    await src.start(got)
    await until(lambda: src.status().state == "running")
    t = made[0]
    assert t.filters == ["skyguard/aws/+/telemetry", "skyguard/aws/+/heartbeat"] and t.connected_with == ("broker.example", 1883, "user", "secret-pass", False)
    t.deliver("skyguard/aws/ESP32-001/telemetry", {"temperature_c": 30.1, "humidity_pct": None, "pressure_hpa": 1001.0})
    t.deliver("skyguard/aws/ESP32-001/heartbeat", b"alive")
    await until(lambda: got.items and "ESP32-001" in src.heartbeats)
    r = got.items[0]
    assert (r.station_id, r.temperature_c, r.humidity_pct, r.pressure_hpa, r.source) == ("ESP32-001", 30.1, None, 1001.0, "esp32")
    assert len(got.items) == 1                                                       # the heartbeat made no reading
    assert [s.station_id for s in src.stations()] == ["ESP32-001", "ESP32-002"]
    await src.stop()
    assert src.status().state == "stopped" and t.closed


@pytest.mark.asyncio
async def test_esp32_refuses_unknown_stations_bad_topics_and_malformed_packets():
    src, made = esp_source()
    got = Collector()
    await src.start(got)
    await until(lambda: src.status().state == "running")
    t = made[0]
    t.deliver("skyguard/aws/NOPE/telemetry", {"temperature_c": 1.0})
    t.deliver("other/ESP32-001/telemetry", {"temperature_c": 1.0})
    t.deliver("skyguard/aws/ESP32-001/telemetry", b"{not json")
    t.deliver("skyguard/aws/ESP32-001/telemetry", {"temperature_c": "hot"})
    t.deliver("skyguard/aws/ESP32-001/telemetry", {})
    await until(lambda: src.rejected == 5)
    assert got.items == [] and src.accepted == 0
    await src.stop()


@pytest.mark.asyncio
async def test_esp32_connection_loss_is_disconnected_then_it_reconnects_and_a_refused_connect_is_reported():
    src, made = esp_source()
    await src.start(Collector())
    await until(lambda: src.status().state == "running")
    made[0].on_connection(False, "keepalive timeout")
    await until(lambda: len(made) >= 2 and src.status().state == "running")          # reconnected on a new transport
    assert made[0].closed
    await src.stop()
    src2, made2 = esp_source(fail_first=True)
    await src2.start(Collector())
    await until(lambda: "broker down" in (src2.status().last_error or ""))
    assert src2.status().state == "disconnected"
    await until(lambda: src2.status().state == "running")                            # the retry worked
    await src2.stop()


@pytest.mark.asyncio
async def test_esp32_without_a_broker_runs_for_virtual_packets_only_and_checks_them():
    src = Esp32Source()
    src.configure(["ESP32-001"], None, None, 60.0, "", 1883, "skyguard/aws", "", "", False)
    with pytest.raises(SourceNotRunning):
        await src.inject_packet({"temperature_c": 1.0})
    got = Collector()
    await src.start(got)
    assert src.status().state == "running" and src.stations() == []                  # no coordinates: not drawn on the map
    r = await src.inject_packet({"temperature_c": 22.0})                             # one station: its id is implied
    assert r.station_id == "ESP32-001" and got.items == [r] and src.virtual == 1
    with pytest.raises(UnknownStation):
        await src.inject_packet({"station_id": "ELSEWHERE", "temperature_c": 1.0})
    with pytest.raises(BadPacket):
        await src.inject_packet({"station_id": "ESP32-001"})
    with pytest.raises(BadPacket):
        await src.inject_packet([1, 2])
    await src.stop()


@pytest.mark.asyncio
async def test_the_real_transport_reports_a_missing_paho_instead_of_crashing(monkeypatch):
    monkeypatch.setitem(sys.modules, "paho", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", None)
    with pytest.raises(MqttUnavailable, match="paho-mqtt"):
        await PahoTransport().connect("h", 1883, "", "", False)
