"""Telemetry stream core (slice S3a): the source interface, the manager's states and fan-out, the seeded simulator and each injected fault kind,
and the checks' honesty about what has no checks. No database, no network; fakes live in tests/test_stream_fakes.py and are labelled."""
import asyncio
from datetime import timedelta

import pytest

from backend.app.stream import frames
from backend.app.stream.manager import StreamManager
from backend.app.stream.scoring import NO_CHECKS, score_reading
from backend.app.stream.sim_faults import CORRUPT_VALUE, FAULT_KINDS
from backend.app.stream.sim_physics import SIM_STATIONS
from backend.app.stream.simulator import SimulatorSource
from backend.app.stream.source import TelemetrySource
from backend.app.stream.types import BadSimulatorConfig, SimulatorBusy, SourceStartFailed, UnknownSource, UnknownStation
from tests.test_stream_fakes import T0, FakeClock, FakeSource, reading


def drain(sub):
    out = []
    while not sub.queue.empty():
        out.append(sub.queue.get_nowait())
    return out


def kinds(frames_):
    return [f["type"] for f in frames_]


# ---------------------------------------------------------------------------------------------------- interface
def test_the_simulator_and_the_fake_both_satisfy_the_source_interface():
    assert isinstance(SimulatorSource(), TelemetrySource)
    assert isinstance(FakeSource(), TelemetrySource)


# ---------------------------------------------------------------------------------------------------- manager states
@pytest.mark.asyncio
async def test_state_goes_stopped_running_stale_running_disconnected_stopped_and_nothing_is_fabricated():
    clock, src = FakeClock(), FakeSource(interval=2.0)
    m = StreamManager(clock=clock, stale_factor=3.0, min_stale_s=1.0)
    m.register(src)
    sub = m.subscribe()
    assert m.status().state == "stopped" and m.status().source_id is None

    await m.select("fake")
    assert m.status().state == "running" and m.status().stale_after_s == 6.0     # 3 x the source's own interval
    await src.push(reading(temperature_c=20.0))
    assert m.status().packet_count == 1 and m.status().last_reading_at == clock.now

    clock.advance(5.9)
    assert m.refresh_state().state == "running"
    clock.advance(0.2)                                                           # 6.1 s of silence
    st = m.refresh_state()
    assert st.state == "stale" and st.stale_since == T0 + timedelta(seconds=6)
    assert st.packet_count == 1                                                  # silence produced no reading

    await src.push(reading(at=clock.now, temperature_c=21.0))
    assert m.status().state == "running" and m.status().stale_since is None

    src.drop_connection("broker went away")
    st = m.refresh_state()
    assert st.state == "disconnected" and st.last_error == "broker went away" and st.stale_since is None

    await m.stop()
    assert m.status().state == "stopped" and src.state == "stopped"

    frames_ = drain(sub)
    assert [f["data"]["state"] for f in frames_ if f["type"] == "status"] == ["running", "stale", "running", "disconnected", "stopped"]
    assert kinds(frames_).count("observation") == 2          # exactly the two readings the source pushed, nothing between them


@pytest.mark.asyncio
async def test_a_source_that_never_delivers_goes_stale_from_its_start_not_silently_running():
    clock, src = FakeClock(), FakeSource(interval=None)
    m = StreamManager(clock=clock, min_stale_s=10.0)
    m.register(src)
    await m.select("fake")
    clock.advance(10.5)
    st = m.status()
    assert st.state == "stale" and st.last_reading_at is None and st.packet_count == 0 and st.stale_since == T0 + timedelta(seconds=10)


@pytest.mark.asyncio
async def test_select_switches_sources_and_stops_the_previous_one():
    a, b = FakeSource("a"), FakeSource("b")
    m = StreamManager()
    m.register(a)
    m.register(b)
    await m.select("a")
    await m.select("b")
    assert a.state == "stopped" and a.stops == 1 and b.state == "running" and m.active is b
    assert m.status().source_id == "b" and m.status().packet_count == 0         # counters belong to the active source's run
    with pytest.raises(UnknownSource):
        await m.select("nope")
    assert m.active is b and b.state == "running"                                # a refused switch changes nothing


@pytest.mark.asyncio
async def test_a_source_that_cannot_start_is_reported_not_hidden():
    bad = FakeSource("bad", fail_start=True)
    m = StreamManager()
    m.register(bad)
    with pytest.raises(SourceStartFailed):
        await m.select("bad")
    assert m.status().last_error and "transport refused" in m.status().last_error and m.status().state == "stopped"


