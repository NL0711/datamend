"""The simulator telemetry source: SYNTHETIC readings from the diurnal physics (sim_physics.py) with injectable faults (sim_faults.py).

The simulator's stations sit in the same station list as the real gauges and carry no label there; the ``source`` id ("simulator") exists
on the stored readings only, and an injected fault carries its kind as a ground-truth label on the reading. Seeded, so a run is reproducible.
Only temperature, pressure and humidity are produced (the original simulator had no rainfall).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

import numpy as np

from backend.app.stream.sim_faults import FAULT_KINDS, PARAMETERS, Injection, default_magnitude
from backend.app.stream.sim_physics import PRESETS, SIM_STATIONS, SimStation, StationModel
from backend.app.stream.source import Emit
from backend.app.stream.types import BadSimulatorConfig, SimulatorBusy, SourceStatus, StationInfo, StreamReading, UnknownStation, utcnow

logger = logging.getLogger(__name__)

SCENARIOS = ("diurnal",)
MIN_INTERVAL_S, MAX_INTERVAL_S = 0.05, 60.0


class SimulatorSource:
    source_id = "simulator"
    source_type = "SIMULATED"
    name = "Simulated stations"
    description = "Synthetic temperature, pressure and humidity from diurnal physics, with faults you can inject. Not measured data."

    def __init__(self, stations: Sequence[SimStation] = SIM_STATIONS, *, interval_seconds: float = 5.0, seed: int = 42, noise_scale: float = 1.0,
                 clock: Callable[[], datetime] = utcnow, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep) -> None:
        self._catalogue = {s.station_id: s for s in stations}
        self._active_ids: List[str] = list(self._catalogue)
        self.interval_seconds = interval_seconds
        self.seed = seed
        self.noise_scale = noise_scale
        self._clock, self._sleep = clock, sleep
        self._task: Optional[asyncio.Task] = None
        self._state = "stopped"
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None
        self._injections: List[Injection] = []
        self._injection_seq = 0
        self.step_count = 0
        self._models: Dict[str, StationModel] = {}
        self._t0: Optional[datetime] = None
        self._fault_rng = np.random.default_rng([seed, 999])
        self.reset()

    # ------------------------------------------------------------------ the TelemetrySource interface
    def stations(self) -> Sequence[StationInfo]:
        return [StationInfo(s.station_id, s.name, s.latitude, s.longitude, s.elevation) for s in self._catalogue.values()]

    def status(self) -> SourceStatus:
        if self._task is not None and self._task.done() and self._state == "running":
            self._state = "disconnected"
        return SourceStatus(self._state, self.interval_seconds, self._last_error, self._last_error_at)  # type: ignore[arg-type]

    async def start(self, emit: Emit) -> None:
        if self._task is not None and not self._task.done():
            return
        self.reset()
        self._state = "running"
        self._last_error = self._last_error_at = None
        self._task = asyncio.create_task(self._loop(emit))

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._state = "stopped"

    # ------------------------------------------------------------------ configuration
    @property
    def active_station_ids(self) -> List[str]:
        return list(self._active_ids)

    @property
    def pending_injections(self) -> int:
        return len(self._injections)

    def configure(self, station_ids: Optional[Sequence[str]] = None, interval_seconds: Optional[float] = None, noise_scale: Optional[float] = None,
                  scenario: Optional[str] = None) -> None:
        """Change what the next run produces. Refused while it runs. Unknown stations and scenarios are refused, never invented."""
        if self._state == "running":
            raise SimulatorBusy("the simulator is running; stop it before changing its settings")
        if scenario is not None and scenario not in SCENARIOS:
            raise BadSimulatorConfig(f"unknown scenario '{scenario}'; the simulator offers: {', '.join(SCENARIOS)}")
        if station_ids:
            unknown = [s for s in station_ids if s not in self._catalogue]
            if unknown:
                raise UnknownStation(f"not simulator stations: {', '.join(unknown)}; the simulator has: {', '.join(self._catalogue)}")
            self._active_ids = list(dict.fromkeys(station_ids))
        if interval_seconds is not None:
            if not MIN_INTERVAL_S <= interval_seconds <= MAX_INTERVAL_S:
                raise BadSimulatorConfig(f"interval_seconds must be between {MIN_INTERVAL_S:g} and {MAX_INTERVAL_S:g}")
            self.interval_seconds = interval_seconds
        if noise_scale is not None:
            if noise_scale < 0:
                raise BadSimulatorConfig("noise_level cannot be negative")
            self.noise_scale = noise_scale
        self.reset()

    def reset(self) -> None:
        """Rebuild the seeded station models and drop pending injections: a new run starts from the seed."""
        self._models = {
            sid: StationModel(self._catalogue[sid], PRESETS[self._catalogue[sid].preset], np.random.default_rng([self.seed, i]), self.noise_scale)
            for i, sid in enumerate(self._catalogue) if sid in self._active_ids
        }
        self._fault_rng = np.random.default_rng([self.seed, 999])
        self._injections.clear()
        self.step_count = 0
        self._t0 = None

    # ------------------------------------------------------------------ production
    def tick(self, now: Optional[datetime] = None) -> List[StreamReading]:
        """One step: a reading per active station at ``now`` (UTC), with any injected fault applied. Deterministic for a given seed and time sequence."""
        now = now or self._clock()
        if self._t0 is None:
            self._t0 = now
        elapsed_days = (now - self._t0).total_seconds() / 86400.0
        out: List[StreamReading] = []
        for sid, model in self._models.items():
            t, p, rh = model.step(now, elapsed_days)
            values: Dict[str, Optional[float]] = {"temperature": t, "pressure": p, "humidity": rh}
            label: Optional[str] = None
            for inj in self._injections:
                if inj.targets(sid) and inj.apply(sid, values, self._fault_rng):
                    label = label or inj.kind
            out.append(StreamReading(sid, now, self.source_id, values["temperature"], values["pressure"], values["humidity"], None, label))
        for inj in self._injections:
            inj.step += 1
        self._injections = [i for i in self._injections if not i.finished]
        self.step_count += 1
        return out

    async def _loop(self, emit: Emit) -> None:
        try:
            while True:
                for reading in self.tick():
                    try:
                        await emit(reading)
                    except Exception:
                        logger.exception("the consumer of the simulator failed on a reading of %s", reading.station_id)
                await self._sleep(self.interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._state = "disconnected"
            self._last_error, self._last_error_at = f"{type(exc).__name__}: {exc}", self._clock()
            logger.exception("the simulator loop stopped")

    # ------------------------------------------------------------------ fault injection
    def inject(self, kind: str, station_id: Optional[str] = None, parameter: str = "temperature", magnitude: Optional[float] = None,
               duration_steps: int = 1, decay: bool = False) -> Dict[str, Any]:
        """Queue a synthetic fault for the next ticks. It only ever touches this simulator's stream. (The caller checks that the simulator runs.)"""
        kind = kind.upper()
        parameter = parameter.lower()
        if kind not in FAULT_KINDS:
            raise BadSimulatorConfig(f"unknown fault kind '{kind}'; the injector offers: {', '.join(FAULT_KINDS)}")
        if parameter not in PARAMETERS:
            raise BadSimulatorConfig(f"unknown parameter '{parameter}'; the simulator produces: {', '.join(PARAMETERS)}")
        if not 1 <= duration_steps <= 200:
            raise BadSimulatorConfig("duration_steps must be between 1 and 200")
        if station_id not in (None, "", "ALL") and station_id not in self._active_ids:
            raise UnknownStation(f"'{station_id}' is not a station of the running simulator; injections only affect simulator stations")
        self._injection_seq += 1
        mag = default_magnitude(kind, parameter) if magnitude is None else float(magnitude)
        inj = Injection(f"inj-{self._injection_seq}", kind, station_id, parameter, mag, duration_steps, decay)
        self._injections.append(inj)
        return {"injection_id": inj.injection_id, "anomaly_type": kind, "station_id": station_id, "parameter": parameter, "magnitude": mag,
                "duration_steps": duration_steps}
