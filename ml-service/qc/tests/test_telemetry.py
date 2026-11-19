"""qc.telemetry: energy arithmetic, span statistics, honest NOT AVAILABLE, files, no-op when off, and the wiring into scoring and main."""
import json
import time

import numpy as np
import pytest

from qc import telemetry as T


def test_energy_integration_is_exact_for_constant_and_partial_intervals():
    flat = [(0.0, 100.0), (10.0, 100.0)]
    assert T.integrate(flat, 0.0, 10.0) == pytest.approx(1000.0 / 3600.0)             # 100 W for 10 s = 1000 J
    assert T.integrate(flat, 2.0, 6.0) == pytest.approx(400.0 / 3600.0)
    ramp = [(0.0, 0.0), (10.0, 100.0)]
    assert T.integrate(ramp, 0.0, 10.0) == pytest.approx(500.0 / 3600.0)              # mean 50 W
    assert T.integrate([(0.0, None), (1.0, None)], 0.0, 1.0) is None                  # no power reported: no number
    assert T.integrate([(0.0, 5.0)], 0.0, 1.0) is None


def test_inactive_helpers_do_nothing_and_do_not_fail():
    assert T.active() is None
    with T.span("anything", units=5):
        pass
    T.record("x", 1.0)
    T.gpu_peak("none")


def _run(tmp_path, sampler):
    t = T.Telemetry(tmp_path, "unit", interval=0.02, sampler=sampler).start()
    for _ in range(5):
        with T.span("work", units=10, unit="items", sync=False):
            time.sleep(0.03)
    with T.span("other", sync=False):
        time.sleep(0.01)
    T.record("model.params", 123, "count")
    T.record("model.params", 456, "count")
    return t, t.stop()


def test_spans_percentiles_throughput_metrics_and_files(tmp_path):
    t, s = _run(tmp_path, lambda: {"power_w": 100.0, "util": 50.0, "mem_mb": 1000.0, "temp_c": 60.0, "sm_mhz": 1500.0})
    w = s["spans"]["work"]
    assert w["count"] == 5 and w["units"] == 50 and w["unit"] == "items"
    assert 25 <= w["p50_ms"] <= 120 and w["p50_ms"] <= w["p95_ms"] <= w["p99_ms"] <= w["max_ms"]
    assert w["units_per_s"] == pytest.approx(50 / w["total_s"])
    assert s["metrics"]["model.params"]["last"] == 456 and s["metrics"]["model.params"]["n"] == 2
    g = s["gpu"]
    assert g["avg_power_w"] == pytest.approx(100.0) and g["max_util_pct"] == 50.0
    assert isinstance(g["energy_wh"], float) and g["energy_wh"] == pytest.approx(100.0 * s["wall_seconds"] / 3600.0, rel=0.35)
    assert g["energy_wh"] > 0 and "integrated" in g["energy_method"]
    assert w["gpu_energy_wh_approx"] is not None and w["gpu_energy_wh_approx"] > 0
    files = sorted(p.suffix for p in tmp_path.iterdir())
    assert files == [".json", ".md"]
    doc = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert doc["name"] == "unit" and "environment" in doc and "python" in doc["environment"]
    md = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "### Telemetry: unit" in md and "work" in md and "GPU energy" in md
    assert T.active() is None                                                          # the session ended


def test_missing_power_is_reported_as_not_available_never_estimated(tmp_path):
    _, s = _run(tmp_path, lambda: {"power_w": None, "util": 10.0, "mem_mb": 500.0})
    assert s["gpu"]["energy_wh"] == T.NA and s["gpu"]["avg_power_w"] == T.NA
    assert "NOT AVAILABLE" in s["gpu"]["energy_method"]
    assert "NOT AVAILABLE" in str(s["cpu"]["energy_wh"]) or isinstance(s["cpu"]["energy_wh"], float)     # RAPL only where readable
    assert s["spans"]["work"]["gpu_energy_wh_approx"] is None


def test_co2_is_only_an_estimate_from_a_given_intensity(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAMEND_GCO2_PER_KWH", "700")
    _, s = _run(tmp_path, lambda: {"power_w": 200.0})
    assert s["co2_estimate"]["label"] == "ESTIMATE"
    assert s["co2_estimate"]["grams"] == pytest.approx(s["gpu"]["energy_wh"] / 1000.0 * 700.0)


def test_session_is_off_with_the_environment_switch_and_does_not_nest(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAMEND_TELEMETRY", "0")
    with T.session(tmp_path, "off") as t:
        assert t is None
    assert not list(tmp_path.iterdir())
    monkeypatch.delenv("DATAMEND_TELEMETRY")
    with T.session(tmp_path, "outer") as outer:
        with T.session(tmp_path, "inner") as inner:
            assert inner is outer                                                       # the outer session keeps the measurement
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_scoring_records_a_span_per_component_with_cell_days(prepared, bench, tmp_path):
    from qc.baselines import run_untrained
    t = T.Telemetry(tmp_path, "scoring", interval=0.05, sampler=lambda: {"power_w": 50.0}).start()
    try:
        run_untrained(prepared, ("val",), overwrite=True)
    finally:
        s = t.stop()
    sp = s["spans"]
    assert "score.rules" in sp and sp["score.rules"]["unit"] == "cell-days" and sp["score.rules"]["units"] > 0
    assert sp["score.rules"]["units_per_s"] > 0 and "data.make_block" in sp
    n_years = len(prepared.split.years["val"]) + len(prepared.split.years["threshold"])
    assert sp["score.rules"]["count"] == n_years


def test_main_wraps_a_command_and_writes_the_session(tmp_path, monkeypatch):
    from qc import __main__ as m
    monkeypatch.setenv("DATAMEND_OUT_DIR", str(tmp_path))
    monkeypatch.setitem(m.COMMANDS, "ceiling", lambda cfg, args: 0)
    assert m.main(["ceiling"]) == 0
    assert list(tmp_path.rglob("telemetry/ceiling_*.json")), "no telemetry file was written"
    for f in tmp_path.rglob("telemetry/*"):
        f.unlink()
    assert m.main(["ceiling", "--no-telemetry"]) == 0
    assert not list(tmp_path.rglob("telemetry/ceiling_*.json"))
