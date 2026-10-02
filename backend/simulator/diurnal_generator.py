"""
SkyGuard AI — High-Fidelity Diurnal Meteorological Simulation Engine.

Generates realistic AWS observations (Temperature, Pressure, Relative Humidity)
adhering to solar diurnal radiation curves, Magnus-Tetens thermodynamic saturation
vapor pressure physics, 12-hour semi-diurnal atmospheric thermal tides, synoptic
Rossby pressure waves, and autoregressive atmospheric turbulence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd


@dataclass
class StationConfig:
    """Automatic Weather Station location metadata."""
    station_id: str = "AWS-001"
    name: str = "Central Weather Station"
    latitude: float = 28.6139
    longitude: float = 77.2090
    elevation: float = 216.0  # meters above sea level


# Alias for backward compatibility
StationMetadata = StationConfig


@dataclass
class DiurnalParameters:
    """Configurable parameters for thermodynamic diurnal generation."""
    # Temperature (°C)
    temp_base: float = 22.0
    temp_amplitude: float = 6.5
    temp_peak_hour: float = 14.5  # 2:30 PM solar radiation lag peak
    temp_seasonal_amp: float = 5.0
    temp_noise_sigma: float = 0.35
    temp_ar_rho: float = 0.88

    # Humidity (%) & Thermodynamics
    dew_point_depression: float = 6.0  # Base (temp_base - T_d)
    rh_min: float = 5.0
    rh_max: float = 100.0
    rh_noise_sigma: float = 1.2
    rh_ar_rho: float = 0.85
    magnus_a: float = 6.112   # hPa (saturation vapor pressure at 0°C)
    magnus_b: float = 17.67   # dimensionless Magnus constant
    magnus_c: float = 243.5   # °C Magnus temperature constant

    # Atmospheric Pressure (hPa)
    sea_level_pressure: float = 1013.25
    pressure_synoptic_amp: float = 8.0
    pressure_synoptic_period_days: float = 5.0
    pressure_tide_amp: float = 1.2  # 12-hour S2(P) atmospheric tide
    pressure_noise_sigma: float = 0.15
    pressure_ar_rho: float = 0.92

    # Reproducibility
    random_seed: Optional[int] = 42


PRESETS: Dict[str, DiurnalParameters] = {
    "subtropical_delhi": DiurnalParameters(
        temp_base=25.0,
        temp_amplitude=7.5,
        temp_peak_hour=14.5,
        dew_point_depression=6.5,
        sea_level_pressure=1013.25,
        pressure_tide_amp=1.4,
    ),
    "temperate_marine": DiurnalParameters(
        temp_base=15.0,
        temp_amplitude=4.0,
        temp_peak_hour=14.0,
        dew_point_depression=3.0,  # High humidity marine boundary layer
        sea_level_pressure=1015.0,
        pressure_tide_amp=0.6,
        pressure_synoptic_amp=12.0,
    ),
    "high_altitude_plateau": DiurnalParameters(
        temp_base=5.0,
        temp_amplitude=9.0,        # Large diurnal range at high elevation
        temp_peak_hour=14.0,
        dew_point_depression=10.0, # Dry air
        pressure_tide_amp=0.8,
    ),
    "arid_desert": DiurnalParameters(
        temp_base=33.0,
        temp_amplitude=13.0,       # Extreme desert diurnal range
        temp_peak_hour=15.0,
        dew_point_depression=18.0, # Low RH (10-25%)
        pressure_tide_amp=1.5,
    ),
}


class DiurnalGenerator:
    """
    Continuous meteorological time-series generator adhering to atmospheric physics.
    """

    def __init__(
        self,
        station_config: Optional[StationConfig] = None,
        params: Optional[DiurnalParameters] = None,
        seed: Optional[int] = None,
        station: Optional[StationConfig] = None,
    ) -> None:
        self.station = station_config or station or StationConfig()
        self.params = params or DiurnalParameters()
        effective_seed = seed if seed is not None else self.params.random_seed
        self.rng = np.random.default_rng(effective_seed)

    def calculate_hypsometric_pressure(self, elevation_m: float) -> float:
        """
        Calculate barometric base pressure at station elevation using the hypsometric formula.
        P(z) = P_slp * (1 - L*z / T0)^(g*M / R0*L)
        """
        base_p = self.params.sea_level_pressure * (
            (1.0 - (0.0065 * elevation_m) / 288.15) ** 5.25588
        )
        return float(base_p)

    def calculate_saturation_vapor_pressure(
        self, temp_c: Union[np.ndarray, float]
    ) -> Union[np.ndarray, float]:
        """
        Calculate saturation vapor pressure e_s(T) [hPa] using the WMO Magnus-Tetens formula.
        e_s(T) = a * exp((b * T) / (T + c))
        """
        a = self.params.magnus_a
        b = self.params.magnus_b
        c = self.params.magnus_c
        t_safe = np.clip(temp_c, -60.0, 70.0)
        return a * np.exp((b * t_safe) / (t_safe + c))

    def calculate_dew_point(
        self, temp_c: Union[np.ndarray, float], rh_pct: Union[np.ndarray, float]
    ) -> Union[np.ndarray, float]:
        """
        Calculate dew point temperature T_d [°C] from T and RH using Magnus inversion.
        gamma = (b*T)/(T+c) + ln(RH / 100)
        T_d = (c * gamma) / (b - gamma)
        """
        b = self.params.magnus_b
        c = self.params.magnus_c
        rh_safe = np.clip(rh_pct, 0.01, 100.0)
        gamma = (b * temp_c) / (temp_c + c) + np.log(rh_safe / 100.0)
        return (c * gamma) / (b - gamma)

    def generate_ar1_noise(
        self, n_steps: int, sigma: float, rho: float
    ) -> np.ndarray:
        """
        Generate a stationary AR(1) autoregressive noise process with Var(eta) = sigma^2.
        eta(t) = rho * eta(t-1) + sqrt(1 - rho^2) * epsilon(t)
        """
        if n_steps <= 0:
            return np.empty(0, dtype=np.float64)

        innovations = self.rng.normal(0.0, sigma, size=n_steps)
        noise = np.empty(n_steps, dtype=np.float64)
        noise[0] = self.rng.normal(0.0, sigma)

        scale = math.sqrt(max(0.0, 1.0 - rho ** 2))
        for i in range(1, n_steps):
            noise[i] = rho * noise[i - 1] + scale * innovations[i]

        return noise

    def generate(
        self,
        start_date: Union[str, datetime] = "2026-08-01 00:00:00",
        end_date: Optional[Union[str, datetime]] = None,
        duration_days: Optional[float] = None,
        days: Optional[float] = None,
        sampling_interval_min: float = 5.0,
        freq: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Generate a complete clean baseline meteorological dataset.
        """
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        effective_freq = freq if freq is not None else f"{int(sampling_interval_min)}min"
        effective_days = duration_days if duration_days is not None else (days if days is not None else 7.0)

        start_dt = pd.to_datetime(start_date, utc=True)
        if end_date is not None:
            end_dt = pd.to_datetime(end_date, utc=True)
            timestamps = pd.date_range(start=start_dt, end=end_dt, freq=effective_freq)
        else:
            total_minutes = effective_days * 1440.0
            step_minutes = pd.Timedelta(effective_freq).total_seconds() / 60.0
            n_periods = int(round(total_minutes / step_minutes))
            timestamps = pd.date_range(start=start_dt, periods=n_periods, freq=effective_freq)

        n_steps = len(timestamps)
        if n_steps == 0:
            return pd.DataFrame()

        # Continuous time features
        hours = timestamps.hour.values + timestamps.minute.values / 60.0 + timestamps.second.values / 3600.0
        day_of_year = timestamps.dayofyear.values
        elapsed_days = (timestamps - timestamps[0]).total_seconds().values / 86400.0

        # 1. Temperature Generation T(t)
        t_season = self.params.temp_seasonal_amp * np.sin(2.0 * np.pi * (day_of_year - 80.0) / 365.25)
        h_zero = self.params.temp_peak_hour - 6.0
        t_diurnal = self.params.temp_amplitude * np.sin(2.0 * np.pi * (hours - h_zero) / 24.0)
        t_noise = self.generate_ar1_noise(
            n_steps, self.params.temp_noise_sigma, self.params.temp_ar_rho
        )
        temperature = self.params.temp_base + t_season + t_diurnal + t_noise

        # 2. Thermodynamic Relative Humidity Generation RH(t) via Magnus-Tetens
        t_dew_base = self.params.temp_base - self.params.dew_point_depression
        e_base = self.calculate_saturation_vapor_pressure(t_dew_base)
        # Multi-day synoptic moisture variation
        e_synoptic = e_base * (1.0 + 0.06 * np.sin(2.0 * np.pi * elapsed_days / 4.0))
        e_s_t = self.calculate_saturation_vapor_pressure(temperature)
        rh_raw = (e_synoptic / e_s_t) * 100.0
        rh_noise = self.generate_ar1_noise(
            n_steps, self.params.rh_noise_sigma, self.params.rh_ar_rho
        )
        humidity = np.clip(rh_raw + rh_noise, self.params.rh_min, self.params.rh_max)

        # 3. Barometric Pressure Generation P(t) with 12h Tides & Synoptic Waves
        p_base = self.calculate_hypsometric_pressure(self.station.elevation)
        p_synoptic = self.params.pressure_synoptic_amp * np.sin(
            2.0 * np.pi * elapsed_days / self.params.pressure_synoptic_period_days
        ) + 2.0 * np.cos(2.0 * np.pi * elapsed_days / 2.5)
        # S2(P) 12-hour thermal tide (max at 10:00 & 22:00, min at 04:00 & 16:00)
        p_tide = self.params.pressure_tide_amp * np.cos(4.0 * np.pi * (hours - 10.0) / 24.0)
        p_noise = self.generate_ar1_noise(
            n_steps, self.params.pressure_noise_sigma, self.params.pressure_ar_rho
        )
        pressure = p_base + p_synoptic + p_tide + p_noise

        # 4. Telemetry DataFrame Construction with Full Metadata
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "station_id": self.station.station_id,
                "temperature": np.round(temperature, 2),
                "pressure": np.round(pressure, 2),
                "humidity": np.round(humidity, 2),
                "latitude": self.station.latitude,
                "longitude": self.station.longitude,
                "elevation": self.station.elevation,
                "is_anomaly": False,
                "anomaly_type": "NORMAL",
                "severity": "NONE",
                "is_fault": False,
                "affected_params": "none",
                "clean_temperature": np.round(temperature, 2),
                "clean_pressure": np.round(pressure, 2),
                "clean_humidity": np.round(humidity, 2),
                "anomaly_metadata": "{}",
            }
        )

        return df

    def generate_streaming_step(
        self,
        timestamp: Union[str, datetime],
        prev_state: Optional[Dict[str, float]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """
        Generate a single telemetry observation step for live streaming / WebSocket ingestion.
        """
        ts = pd.to_datetime(timestamp, utc=True)
        hour = ts.hour + ts.minute / 60.0 + ts.second / 3600.0
        doy = ts.dayofyear

        prev_t_noise = prev_state.get("t_noise", 0.0) if prev_state else 0.0
        prev_p_noise = prev_state.get("p_noise", 0.0) if prev_state else 0.0
        prev_rh_noise = prev_state.get("rh_noise", 0.0) if prev_state else 0.0
        elapsed_days = prev_state.get("elapsed_days", 0.0) if prev_state else 0.0

        # AR(1) state step updates
        scale_t = math.sqrt(max(0.0, 1.0 - self.params.temp_ar_rho ** 2))
        t_noise = self.params.temp_ar_rho * prev_t_noise + scale_t * self.rng.normal(
            0.0, self.params.temp_noise_sigma
        )

        scale_p = math.sqrt(max(0.0, 1.0 - self.params.pressure_ar_rho ** 2))
        p_noise = self.params.pressure_ar_rho * prev_p_noise + scale_p * self.rng.normal(
            0.0, self.params.pressure_noise_sigma
        )

        scale_rh = math.sqrt(max(0.0, 1.0 - self.params.rh_ar_rho ** 2))
        rh_noise = self.params.rh_ar_rho * prev_rh_noise + scale_rh * self.rng.normal(
            0.0, self.params.rh_noise_sigma
        )

        # Temperature
        t_season = self.params.temp_seasonal_amp * math.sin(2.0 * math.pi * (doy - 80.0) / 365.25)
        h_zero = self.params.temp_peak_hour - 6.0
        t_diurnal = self.params.temp_amplitude * math.sin(2.0 * math.pi * (hour - h_zero) / 24.0)
        temp_c = self.params.temp_base + t_season + t_diurnal + t_noise

        # Humidity via Magnus-Tetens
        t_dew_base = self.params.temp_base - self.params.dew_point_depression
        e_base = float(self.calculate_saturation_vapor_pressure(t_dew_base))
        e_synoptic = e_base * (1.0 + 0.06 * math.sin(2.0 * math.pi * elapsed_days / 4.0))
        e_s = float(self.calculate_saturation_vapor_pressure(temp_c))
        rh_pct = float(
            np.clip((e_synoptic / e_s) * 100.0 + rh_noise, self.params.rh_min, self.params.rh_max)
        )

        # Pressure
        p_base = self.calculate_hypsometric_pressure(self.station.elevation)
        p_synoptic = self.params.pressure_synoptic_amp * math.sin(
            2.0 * math.pi * elapsed_days / self.params.pressure_synoptic_period_days
        )
        p_tide = self.params.pressure_tide_amp * math.cos(4.0 * math.pi * (hour - 10.0) / 24.0)
        pressure_hpa = p_base + p_synoptic + p_tide + p_noise

        telemetry = {
            "timestamp": ts.isoformat(),
            "station_id": self.station.station_id,
            "temperature": round(temp_c, 2),
            "pressure": round(pressure_hpa, 2),
            "humidity": round(rh_pct, 2),
            "latitude": self.station.latitude,
            "longitude": self.station.longitude,
            "elevation": self.station.elevation,
            "is_anomaly": False,
            "anomaly_type": "NORMAL",
            "severity": "NONE",
            "is_fault": False,
            "affected_params": "none",
            "clean_temperature": round(temp_c, 2),
            "clean_pressure": round(pressure_hpa, 2),
            "clean_humidity": round(rh_pct, 2),
            "anomaly_metadata": "{}",
        }

        new_state = {
            "t_noise": float(t_noise),
            "p_noise": float(p_noise),
            "rh_noise": float(rh_noise),
            "elapsed_days": float(elapsed_days + 5.0 / 1440.0),
        }

        return telemetry, new_state


def generate_diurnal_data(
    start_date: Union[str, datetime] = "2026-08-01 00:00:00",
    days: float = 7.0,
    sampling_interval_min: float = 5.0,
    station_id: str = "AWS-001",
    seed: Optional[int] = 42,
    **kwargs: Any,
) -> pd.DataFrame:
    """Convenience function to generate diurnal weather observations."""
    station = StationConfig(station_id=station_id)
    params = DiurnalParameters(random_seed=seed, **kwargs)
    generator = DiurnalGenerator(station_config=station, params=params, seed=seed)
    return generator.generate(
        start_date=start_date,
        duration_days=days,
        sampling_interval_min=sampling_interval_min,
        seed=seed,
    )

