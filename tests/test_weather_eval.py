"""SYNTHETIC evaluation floors for the temperature, pressure and humidity checks (see tests/weather_eval.py).

The background and every fault come from the seeded simulator: these numbers describe how the checks behave on simulated data, not their accuracy on
real stations (no real labelled faults exist). The floors are deliberately below what was measured (see the slice report) and are not tuned to it.

Floors asserted: false alarms (flagged readings per 1,000 clean readings, fault-free runs) <= 1.0 and SUSPECT calls on clean data == 0; event-level
recall >= 0.9 for SPIKE, FROZEN, DROPOUT, MULTIVARIATE_INCONSISTENCY, METEOROLOGICAL_EXTREME, DATA_CORRUPTION; >= 0.6 for NOISE_BURST (small bursts
are inside the noise); >= 0.5 for DRIFT (a slow, small ramp is the hardest); METEOROLOGICAL_EXTREME is called a fault (SUSPECT) in at most 10 % of
injections; detection delay: median 0 readings for SPIKE, DROPOUT, DATA_CORRUPTION, METEOROLOGICAL_EXTREME, at most 10 for FROZEN; scoring latency
of one reading below 5 ms on average.
"""
from tests import weather_eval as ev


def test_synthetic_false_alarm_rate_on_fault_free_runs():
    lat = []
    for step in (60.0, 5.0):
        fa = ev.false_alarms(seeds=range(100, 102), ticks=1440 if step == 60.0 else 2500, step_s=step, latencies=lat)
        assert fa["clean_readings"] >= 12000
        assert fa["suspect"] == 0
        assert fa["per_1000_flagged"] <= 1.0, fa
    s = ev.latency_summary(lat)
    assert s["mean_us"] < 5000, s            # scoring only (no database); the database write is not measured here


def test_return_to_baseline_after_an_extreme_is_not_flagged_again():
    """SYNTHETIC: at 1 s cadence the recovery readings after a METEOROLOGICAL_EXTREME must not be flagged one by one (at most 3 in all)."""
    for seed, station in ((1, ev.STATION_IDS[0]), (2, ev.STATION_IDS[1 % len(ev.STATION_IDS)]), (3, ev.STATION_IDS[2 % len(ev.STATION_IDS)])):
        sim = ev.SimulatorSource(seed=seed)
        sim.configure(station_ids=[station])
        history = {}
        ev._run(sim, ev.WARMUP, 1.0, history)
        sim.inject("METEOROLOGICAL_EXTREME", station, "pressure", -22.0, 10)
        rows = ev._run(sim, 10 + 90, 1.0, history, start_tick=ev.WARMUP)
        last = max(k for k, (_, r, _o) in enumerate(rows) if r.injected == "METEOROLOGICAL_EXTREME")
        assert any(o.flagged for _, r, o in rows if r.injected == "METEOROLOGICAL_EXTREME")
        after = [o for _, _r, o in rows[last + 1:]]
        assert len(after) >= 60
        assert sum(o.flagged for o in after) <= 3, [(o.status, o.reason) for o in after if o.flagged]


def test_synthetic_recall_delay_and_the_extreme_is_not_a_fault():
    res = ev.evaluate(seeds=range(1, 7), step_s=60.0)["per_kind"]
    assert set(res) == {"SPIKE", "DRIFT", "FROZEN", "DROPOUT", "NOISE_BURST", "MULTIVARIATE_INCONSISTENCY", "METEOROLOGICAL_EXTREME", "DATA_CORRUPTION"}
    for kind in ("SPIKE", "FROZEN", "DROPOUT", "MULTIVARIATE_INCONSISTENCY", "METEOROLOGICAL_EXTREME", "DATA_CORRUPTION"):
        assert res[kind]["recall"] >= 0.9, (kind, res[kind])
    assert res["NOISE_BURST"]["recall"] >= 0.6 and res["DRIFT"]["recall"] >= 0.5
    # the project's differentiator: a genuine extreme is flagged for a person to look at, but never called a fault
    assert res["METEOROLOGICAL_EXTREME"]["suspect_rate"] <= 0.1, res["METEOROLOGICAL_EXTREME"]
    for kind in ("SPIKE", "DROPOUT", "DATA_CORRUPTION", "METEOROLOGICAL_EXTREME"):
        assert res[kind]["median_delay"] == 0, (kind, res[kind])
    assert res["FROZEN"]["max_delay"] <= 10
