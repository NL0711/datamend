"""
backend/app/services/simulation_service.py
SkyGuard AI — Multi-Station Background Simulation Service and On-The-Fly Anomaly Injector.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np

from backend.simulator.diurnal_generator import (
    PRESETS,
    DiurnalGenerator,
    StationConfig,
)
from backend.app.schemas.schemas import (
    AnomalyInjectRequest,
    AnomalyInjectResponse,
    SimulationStartRequest,
    SimulationStatusResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class ActiveInjectionState:
    station_id: Optional[str]
    anomaly_type: str
    parameter: str
    magnitude: float
    remaining_steps: int
    total_steps: int
    decay: bool = False
    step_count: int = 0
    frozen_val: Optional[float] = None
    drift_rate: Optional[float] = None


class SimulationService:
    """Manages background multi-station synthetic telemetry streaming and dynamic anomaly injection."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._is_running: bool = False
        self._interval_sec: float = 1.0
        self._noise_level: float = 0.05
        self._scenario: str = "diurnal"
        self._step_counter: int = 0
        self._generators: Dict[str, DiurnalGenerator] = {}
        self._generator_states: Dict[str, Dict[str, float]] = {}
        self._active_injections: List[ActiveInjectionState] = []
        self._lock = asyncio.Lock()

        # Initialize default generator presets
        self._init_generators()

    def _init_generators(self) -> None:
        """Initializes station generators for standard regional microclimate presets."""
        stations_config = [
            ("AWS-001", "Central Meteorological Observatory", 28.6139, 77.2090, 216.0, "subtropical_delhi"),
            ("AWS-002", "Coastal Marine Weather Tower", 18.9220, 72.8347, 14.0, "temperate_marine"),
            ("AWS-003", "Plateau Highland Station", 32.2190, 76.3234, 1457.0, "high_altitude_plateau"),
            ("AWS-004", "Arid Subtropical Outpost", 26.9124, 70.9022, 225.0, "arid_desert"),
        ]

        for st_id, name, lat, lon, elev, preset_key in stations_config:
            meta = StationConfig(
                station_id=st_id,
                name=name,
                latitude=lat,
                longitude=lon,
                elevation=elev,
            )
            params = PRESETS.get(preset_key, PRESETS["subtropical_delhi"])
            gen = DiurnalGenerator(params=params, station_config=meta, seed=42)
            self._generators[st_id] = gen
            self._generator_states[st_id] = {
                "t_noise": 0.0,
                "p_noise": 0.0,
                "rh_noise": 0.0,
                "elapsed_days": 0.0,
            }

    async def start(
        self,
        station_ids: Optional[List[str]] = None,
        interval_seconds: float = 1.0,
        noise_level: float = 0.05,
        scenario: str = "diurnal",
    ) -> SimulationStatusResponse:
        """Starts background multi-station synthetic observation generation."""
        async with self._lock:
            if self._is_running and self._task and not self._task.done():
                return SimulationStatusResponse(
                    running=True,
                    interval_seconds=self._interval_sec,
                    active_stations=list(self._generators.keys()),
                    step_count=self._step_counter,
                    pending_injections_count=len(self._active_injections),
                    message="Simulation is already actively running.",
                )

            self._interval_sec = max(0.05, interval_seconds)
            self._noise_level = noise_level
            self._scenario = scenario
            self._is_running = True

            # If specific station IDs requested, ensure generators exist
            if station_ids:
                for st_id in station_ids:
                    if st_id not in self._generators:
                        meta = StationConfig(
                            station_id=st_id,
                            name=f"Simulated Station {st_id}",
                            latitude=28.6139,
                            longitude=77.2090,
                            elevation=216.0,
                        )
                        self._generators[st_id] = DiurnalGenerator(station_config=meta)
                        self._generator_states[st_id] = {
                            "t_noise": 0.0,
                            "p_noise": 0.0,
                            "rh_noise": 0.0,
                            "elapsed_days": 0.0,
                        }

            # Launch async background loop
            self._task = asyncio.create_task(self._simulation_loop())
            logger.info("Simulation service started with interval %.2fs", self._interval_sec)

            return SimulationStatusResponse(
                running=True,
                interval_seconds=self._interval_sec,
                active_stations=list(self._generators.keys()),
                step_count=self._step_counter,
                pending_injections_count=len(self._active_injections),
                message="Simulation successfully started.",
            )

    async def stop(self) -> SimulationStatusResponse:
        """Stops the active background simulation loop."""
        async with self._lock:
            self._is_running = False
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None

            logger.info("Simulation service stopped.")
            return SimulationStatusResponse(
                running=False,
                interval_seconds=self._interval_sec,
                active_stations=list(self._generators.keys()),
                step_count=self._step_counter,
                pending_injections_count=len(self._active_injections),
                message="Simulation successfully stopped.",
            )

    async def inject_anomaly(self, req: AnomalyInjectRequest) -> AnomalyInjectResponse:
        """Enqueues an on-the-fly anomaly to be injected into the next simulation step."""
        async with self._lock:
            # Set default magnitudes if not supplied
            mag = req.magnitude
            param = req.parameter.lower()
            a_type = req.anomaly_type.upper()

            if mag is None:
                if a_type == "SPIKE":
                    mag = 25.0 if param == "temperature" else (-20.0 if param == "pressure" else -40.0)
                elif a_type == "DRIFT":
                    mag = 0.5  # per step drift
                elif a_type in ["DROPOUT", "DATA_CORRUPTION"]:
                    mag = 0.0
                elif a_type == "NOISE_BURST":
                    mag = 8.0
                elif a_type == "MULTIVARIATE_INCONSISTENCY":
                    mag = 15.0
                elif a_type == "METEOROLOGICAL_EXTREME":
                    mag = -10.0
                else:
                    mag = 20.0

            injection = ActiveInjectionState(
                station_id=req.station_id,
                anomaly_type=a_type,
                parameter=param,
                magnitude=mag,
                remaining_steps=req.duration_steps,
                total_steps=req.duration_steps,
                decay=req.decay,
                step_count=0,
                drift_rate=mag if a_type == "DRIFT" else None,
            )
            self._active_injections.append(injection)
            logger.info("Enqueued anomaly injection: %s on %s (param: %s, mag: %s, steps: %d)",
                        a_type, req.station_id or "ALL", param, mag, req.duration_steps)

            return AnomalyInjectResponse(
                success=True,
                anomaly_type=a_type,
                station_id=req.station_id,
                parameter=param,
                magnitude=mag,
                duration_steps=req.duration_steps,
                message=f"Injected {a_type} on {param} for {req.duration_steps} steps.",
            )

    def get_status(self) -> SimulationStatusResponse:
        """Queries the current status of the simulation service."""
        return SimulationStatusResponse(
            running=self._is_running and (self._task is not None and not self._task.done()),
            interval_seconds=self._interval_sec,
            active_stations=list(self._generators.keys()),
            step_count=self._step_counter,
            pending_injections_count=len(self._active_injections),
            message="Simulation running" if self._is_running else "Simulation idle",
        )

    def _apply_injection(self, telemetry: Dict[str, Any], st_id: str) -> Dict[str, Any]:
        """Applies active anomaly injections to raw telemetry before ML processing."""
        data = dict(telemetry)
        for inj in list(self._active_injections):
            if inj.station_id is not None and inj.station_id != st_id:
                continue

            param = inj.parameter
            a_type = inj.anomaly_type

            if a_type == "SPIKE":
                factor = (0.5 ** inj.step_count) if inj.decay else 1.0
                if param in data and data[param] is not None:
                    data[param] = round(data[param] + inj.magnitude * factor, 2)

            elif a_type == "DRIFT":
                drift_offset = (inj.drift_rate or 0.5) * (inj.step_count + 1)
                if param in data and data[param] is not None:
                    data[param] = round(data[param] + drift_offset, 2)

            elif a_type == "FROZEN":
                if inj.frozen_val is None:
                    inj.frozen_val = data.get(param, 25.0)
                data[param] = inj.frozen_val

            elif a_type == "DROPOUT":
                data[param] = None

            elif a_type == "NOISE_BURST":
                noise = float(np.random.normal(0, inj.magnitude))
                if param in data and data[param] is not None:
                    data[param] = round(data[param] + noise, 2)

            elif a_type == "MULTIVARIATE_INCONSISTENCY":
                # Increase temperature while simultaneously increasing humidity
                if "temperature" in data and data["temperature"] is not None:
                    data["temperature"] = round(data["temperature"] + 12.0, 2)
                if "humidity" in data and data["humidity"] is not None:
                    data["humidity"] = min(100.0, round(data["humidity"] + 35.0, 2))

            elif a_type == "METEOROLOGICAL_EXTREME":
                # Coordinated rapid convective squall front
                if "temperature" in data and data["temperature"] is not None:
                    data["temperature"] = round(data["temperature"] - 8.0, 2)
                if "pressure" in data and data["pressure"] is not None:
                    data["pressure"] = round(data["pressure"] - 14.0, 2)
                if "humidity" in data and data["humidity"] is not None:
                    data["humidity"] = min(100.0, round(data["humidity"] + 25.0, 2))

            elif a_type == "DATA_CORRUPTION":
                data[param] = 9999.9  # Non-physical value trigger

            inj.step_count += 1
            inj.remaining_steps -= 1

            if inj.remaining_steps <= 0:
                self._active_injections.remove(inj)

        return data

    async def _simulation_loop(self) -> None:
        """Background asynchronous simulation generation loop."""
        from backend.app.services.ingestion_service import ingestion_service

        logger.info("Starting simulation tick loop...")
        try:
            while self._is_running:
                now_ts = datetime.now(timezone.utc)
                self._step_counter += 1

                for st_id, generator in self._generators.items():
                    prev_state = self._generator_states.get(st_id)
                    telemetry, new_state = generator.generate_streaming_step(now_ts, prev_state=prev_state)
                    self._generator_states[st_id] = new_state

                    # Apply any active anomaly injections
                    modified_telemetry = self._apply_injection(telemetry, st_id)

                    # Ingest into 5-tier pipeline + DB + WebSocket
                    try:
                        await ingestion_service.ingest_observation(
                            obs_data=modified_telemetry,
                            save_db=True,
                            broadcast=True,
                        )
                    except Exception as e:
                        logger.error("Simulation ingestion error for station %s: %s", st_id, e)

                await asyncio.sleep(self._interval_sec)

        except asyncio.CancelledError:
            logger.info("Simulation loop cancelled.")
        except Exception as e:
            logger.error("Simulation loop encountered fatal error: %s", e)
            self._is_running = False


# Global simulation service singleton
simulation_service = SimulationService()