@pytest.mark.asyncio
async def test_start_after_stop_restarts_the_active_source():
    src = FakeSource()
    m = StreamManager()
    m.register(src)
    assert (await m.start()).state == "stopped"                                  # nothing selected: nothing to start
    await m.select("fake")
    await m.stop()
    assert (await m.start()).state == "running" and src.starts == 2


# ---------------------------------------------------------------------------------------------------- fan-out
@pytest.mark.asyncio
async def test_two_subscribers_get_the_same_frames_in_order_and_unsubscribing_stops_delivery():
    src = FakeSource()
    m = StreamManager()
    m.register(src)
    s1, s2 = m.subscribe(), m.subscribe()
    await m.select("fake")
    for i in range(3):
        await src.push(reading(at=T0 + timedelta(seconds=i), temperature_c=float(i)))
    f1, f2 = drain(s1), drain(s2)
    assert f1 == f2 and kinds(f1) == ["status", "observation", "observation", "observation"]
    assert [f["data"]["temperature"] for f in f1 if f["type"] == "observation"] == [0.0, 1.0, 2.0]
    m.unsubscribe(s2)
    await src.push(reading(temperature_c=9.0))
    assert len(drain(s1)) == 1 and drain(s2) == [] and m.status().subscribers == 1


@pytest.mark.asyncio
async def test_a_slow_subscriber_loses_its_oldest_frames_and_does_not_hold_back_the_others():
    src = FakeSource()
    m = StreamManager(queue_size=3)
    m.register(src)
    slow = m.subscribe()
    await m.select("fake")
    fast_seen = []
    fast = m.subscribe()
    for i in range(6):
        await src.push(reading(at=T0 + timedelta(seconds=i), temperature_c=float(i)))
        fast_seen += drain(fast)
    assert [f["data"]["temperature"] for f in fast_seen if f["type"] == "observation"] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    kept = [f["data"]["temperature"] for f in drain(slow) if f["type"] == "observation"]
    assert kept == [3.0, 4.0, 5.0] and slow.dropped == 4          # 1 status + 6 readings pushed into a queue of 3


@pytest.mark.asyncio
async def test_a_processor_failure_still_passes_the_reading_on_marked_unstored():
    async def broken(_):
        raise RuntimeError("database down")
    src = FakeSource()
    m = StreamManager(processor=broken)
    m.register(src)
    sub = m.subscribe()
    await m.select("fake")
    await src.push(reading(temperature_c=20.0))
    obs = [f for f in drain(sub) if f["type"] == "observation"]
    assert len(obs) == 1 and obs[0]["data"]["stored"] is False and obs[0]["data"]["validation_status"] == NO_CHECKS


def test_a_status_frame_has_no_station_id_so_the_dashboard_client_cannot_mistake_it_for_a_reading():
    f = frames.status_frame(StreamManager().status().as_dict())
    assert f["type"] == "status" and "station_id" not in f and "temperature" not in f and "anomaly_score" not in f


# ---------------------------------------------------------------------------------------------------- checks honesty
def test_temperature_pressure_humidity_get_no_checks_no_score_no_verdict():
    out = score_reading(reading(temperature_c=20.0, pressure_hpa=1010.0, humidity_pct=50.0))
    assert out.status == NO_CHECKS and out.rule_score is None and out.severity is None and out.hits == [] and not out.ran and not out.flagged
    assert {n["check"] for n in out.not_run} == {"temperature", "pressure", "humidity"} and all("S4" in n["reason"] for n in out.not_run)
    data = frames.observation_data(reading(temperature_c=20.0), out)
    assert data["validation_status"] == NO_CHECKS and data["checks_run"] is False
    assert not {"anomaly_score", "is_anomaly", "severity", "classification", "reason"} & set(data)


def test_a_rain_reading_goes_through_the_rainfall_catalogue():
    ok = score_reading(reading(rain_mm=1.2))
    assert ok.status == "OK" and ok.rule_score == 0.0 and ok.hits == [] and ok.ran
    bad = score_reading(reading(rain_mm=-4.0))
    assert bad.status == "SUSPECT" and bad.flagged and bad.hits[0]["check"] == "negative_value" and bad.rule_score and bad.rule_score > 0.9
    assert any(n["check"] == "neighbour" for n in bad.not_run)           # the neighbour check says why it did not run
    assert bad.hits[0]["evidence"]["observed"]["basis"] == "assumed"      # the unit of a stream value is not confirmed


