"""Telemetry: what a run cost, measured, never guessed.

Every ``python -m qc <command>`` is wrapped in a session (``DATAMEND_TELEMETRY=0`` or ``--no-telemetry`` turns it off). A session records:

  time        wall and process CPU seconds of the command, and named SPANS inside it: count, total, mean, p50, p95, p99 and max in
              milliseconds, and throughput (units per second, for example cell-days scored or training samples), with the GPU energy that
              fell inside each span (approximate: the sampling interval is about one second, so short spans are noisy).
  GPU         power (W), energy (Wh), utilisation, memory used, temperature and SM clock, sampled in the background. Energy comes from the
              NVML total-energy counter when ``pynvml`` (package nvidia-ml-py) is installed and the GPU supports it, otherwise from the
              sampled power integrated over time, otherwise it is reported as NOT AVAILABLE (many virtual GPUs report no power at all).
              Peak torch memory allocated is recorded per phase.
  CPU and RAM utilisation and resident memory (psutil). CPU ENERGY is read from Linux RAPL counters when readable; on Windows and in most
              containers it is NOT AVAILABLE, and it is not estimated.
  model       parameter count, size, FLOPs per forward pass (where a module records them).
  environment python, torch, CUDA, GPU name, platform (not the host name or user), the git commit.

A figure that could not be measured says NOT AVAILABLE with the reason. Optional: ``DATAMEND_GCO2_PER_KWH`` (grid intensity) adds a CO2 figure,
labelled an estimate from the measured energy and that number.
Output: <run>/telemetry/<command>_<time>.json and .md.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

NA = "NOT AVAILABLE"
_ACTIVE: Optional["Telemetry"] = None


def _num(s: str) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None                                    # "[N/A]", "[Not Supported]", "N/A", empty


class GpuProbe:
    """First GPU, through pynvml if it is importable, else nvidia-smi, else nothing."""

    def __init__(self) -> None:
        self.mode: Optional[str] = None
        self.name: Optional[str] = None
        self._nv = None
        self._h = None
        self._e0: Optional[float] = None
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nv, self._h = pynvml, pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(self._h)
            self.name = name.decode() if isinstance(name, bytes) else str(name)
            self.mode = "nvml"
            try:
                self._e0 = float(pynvml.nvmlDeviceGetTotalEnergyConsumption(self._h))      # millijoules since the driver loaded
            except Exception:
                self._e0 = None
        except Exception:
            self._nv = self._h = None
            if shutil.which("nvidia-smi"):
                self.mode = "smi"
                s = self.sample()
                self.name = s.get("name")

    def sample(self) -> Dict:
        if self.mode == "nvml":
            nv, h = self._nv, self._h
            out: Dict = {}
            for key, fn in (("power_w", lambda: nv.nvmlDeviceGetPowerUsage(h) / 1000.0),
                            ("util", lambda: float(nv.nvmlDeviceGetUtilizationRates(h).gpu)),
                            ("mem_mb", lambda: nv.nvmlDeviceGetMemoryInfo(h).used / 2 ** 20),
                            ("temp_c", lambda: float(nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU))),
                            ("sm_mhz", lambda: float(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM)))):
                try:
                    out[key] = fn()
                except Exception:
                    out[key] = None
            return out
        if self.mode == "smi":
            try:
                r = subprocess.run(["nvidia-smi", "--query-gpu=name,power.draw,utilization.gpu,memory.used,temperature.gpu,clocks.sm",
                                    "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
                f = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
                return {"name": f[0], "power_w": _num(f[1]), "util": _num(f[2]), "mem_mb": _num(f[3]), "temp_c": _num(f[4]),
                        "sm_mhz": _num(f[5])}
            except Exception:
                return {}
        return {}

    def energy_wh_since_start(self) -> Optional[float]:
        if self.mode == "nvml" and self._e0 is not None:
            try:
                return (float(self._nv.nvmlDeviceGetTotalEnergyConsumption(self._h)) - self._e0) / 3.6e6      # mJ -> Wh
            except Exception:
                return None
        return None


def rapl_energy_uj() -> Optional[float]:
    """Sum of the readable Linux RAPL package counters, microjoules; None when there are none (Windows, containers, no permission)."""
    base = Path("/sys/class/powercap")
    if not base.is_dir():
        return None
    total, found = 0.0, False
    for d in sorted(base.glob("intel-rapl:*")):
        if d.name.count(":") != 1:
            continue                                   # package domains only, not their sub-domains
        try:
            total += float((d / "energy_uj").read_text())
            found = True
        except Exception:
            return None
    return total if found else None


def integrate(samples: List[Tuple[float, float]], t0: float, t1: float) -> Optional[float]:
    """Watt-hours between t0 and t1 from (time, watts) samples, trapezoids with linear interpolation at the ends; None without samples."""
    pts = [(t, w) for t, w in samples if w is not None]
    if len(pts) < 2 or t1 <= t0:
        return None
    ts, ws = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    grid = np.concatenate([[t0], ts[(ts > t0) & (ts < t1)], [t1]])
    power = np.interp(grid, ts, ws)                    # holds the first and last value outside the sampled range
    return float(np.sum(0.5 * (power[1:] + power[:-1]) * np.diff(grid)) / 3600.0)          # trapezoids; joules -> watt-hours


class Telemetry:
    def __init__(self, out_dir: Path, name: str, interval: float = 1.0, meta: Optional[Dict] = None, probe: Optional[GpuProbe] = None,
                 sampler=None) -> None:
        self.out_dir, self.name, self.interval, self.meta = Path(out_dir), name, float(interval), dict(meta or {})
        self.probe = probe if probe is not None else GpuProbe()
        self._sampler = sampler                         # a callable returning a dict like GpuProbe.sample; replaces the probe (tests)
        self.spans: Dict[str, List[Tuple[float, float, float]]] = {}      # name -> [(t0, t1, units)]
        self.span_units: Dict[str, str] = {}
        self.metrics: Dict[str, List[Tuple[float, str]]] = {}
        self.samples: List[Dict] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.started = ""
        self.written: Optional[Path] = None

    # ---- lifecycle
    def start(self) -> "Telemetry":
        global _ACTIVE
        self.t0, self.cpu0, self.started = time.time(), time.process_time(), datetime.datetime.now().isoformat(timespec="seconds")
        self.rapl0 = rapl_energy_uj()
        self._cuda("reset")
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telemetry-sampler")
        self._thread.start()
        _ACTIVE = self
        return self

    def _loop(self) -> None:
        proc = None
        try:
            import psutil
            proc = psutil.Process()
            psutil.cpu_percent(None)
        except Exception:
            psutil = None                                                    # type: ignore[assignment]
        while not self._stop.is_set():
            s: Dict = {"t": time.time()}
            try:
                s.update(self._sampler() if self._sampler else self.probe.sample())
            except Exception:
                pass
            if proc is not None:
                try:
                    s["cpu_pct"], s["rss_mb"] = psutil.cpu_percent(None), proc.memory_info().rss / 2 ** 20
                except Exception:
                    pass
            with self._lock:
                self.samples.append(s)
            self._stop.wait(self.interval)

    def stop(self) -> Dict:
        global _ACTIVE
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if _ACTIVE is self:
            _ACTIVE = None
        self.t1 = time.time()
        try:
            summary = self.summary()
            self.written = self._write(summary)
        except Exception as e:                                               # telemetry must never break the command it measures
            summary = {"error": f"telemetry failed: {e}"}
        return summary

    # ---- recording
    @contextlib.contextmanager
    def span(self, name: str, units: float = 0.0, unit: str = "units", sync: bool = True):
        self._cuda("sync") if sync else None
        a = time.time()
        try:
            yield
        finally:
            self._cuda("sync") if sync else None
            self.spans.setdefault(name, []).append((a, time.time(), float(units)))
            if units:
                self.span_units[name] = unit

    def record(self, name: str, value: float, unit: str = "") -> None:
        self.metrics.setdefault(name, []).append((float(value), unit))

    def gpu_peak(self, label: str) -> None:
        """Record the peak torch memory allocated since the last call (or the start), in MB, then reset the peak."""
        peak = self._cuda("peak")
        if peak is not None:
            self.record(f"gpu_peak_allocated_mb.{label}", peak, "MB")

    @staticmethod
    def _cuda(what: str):
        try:
            import torch
            if not torch.cuda.is_available():
                return None
            if what == "sync":
                torch.cuda.synchronize()
            elif what == "reset":
                torch.cuda.reset_peak_memory_stats()
            elif what == "peak":
                v = torch.cuda.max_memory_allocated() / 2 ** 20
                torch.cuda.reset_peak_memory_stats()
                return v
        except Exception:
            return None
        return None

    # ---- summary
    def environment(self) -> Dict:
        env: Dict = {"python": sys.version.split()[0], "platform": f"{platform.system()} {platform.release()}", "numpy": np.__version__,
                     "cpu_count": os.cpu_count()}
        try:
            import torch
            env.update(torch=torch.__version__, cuda=torch.version.cuda, cuda_available=bool(torch.cuda.is_available()),
                       gpu_names=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
        except Exception:
            pass
        try:
            import psutil
            env["ram_total_gb"] = round(psutil.virtual_memory().total / 2 ** 30, 1)
        except Exception:
            pass
        try:
            from qc.runs import git_commit
            env["git_commit"] = git_commit()
        except Exception:
            env["git_commit"] = "unknown"
        return env

    def summary(self) -> Dict:
        wall = self.t1 - self.t0
        with self._lock:
            smp = list(self.samples)
        power = [(s["t"], s.get("power_w")) for s in smp]
        has_power = any(w is not None for _, w in power)
        col = lambda k: [s[k] for s in smp if s.get(k) is not None]
        gpu: Dict = {"name": self.probe.name, "source": self.probe.mode or "none", "samples": len(smp)}
        if self._sampler is None and self.probe.mode is None:
            gpu.update(available=False, note="no GPU monitor found (no pynvml, no nvidia-smi)")
        else:
            gpu["available"] = True
            counter = self.probe.energy_wh_since_start() if self._sampler is None else None
            integ = integrate(power, self.t0, self.t1) if has_power else None
            if counter is not None:
                gpu["energy_wh"], gpu["energy_method"] = counter, "NVML total-energy counter"
            elif integ is not None:
                gpu["energy_wh"], gpu["energy_method"] = integ, "sampled power integrated over time"
            else:
                gpu["energy_wh"], gpu["energy_method"] = NA, "NOT AVAILABLE: the GPU reports no power (common on virtual GPUs); install nvidia-ml-py for the NVML counter"
            if has_power:
                w = col("power_w")
                gpu.update(avg_power_w=float(np.mean(w)), max_power_w=float(np.max(w)))
            else:
                gpu.update(avg_power_w=NA, max_power_w=NA)
            for k, key in (("util", "util_pct"), ("mem_mb", "mem_used_mb"), ("temp_c", "temp_c"), ("sm_mhz", "sm_mhz")):
                v = col(k)
                gpu[f"avg_{key}"] = float(np.mean(v)) if v else NA
                gpu[f"max_{key}"] = float(np.max(v)) if v else NA
        cpu: Dict = {"process_cpu_seconds": time.process_time() - self.cpu0}
        for k, key in (("cpu_pct", "cpu_percent"), ("rss_mb", "rss_mb")):
            v = col(k)
            cpu[f"avg_{key}"] = float(np.mean(v)) if v else NA
            cpu[f"max_{key}"] = float(np.max(v)) if v else NA
        r1 = rapl_energy_uj()
        cpu["energy_wh"] = (max(r1 - self.rapl0, 0.0) / 3.6e9) if (r1 is not None and self.rapl0 is not None) else \
            f"{NA}: no readable RAPL counters (Windows, container or no permission); not estimated"
        spans = {}
        for name, rows in self.spans.items():
            d = np.array([b - a for a, b, _ in rows]) * 1000.0
            units = sum(u for _, _, u in rows)
            tot = float(d.sum()) / 1000.0
            e = [integrate(power, a, b) for a, b, _ in rows] if has_power else []
            e_sum = float(sum(x for x in e if x is not None)) if e and any(x is not None for x in e) else None
            spans[name] = {"count": len(rows), "total_s": tot, "mean_ms": float(d.mean()), "p50_ms": float(np.percentile(d, 50)),
                           "p95_ms": float(np.percentile(d, 95)), "p99_ms": float(np.percentile(d, 99)), "max_ms": float(d.max()),
                           "units": units, "unit": self.span_units.get(name, ""),
                           "units_per_s": (units / tot) if (units and tot > 0) else None,
                           "gpu_energy_wh_approx": e_sum, "gpu_energy_mwh_per_unit_approx": (1000.0 * e_sum / units) if (e_sum and units) else None}
        metrics = {}
        for name, vals in self.metrics.items():
            v = [x for x, _ in vals]
            metrics[name] = {"unit": vals[-1][1], "n": len(v), "last": v[-1], "mean": float(np.mean(v)), "max": float(np.max(v)),
                             "values": v if len(v) <= 50 else None}
        out = {"name": self.name, "started": self.started, "wall_seconds": wall, "meta": self.meta, "environment": self.environment(),
               "gpu": gpu, "cpu": cpu, "spans": spans, "metrics": metrics}
        g = os.environ.get("DATAMEND_GCO2_PER_KWH")
        if g and isinstance(gpu.get("energy_wh"), (int, float)):
            out["co2_estimate"] = {"grams": float(gpu["energy_wh"]) / 1000.0 * float(g), "basis": f"GPU energy only, times {g} gCO2/kWh given by the user",
                                   "label": "ESTIMATE"}
        return out

    def _write(self, s: Dict) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        base = self.out_dir / f"{self.name}_{stamp}"
        base.with_suffix(".json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
        base.with_suffix(".md").write_text(markdown(s), encoding="utf-8")
        return base.with_suffix(".md")


def markdown(s: Dict) -> str:
    f = lambda v, d=2: v if isinstance(v, str) or v is None else f"{v:.{d}f}"
    g, c, e = s["gpu"], s["cpu"], s["environment"]
    o = [f"### Telemetry: {s['name']}", "",
         f"Started {s['started']}; wall {f(s['wall_seconds'], 1)} s; process CPU {f(c['process_cpu_seconds'], 1)} s. "
         f"Python {e.get('python')}, torch {e.get('torch')}, CUDA {e.get('cuda')}, {e.get('platform')}, commit {e.get('git_commit')}.", "",
         "| resource | value |", "|---|---|",
         f"| GPU | {g.get('name')} (monitor: {g.get('source')}) |",
         f"| GPU energy (Wh) | {f(g.get('energy_wh'), 4)} ({g.get('energy_method', g.get('note'))}) |",
         f"| GPU power avg / max (W) | {f(g.get('avg_power_w'))} / {f(g.get('max_power_w'))} |",
         f"| GPU utilisation avg / max (%) | {f(g.get('avg_util_pct'), 1)} / {f(g.get('max_util_pct'), 1)} |",
         f"| GPU memory used max (MB) | {f(g.get('max_mem_used_mb'), 0)} |",
         f"| GPU temperature max (C) | {f(g.get('max_temp_c'), 0)} |",
         f"| CPU utilisation avg / max (%) | {f(c.get('avg_cpu_percent'), 1)} / {f(c.get('max_cpu_percent'), 1)} |",
         f"| process memory max (MB) | {f(c.get('max_rss_mb'), 0)} |",
         f"| CPU energy (Wh) | {f(c.get('energy_wh'), 4)} |"]
    if "co2_estimate" in s:
        o.append(f"| CO2 (g, ESTIMATE) | {f(s['co2_estimate']['grams'], 3)} ({s['co2_estimate']['basis']}) |")
    if s["spans"]:
        o += ["", "| span | n | total s | mean ms | p50 | p95 | p99 | max | units/s | GPU energy Wh (approx) |", "|---|---|---|---|---|---|---|---|---|---|"]
        for k, v in sorted(s["spans"].items(), key=lambda kv: -kv[1]["total_s"]):
            ups = f"{f(v['units_per_s'], 1)} {v['unit']}" if v["units_per_s"] else "-"
            o.append(f"| {k} | {v['count']} | {f(v['total_s'], 2)} | {f(v['mean_ms'], 1)} | {f(v['p50_ms'], 1)} | {f(v['p95_ms'], 1)} | "
                     f"{f(v['p99_ms'], 1)} | {f(v['max_ms'], 1)} | {ups} | {f(v['gpu_energy_wh_approx'], 4) if v['gpu_energy_wh_approx'] is not None else '-'} |")
    if s["metrics"]:
        o += ["", "| metric | last | mean | max | unit |", "|---|---|---|---|---|"]
        o += [f"| {k} | {f(v['last'], 4)} | {f(v['mean'], 4)} | {f(v['max'], 4)} | {v['unit']} |" for k, v in sorted(s["metrics"].items())]
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------- module-level helpers (no-ops when off)

def active() -> Optional[Telemetry]:
    return _ACTIVE


def span(name: str, units: float = 0.0, unit: str = "units", sync: bool = True):
    return _ACTIVE.span(name, units, unit, sync) if _ACTIVE is not None else contextlib.nullcontext()


def record(name: str, value: float, unit: str = "") -> None:
    if _ACTIVE is not None:
        _ACTIVE.record(name, value, unit)


def gpu_peak(label: str) -> None:
    if _ACTIVE is not None:
        _ACTIVE.gpu_peak(label)


def enabled() -> bool:
    return os.environ.get("DATAMEND_TELEMETRY", "1") != "0"


@contextlib.contextmanager
def session(out_dir: Path, name: str, on: bool = True, **meta):
    """Measure the block. Does nothing if telemetry is off or a session is already running (the outer one keeps the measurement)."""
    if not (on and enabled()) or _ACTIVE is not None:
        yield _ACTIVE
        return
    t = Telemetry(out_dir, name, interval=float(os.environ.get("DATAMEND_TELEMETRY_INTERVAL", "1.0")), meta=meta).start()
    try:
        yield t
    finally:
        t.stop()
        if t.written:
            print(f"telemetry: {t.written}")
