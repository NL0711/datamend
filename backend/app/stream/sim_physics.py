"""SYNTHETIC weather physics for the simulator source (temperature, pressure, relative humidity). Nothing here is measured data.

A reimplementation of the original dashboard simulator's model: a diurnal temperature curve (peak after local solar noon) plus a seasonal
term, relative humidity from the Magnus-Tetens saturation vapour pressure against a slowly varying dew point, pressure from the hypsometric
formula plus a synoptic wave and a 12-hour tide, and autoregressive AR(1) noise on all three. Each station has its own phase (local solar time
from its longitude and its own synoptic offset) and its own seeded random stream, so a run is reproducible and stations differ.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class DiurnalParams:
    temp_base: float = 22.0
    temp_amplitude: float = 6.5
    temp_peak_hour: float = 14.5          # local solar hour of the temperature peak
    temp_seasonal_amp: float = 5.0
    temp_noise_sigma: float = 0.35
    temp_ar_rho: float = 0.88
    dew_point_depression: float = 6.0     # temp_base minus the base dew point
    rh_min: float = 5.0
    rh_max: float = 100.0
    rh_noise_sigma: float = 1.2
    rh_ar_rho: float = 0.85
    magnus_a: float = 6.112               # hPa
    magnus_b: float = 17.67
    magnus_c: float = 243.5               # deg C
    sea_level_pressure: float = 1013.25
    pressure_synoptic_amp: float = 8.0
    pressure_synoptic_period_days: float = 5.0
    pressure_tide_amp: float = 1.2
    pressure_noise_sigma: float = 0.15
    pressure_ar_rho: float = 0.92


PRESETS: Dict[str, DiurnalParams] = {
    "subtropical": DiurnalParams(temp_base=25.0, temp_amplitude=7.5, temp_peak_hour=14.5, dew_point_depression=6.5, pressure_tide_amp=1.4),
    "temperate_marine": DiurnalParams(temp_base=15.0, temp_amplitude=4.0, temp_peak_hour=14.0, dew_point_depression=3.0, sea_level_pressure=1015.0,
                                      pressure_tide_amp=0.6, pressure_synoptic_amp=12.0),
    "high_altitude_plateau": DiurnalParams(temp_base=5.0, temp_amplitude=9.0, temp_peak_hour=14.0, dew_point_depression=10.0, pressure_tide_amp=0.8),
    "arid_desert": DiurnalParams(temp_base=33.0, temp_amplitude=13.0, temp_peak_hour=15.0, dew_point_depression=18.0, pressure_tide_amp=1.5),
}


@dataclass(frozen=True)
class SimStation:
    station_id: str
    name: str
    latitude: float
    longitude: float
    elevation: float
    preset: str

    @property
    def solar_offset_hours(self) -> float:
        """Local solar time minus UTC, from the longitude (15 degrees per hour): the station's diurnal phase."""
        return self.longitude / 15.0


def saturation_vapour_pressure(params: DiurnalParams, temp_c: float) -> float:
    t = min(70.0, max(-60.0, temp_c))
    return params.magnus_a * math.exp(params.magnus_b * t / (t + params.magnus_c))


def hypsometric_pressure(params: DiurnalParams, elevation_m: float) -> float:
    return params.sea_level_pressure * (1.0 - 0.0065 * elevation_m / 288.15) ** 5.25588


class StationModel:
    """The clean (fault-free) series of one station, one step at a time. ``rng`` is the station's own seeded generator."""

    def __init__(self, station: SimStation, params: DiurnalParams, rng: np.random.Generator, noise_scale: float = 1.0) -> None:
        self.station, self.params, self.rng, self.noise_scale = station, params, rng, max(0.0, noise_scale)
        self._t_noise = self._p_noise = self._rh_noise = 0.0
        self._synoptic_offset_days = station.longitude / 360.0       # stations are not in phase with each other

    def _ar(self, previous: float, rho: float, sigma: float) -> float:
        return rho * previous + math.sqrt(max(0.0, 1.0 - rho * rho)) * float(self.rng.normal(0.0, sigma * self.noise_scale))

    def step(self, ts: datetime, elapsed_days: float) -> Tuple[float, float, float]:
        """(temperature C, pressure hPa, relative humidity %) at ``ts`` (UTC), ``elapsed_days`` after the simulator's start."""
        p, st = self.params, self.station
        utc_hour = ts.hour + ts.minute / 60.0 + ts.second / 3600.0 + ts.microsecond / 3.6e9
        hour = (utc_hour + st.solar_offset_hours) % 24.0
        doy = ts.timetuple().tm_yday
        self._t_noise = self._ar(self._t_noise, p.temp_ar_rho, p.temp_noise_sigma)
        self._p_noise = self._ar(self._p_noise, p.pressure_ar_rho, p.pressure_noise_sigma)
        self._rh_noise = self._ar(self._rh_noise, p.rh_ar_rho, p.rh_noise_sigma)

        season = p.temp_seasonal_amp * math.sin(2.0 * math.pi * (doy - 80.0) / 365.25)
        diurnal = p.temp_amplitude * math.sin(2.0 * math.pi * (hour - (p.temp_peak_hour - 6.0)) / 24.0)
        temperature = p.temp_base + season + diurnal + self._t_noise

        days = elapsed_days + self._synoptic_offset_days
        e_dew = saturation_vapour_pressure(p, p.temp_base - p.dew_point_depression) * (1.0 + 0.06 * math.sin(2.0 * math.pi * days / 4.0))
        humidity = min(p.rh_max, max(p.rh_min, e_dew / saturation_vapour_pressure(p, temperature) * 100.0 + self._rh_noise))

        synoptic = p.pressure_synoptic_amp * math.sin(2.0 * math.pi * days / p.pressure_synoptic_period_days)
        tide = p.pressure_tide_amp * math.cos(4.0 * math.pi * (hour - 10.0) / 24.0)
        pressure = hypsometric_pressure(p, st.elevation) + synoptic + tide + self._p_noise
        return round(temperature, 2), round(pressure, 2), round(humidity, 2)


# The original simulator's stations. They are simulated; the names are places, not claims that a real gauge reports there.
SIM_STATIONS: Tuple[SimStation, ...] = (
    SimStation("KTLX", "Oklahoma City, OK", 35.3331, -97.2778, 370.0, "subtropical"),
    SimStation("KOKX", "New York City, NY", 40.8656, -72.8628, 30.0, "temperate_marine"),
    SimStation("KAMX", "Miami, FL", 25.6111, -80.4128, 5.0, "temperate_marine"),
    SimStation("KATX", "Seattle, WA", 48.1947, -122.4944, 150.0, "temperate_marine"),
    SimStation("KFWS", "Dallas-Fort Worth, TX", 32.5731, -97.3031, 210.0, "subtropical"),
    SimStation("KDMX", "Des Moines, IA", 41.7311, -93.7228, 290.0, "subtropical"),
)