# ---------------------------------------------------------------------------------------------------- simulator
def run_ticks(sim, n, step_s=60):
    out = []
    for i in range(n):
        out.append(sim.tick(T0 + timedelta(seconds=i * step_s)))
    return out


def test_the_simulator_is_deterministic_for_a_seed_and_differs_between_seeds():
    a, b, c = SimulatorSource(seed=7), SimulatorSource(seed=7), SimulatorSource(seed=8)
    ra, rb, rc = run_ticks(a, 20), run_ticks(b, 20), run_ticks(c, 20)
    assert ra == rb and ra != rc
    a.reset()
    assert run_ticks(a, 20) == ra                                         # a new run starts from the seed again


def test_simulated_readings_are_plausible_labelled_with_their_source_and_never_carry_rain():
    sim = SimulatorSource()
    flat = [r for tick in run_ticks(sim, 200, step_s=600) for r in tick]
    assert {r.station_id for r in flat} == {s.station_id for s in SIM_STATIONS}
    assert all(r.source == "simulator" and r.injected is None and r.rain_mm is None for r in flat)
    assert all(-30 < r.temperature_c < 60 and 900 < r.pressure_hpa < 1060 and 5 <= r.humidity_pct <= 100 for r in flat)


def test_stations_have_their_own_diurnal_phase():
    sim = SimulatorSource(noise_scale=0.0)
    peak = {}
    series = {s.station_id: [] for s in SIM_STATIONS}
    for h in range(48):
        for r in sim.tick(T0 + timedelta(hours=h)):
            series[r.station_id].append(r.temperature_c)
    for sid, vals in series.items():
        peak[sid] = max(range(24), key=lambda i: vals[i])                # hour of the daily maximum
    assert peak["KTLX"] != peak["KOKX"] != peak["KATX"] and len(set(peak.values())) >= 3
    assert peak["KOKX"] < peak["KATX"] or peak["KOKX"] > peak["KATX"]


def twin(**kw):
    """Two identical noise-free simulators: one clean, one that gets an injection, to compare tick by tick."""
    return SimulatorSource(noise_scale=0.0, **kw), SimulatorSource(noise_scale=0.0, **kw)


def pick(tick, sid="KTLX"):
    return next(r for r in tick if r.station_id == sid)


def test_each_fault_kind_is_visible_in_the_stream_and_labelled():
    assert set(FAULT_KINDS) == {"SPIKE", "DRIFT", "FROZEN", "DROPOUT", "NOISE_BURST", "MULTIVARIATE_INCONSISTENCY", "METEOROLOGICAL_EXTREME", "DATA_CORRUPTION"}

    def compare(kind, steps=3, **inj):
        clean, hit = twin()
        hit.inject(kind, "KTLX", duration_steps=steps, **inj)
        rows = []
        for i in range(steps + 1):
            t = T0 + timedelta(hours=i)
            rows.append((pick(clean.tick(t)), pick(hit.tick(t))))
        return rows

    # SPIKE: +25 C on the first step, halving with decay, gone after the duration
    rows = compare("SPIKE", parameter="temperature", magnitude=25.0, decay=True)
    assert rows[0][1].temperature_c == pytest.approx(rows[0][0].temperature_c + 25.0, abs=0.01) and rows[0][1].injected == "SPIKE"
    assert rows[1][1].temperature_c == pytest.approx(rows[1][0].temperature_c + 12.5, abs=0.01)
    assert rows[3][1].temperature_c == rows[3][0].temperature_c and rows[3][1].injected is None

    # DRIFT: a linear ramp that reaches the magnitude on the last step
    rows = compare("DRIFT", steps=4, parameter="pressure", magnitude=8.0)
    offs = [round(h.pressure_hpa - c.pressure_hpa, 2) for c, h in rows[:4]]
    assert offs == [2.0, 4.0, 6.0, 8.0] and rows[4][1].injected is None

    # FROZEN: the value stays constant while the clean series moves
    rows = compare("FROZEN", steps=3, parameter="temperature")
    frozen = {h.temperature_c for _, h in rows[:3]}
    assert len(frozen) == 1 and len({c.temperature_c for c, _ in rows[:3]}) == 3 and rows[0][1].injected == "FROZEN"

    # DROPOUT: the value is missing, not zero and not filled
    rows = compare("DROPOUT", steps=2, parameter="humidity")
    assert rows[0][1].humidity_pct is None and rows[0][1].temperature_c == rows[0][0].temperature_c and rows[0][1].injected == "DROPOUT"

    # NOISE_BURST: the clean series is smooth (noise-free twin), the burst is not
    rows = compare("NOISE_BURST", steps=3, parameter="temperature", magnitude=8.0)
    diffs = [abs(h.temperature_c - c.temperature_c) for c, h in rows[:3]]
    assert max(diffs) > 0.5 and rows[0][1].injected == "NOISE_BURST"

    # MULTIVARIATE_INCONSISTENCY: warmer and much more humid at once
    rows = compare("MULTIVARIATE_INCONSISTENCY", steps=2)
    c, h = rows[0]
    assert h.temperature_c == pytest.approx(c.temperature_c + 12.0, abs=0.01) and h.humidity_pct == pytest.approx(min(100.0, c.humidity_pct + 35.0), abs=0.01)
    assert h.injected == "MULTIVARIATE_INCONSISTENCY"

    # METEOROLOGICAL_EXTREME: a consistent squall (temperature and pressure fall, humidity rises); labelled as the genuine kind
    rows = compare("METEOROLOGICAL_EXTREME", steps=2, parameter="pressure", magnitude=-22.0)
    c, h = rows[0]
    assert h.temperature_c < c.temperature_c and h.pressure_hpa == pytest.approx(c.pressure_hpa - 22.0, abs=0.01) and h.humidity_pct >= c.humidity_pct
    assert h.injected == "METEOROLOGICAL_EXTREME"

    # DATA_CORRUPTION: a non-physical number, stored as sent
    rows = compare("DATA_CORRUPTION", steps=2, parameter="temperature")
    assert rows[0][1].temperature_c == CORRUPT_VALUE and rows[0][1].injected == "DATA_CORRUPTION"


