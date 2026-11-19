"""
backend/app/ml/stage3_physics.py
DataMend — Stage 3A: Thermodynamic Physical Consistency Validator.

Enforces meteorological physical invariants across correlated sensor channels:
1. Magnus-Tetens Clausius-Clapeyron Dew Point Boundary: T_dew <= T_air + 0.1°C
2. Barometric Hypsometric Sea-Level Pressure Consistency: Compares observed station pressure
   against barometric formula given station elevation.
3. Psychrometric Flat-Humidity / Temperature-Swing Invariance: Flags stuck RH sensors when
   ambient temperature fluctuates significantly while humidity remains artificially flat.

Flags MULTIVARIATE_INCONSISTENCY deterministically for impossible physical states.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

MULTIVARIATE_FLAG = "MULTIVARIATE_INCONSISTENCY"
DEWPOINT_MARGIN_C = 0.1
PRESSURE_TOLERANCE_HPA = 80.0


def calculate_magnus_dew_point(temp_c: float | np.ndarray, humidity_pct: float | np.ndarray) -> np.ndarray:
    """
    Computes dew point temperature (°C) using the Magnus-Tetens formulation
    (Alduchov & Eskridge 1996 approximation).
    """
    t = np.asarray(temp_c, dtype=float)
    rh = np.clip(np.asarray(humidity_pct, dtype=float), 0.01, 100.0)

    a = 17.625
    b = 243.04
    alpha = ((a * t) / (b + t)) + np.log(rh / 100.0)
    dew_point = (b * alpha) / (a - alpha)
    return np.asarray(dew_point, dtype=float)


def compute_hypsometric_slp(
    station_pressure_hpa: float | np.ndarray,
    temp_c: float | np.ndarray,
    elevation_m: float,
) -> np.ndarray:
    """
    Calculates sea-level pressure (hPa) from station atmospheric pressure using the barometric formula.
    """
    p = np.asarray(station_pressure_hpa, dtype=float)
    t = np.asarray(temp_c, dtype=float)
    t_kelvin = t + 273.15
    # Standard lapse rate = 0.0065 K/m, barometric exponent = 5.255
    factor = 1.0 - (0.0065 * elevation_m) / (t_kelvin + 0.0065 * elevation_m)
    # Clip factor to prevent numerical overflow at extreme elevation
    factor = np.clip(factor, 0.5, 1.5)
    return p * (factor ** -5.255)


@dataclass
class PhysicsValidationResult:
    """Diagnostic outcome of thermodynamic consistency check."""
    is_valid: bool
    flag: Optional[str]  # 'MULTIVARIATE_INCONSISTENCY' or None
    dew_point_c: float
    expected_slp_hpa: Optional[float]
    dew_point_violated: bool
    pressure_violated: bool
    psychrometric_violated: bool
    diagnostic_message: str


class ThermodynamicPhysicsValidator:
    """
    Evaluates physical atmospheric laws across concurrent (T, P, RH) observations.
    """

    def __init__(
        self,
        dewpoint_margin_c: float = DEWPOINT_MARGIN_C,
        pressure_tolerance_hpa: float = PRESSURE_TOLERANCE_HPA,
    ) -> None:
        self.dewpoint_margin_c = dewpoint_margin_c
        self.pressure_tolerance_hpa = pressure_tolerance_hpa

    def validate_reading(
        self,
        temperature_c: Optional[float],
        pressure_hpa: Optional[float],
        humidity_pct: Optional[float],
        altitude_m: float = 0.0,
        dew_point_c: Optional[float] = None,
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> PhysicsValidationResult:
        """
        Validates an instantaneous AWS observation against thermodynamic laws.
        """
        if temperature_c is None or pressure_hpa is None or humidity_pct is None:
            return PhysicsValidationResult(
                is_valid=False,
                flag=MULTIVARIATE_FLAG,
                dew_point_c=0.0,
                expected_slp_hpa=None,
                dew_point_violated=False,
                pressure_violated=False,
                psychrometric_violated=False,
                diagnostic_message="Missing one or more required thermodynamic parameters (T, P, RH).",
            )

        # 1. Clausius-Clapeyron Dew Point Check
        if dew_point_c is not None:
            tdew = float(dew_point_c)
            dew_bad = bool(tdew > (temperature_c + self.dewpoint_margin_c))
        else:
            tdew = float(calculate_magnus_dew_point(temperature_c, min(100.0, humidity_pct)))
            dew_bad = bool(humidity_pct > 100.0)

        # 2. Hypsometric Barometric Pressure Consistency
        expected_slp = float(compute_hypsometric_slp(pressure_hpa, temperature_c, altitude_m))
        # Standard sea level pressure is 1013.25 hPa
        press_bad = bool(abs(expected_slp - 1013.25) > self.pressure_tolerance_hpa)

        # 3. Psychrometric Flat-Humidity / Temperature-Swing Check
        psychro_bad = False
        if recent_history and len(recent_history) >= 3:
            recent_readings = recent_history[-3:] + [{
                "temperature_c": temperature_c,
                "humidity_pct": humidity_pct,
            }]
            temps = [r["temperature_c"] for r in recent_readings if r.get("temperature_c") is not None]
            hums = [r["humidity_pct"] for r in recent_readings if r.get("humidity_pct") is not None]
            if len(temps) == 4 and len(hums) == 4:
                temp_swing = max(temps) - min(temps)
                hum_var = float(np.var(hums))
                if temp_swing > 3.0 and hum_var < 1e-4:
                    psychro_bad = True

        is_violating = dew_bad or press_bad or psychro_bad
        flag = MULTIVARIATE_FLAG if is_violating else None

        messages = []
        if dew_bad:
            messages.append(f"Dew point ({tdew:.1f}°C) exceeds air temperature ({temperature_c:.1f}°C)")
        if press_bad:
            messages.append(f"Reduced SLP ({expected_slp:.1f} hPa) violates standard barometric bounds")
        if psychro_bad:
            messages.append("Humidity flatlined during significant temperature swing (>3°C)")

        diagnostic = "; ".join(messages) if messages else "Thermodynamic laws satisfied."

        return PhysicsValidationResult(
            is_valid=not is_violating,
            flag=flag,
            dew_point_c=round(tdew, 2),
            expected_slp_hpa=round(expected_slp, 2),
            dew_point_violated=dew_bad,
            pressure_violated=press_bad,
            psychrometric_violated=psychro_bad,
            diagnostic_message=diagnostic,
        )