def test_an_injection_targets_one_station_and_counts_ticks_not_stations():
    sim = SimulatorSource(noise_scale=0.0)
    sim.inject("SPIKE", "KOKX", "temperature", 25.0, duration_steps=2)
    t1, t2, t3 = (sim.tick(T0 + timedelta(minutes=i)) for i in range(3))
    assert [r.station_id for r in t1 if r.injected] == ["KOKX"] and [r.station_id for r in t2 if r.injected] == ["KOKX"] and not any(r.injected for r in t3)
    sim2 = SimulatorSource()
    sim2.inject("SPIKE", None, "temperature", 25.0, duration_steps=2)           # every station: still two ticks, not 6 x faster
    a, b, c = (sim2.tick(T0 + timedelta(minutes=i)) for i in range(3))
    assert all(r.injected for r in a) and all(r.injected for r in b) and not any(r.injected for r in c) and sim2.pending_injections == 0


def test_injection_and_configuration_refuse_what_the_simulator_does_not_have():
    sim = SimulatorSource()
    with pytest.raises(UnknownStation):
        sim.inject("SPIKE", "ZWL001")                    # a real gauge id: injections never reach anything but simulator stations
    with pytest.raises(BadSimulatorConfig):
        sim.inject("TELEPORT", "KTLX")
    with pytest.raises(BadSimulatorConfig):
        sim.inject("SPIKE", "KTLX", parameter="rain")
    with pytest.raises(UnknownStation):
        sim.configure(station_ids=["KTLX", "NOPE"])
    with pytest.raises(BadSimulatorConfig):
        sim.configure(scenario="monsoon")
    with pytest.raises(BadSimulatorConfig):
        sim.configure(interval_seconds=0.0)
    sim.configure(station_ids=["KAMX"], interval_seconds=1.0)
    assert [r.station_id for r in sim.tick(T0)] == ["KAMX"] and sim.active_station_ids == ["KAMX"]
    with pytest.raises(UnknownStation):
        sim.inject("SPIKE", "KTLX")                     # a simulator station, but not in this run


@pytest.mark.asyncio
async def test_the_simulator_runs_pushes_readings_to_the_manager_and_stops_cleanly():
    async def fast(_):
        await asyncio.sleep(0)
    sim = SimulatorSource(sleep=fast)
    seen = []

    async def collect(r):
        seen.append(r)
    await sim.start(collect)
    assert sim.status().state == "running"
    for _ in range(20):
        await asyncio.sleep(0)
    with pytest.raises(SimulatorBusy):
        sim.configure(interval_seconds=1.0)
    await sim.stop()
    n = len(seen)
    assert n >= 6 and sim.status().state == "stopped" and {r.source for r in seen} == {"simulator"}
    await asyncio.sleep(0.01)
    assert len(seen) == n                                # stopped means stopped: no reading after stop
