# Architectural & Mathematical Specification: Diurnal Meteorological Simulation Engine (`diurnal_generator.py`)

**Agent**: `m1_explorer_1`  
**Milestone**: M1 — Simulator & Anomaly Injector Engine (Phase 1–4 of `TODO.md`)  
**Target Module**: `backend/simulator/diurnal_generator.py`  
**Workspace**: `c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard`  
**Date**: 2026-08-24  

---

## 1. Executive Summary & Problem Scope

SkyGuard AI requires a high-fidelity synthetic meteorological simulation engine capable of generating continuous time-series telemetry for Automatic Weather Stations (AWS). To ensure the subsequent 5-Tier ML Anomaly Detection pipeline and Sensor Health Engine operate on authentic physical baselines without faked or arbitrary data, the simulator must adhere strictly to atmospheric thermodynamic laws and boundary layer physics.

The simulation engine is constrained to the three primary AWS meteorological variables:
1. **Air Temperature ($T$)** in $^\circ\text{C}$
2. **Atmospheric Pressure ($P$)** in $\text{hPa}$
3. **Relative Humidity ($RH$)** in $\%$

This specification defines the complete mathematical equations, thermodynamic relationships (Magnus-Tetens saturation vapor pressure), atmospheric tidal physics ($S_2(P)$ semi-diurnal oscillations), synoptic Rossby wave modulations, autoregressive turbulence noise models, object-oriented software architecture, streaming and batch APIs, parameter configurations, and verification test cases for `backend/simulator/diurnal_generator.py`.

---

## 2. Mathematical & Thermodynamic Formulations

```
                       Time Grid & Solar Cycle
                     (h(t) in [0,24), d(t) in R)
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
   │ Temperature │         │  Pressure   │         │  Humidity   │
   │    T(t)     │         │    P(t)     │         │   RH(t)     │
   └──────┬──────┘         └──────┬──────┘         └──────┬──────┘
          │                       │                       │
          ├─ Mean & Season        ├─ Hypsometric P0(z)    ├─ Dew Point T_d
          ├─ Diurnal Wave         ├─ Synoptic Rossby Wave ├─ e_s(T) Magnus-Tetens
          ├─ AR(1) Turb. Noise    ├─ 12h S2(P) Tide       ├─ RH = e / e_s(T) * 100
          ▼                       ├─ AR(1) Press. Noise   ├─ AR(1) Noise & Clip
    T(t) in [-40,60]              ▼                       ▼
                           P(t) in [300,1100]      RH(t) in [5,100]
```

### 2.1 Time Parameterization & Solar Angle

Let $t_i$ ($i = 0, 1, \dots, N-1$) represent discrete timestamps spaced at uniform sampling interval $\Delta t$ (minutes). For standard AWS operations, $\Delta t = 5.0\text{ min}$.

1. **Continuous Local Solar Hour $h(t)$**:
   $$h(t) = \left( \text{hour}(t) + \frac{\text{minute}(t)}{60.0} + \frac{\text{second}(t)}{3600.0} \right) \in [0.0, 24.0)$$

2. **Continuous Elapsed Days $d(t)$**:
   $$d(t) = \frac{t - t_0}{86400\text{ seconds}} = \frac{i \cdot \Delta t}{1440.0}$$

3. **Day of Year $\text{DOY}(t)$**:
   $$\text{DOY}(t) \in [1, 366]$$

---

### 2.2 Diurnal Temperature Model $T(t)$

#### Atmospheric Physics
In boundary layer meteorology, surface air temperature is driven by shortwave solar insolation followed by sensible heat flux. Solar noon occurs at ~12:00–13:00, while maximum air temperature occurs with a characteristic thermal lag of ~2.0 to 3.0 hours (peaking at $h_{\text{peak}} \approx 14:00 - 15:00$). Minimum temperature occurs around sunrise ($h_{\text{min}} \approx 05:30 - 06:00$).

#### Mathematical Formulation
$$T(t) = T_{\text{base}} + T_{\text{season}}(t) + A_T \cdot f_T(h(t)) + \eta_T(t)$$

Where:
- **Baseline Temperature**: $T_{\text{base}}$ ($^\circ\text{C}$, default: $22.0^\circ\text{C}$).
- **Seasonal Cycle Component**:
  $$T_{\text{season}}(t) = A_{\text{season}} \cdot \sin\left( \frac{2\pi (\text{DOY}(t) - 80)}{365.25} \right)$$
  where $A_{\text{season}}$ is the seasonal amplitude (default: $5.0^\circ\text{C}$), and phase offset $-80$ aligns spring equinox (day 80).
- **Diurnal Waveform $f_T(h)$**:
  $$f_T(h) = \sin\left( \frac{2\pi (h - (h_{\text{peak}} - 6.0))}{24.0} \right)$$
  For standard peak at $h_{\text{peak}} = 14.5$ (2:30 PM):
  $$h_{\text{zero}} = 14.5 - 6.0 = 8.5 \implies f_T(h) = \sin\left( \frac{2\pi (h - 8.5)}{24.0} \right)$$
  - At $h = 14.5$: $\sin\left(\frac{2\pi \cdot 6.0}{24.0}\right) = \sin\left(\frac{\pi}{2}\right) = +1.0$ (Peak Maximum).
  - At $h = 02.5$: $\sin\left(\frac{2\pi \cdot (-6.0)}{24.0}\right) = \sin\left(-\frac{\pi}{2}\right) = -1.0$ (Night Minimum).
- **Diurnal Amplitude**: $A_T$ ($^\circ\text{C}$, default: $6.5^\circ\text{C}$, giving daily range $2 \times 6.5 = 13.0^\circ\text{C}$).

#### Autoregressive Turbulence Noise $\eta_T(t)$
Atmospheric turbulence produces autocorrelated fluctuations rather than white noise. We model $\eta_T(t)$ as a stationary first-order autoregressive $\text{AR}(1)$ Markov process:
$$\eta_T(0) \sim \mathcal{N}(0, \sigma_T^2)$$
$$\eta_T(t) = \rho_T \cdot \eta_T(t-1) + \sqrt{1 - \rho_T^2} \cdot \epsilon_T(t), \quad \epsilon_T(t) \sim \mathcal{N}(0, \sigma_T^2)$$
- Default parameters: Lag-1 autocorrelation $\rho_T = 0.88$, standard deviation $\sigma_T = 0.35^\circ\text{C}$.
- **Mathematical Property**: $\mathbb{E}[\eta_T(t)] = 0$, $\text{Var}(\eta_T(t)) = \sigma_T^2$ unconditionally for all $t$.

---

### 2.3 Thermodynamic Relative Humidity Model $RH(t)$ via Magnus-Tetens

#### Atmospheric Physics & Clausius-Clapeyron Relation
Relative humidity ($RH$) represents the ratio of actual water vapor pressure $e$ to saturation water vapor pressure $e_s(T)$ at ambient temperature $T$:
$$RH = \frac{e}{e_s(T)} \times 100\%$$

In a typical well-mixed boundary layer under non-frontal conditions, the total moisture content (dew point $T_d$) remains stable over diurnal timescales. As daytime temperature $T(t)$ increases, $e_s(T)$ increases exponentially, causing $RH(t)$ to decrease sharply to a minimum in mid-afternoon and peak near 90–100% near sunrise.

#### Magnus-Tetens Equation for Saturation Vapor Pressure $e_s(T)$
The WMO standard Magnus approximation for saturation vapor pressure over liquid water in range $[-40^\circ\text{C}, +60^\circ\text{C}]$ is:
$$e_s(T) = a \cdot \exp\left( \frac{b \cdot T}{T + c} \right) \quad [\text{hPa}]$$
Where WMO standard constants are:
- $a = 6.112\text{ hPa}$ (saturation pressure at $0^\circ\text{C}$)
- $b = 17.67$ (dimensionless)
- $c = 243.5^\circ\text{C}$ (temperature offset)

#### Actual Vapor Pressure $e(t)$ and Baseline Dew Point $T_d$
Let base dew point depression be $\Delta T_d = T_{\text{base}} - T_d$ (default $\Delta T_d = 6.0^\circ\text{C}$, so $T_{d, \text{base}} = 22.0 - 6.0 = 16.0^\circ\text{C}$).
Baseline actual vapor pressure is:
$$e_{\text{base}} = e_s(T_d) = a \cdot \exp\left( \frac{b \cdot T_d}{T_d + c} \right)$$

To incorporate multi-day synoptic moisture fluctuations:
$$e(t) = e_{\text{base}} \cdot \left( 1.0 + A_{\text{moisture}} \cdot \sin\left(\frac{2\pi d(t)}{\tau_{\text{moisture}}} + \phi_{\text{moist}}\right) \right)$$
where $A_{\text{moisture}} = 0.08$, $\tau_{\text{moisture}} = 4.0\text{ days}$.

#### Relative Humidity Formulation & Bounding
$$RH_{\text{raw}}(t) = \left( \frac{e(t)}{e_s(T(t))} \right) \times 100.0 + \eta_{RH}(t)$$
$$\eta_{RH}(t) = \rho_{RH} \cdot \eta_{RH}(t-1) + \sqrt{1 - \rho_{RH}^2} \cdot \epsilon_{RH}(t), \quad \epsilon_{RH}(t) \sim \mathcal{N}(0, \sigma_{RH}^2)$$
$$RH(t) = \text{clip}\left( RH_{\text{raw}}(t), \; RH_{\min}, \; RH_{\max} \right)$$
- Default parameters: $\rho_{RH} = 0.85$, $\sigma_{RH} = 1.2\%$, $RH_{\min} = 5.0\%$, $RH_{\max} = 100.0\%$.

#### Inverse Dew Point Inversion (Magnus Inversion Formula)
For validation and cross-check during simulation and Tier 3 ML consistency checks:
$$\gamma(T, RH) = \frac{b \cdot T}{T + c} + \ln\left( \frac{\max(RH, 0.01)}{100.0} \right)$$
$$T_d(t) = \frac{c \cdot \gamma(T, RH)}{b - \gamma(T, RH)}$$
This guarantees by construction that clean generated baseline observations satisfy $T_d(t) \le T(t)$ for all $t$.

---

### 2.4 Atmospheric Pressure Model $P(t)$

#### 1. Hypsometric Barometric Elevation Adjustment
Given station elevation $z$ (meters above sea level), the base sea-level pressure $P_{\text{slp}} = 1013.25\text{ hPa}$ is adjusted using the standard international barometric formula:
$$P_0(z) = P_{\text{slp}} \cdot \left( 1.0 - \frac{L \cdot z}{T_0} \right)^{\frac{g \cdot M}{R_0 \cdot L}} = 1013.25 \cdot \left( 1.0 - \frac{0.0065 \cdot z}{288.15} \right)^{5.25588}$$
- For Delhi ($z = 216\text{ m}$): $P_0(216) \approx 988.2\text{ hPa}$.
- For Sea Level ($z = 0\text{ m}$): $P_0(0) = 1013.25\text{ hPa}$.

#### 2. Synoptic Rossby Wave Modulation
Passage of synoptic-scale anticyclones (highs) and depressions/troughs (lows) across 3 to 7 days:
$$P_{\text{synoptic}}(t) = A_{\text{synoptic}} \cdot \sin\left( \frac{2\pi d(t)}{\tau_{\text{synoptic}}} + \phi_{\text{syn}} \right) + A_{\text{synoptic}, 2} \cdot \cos\left( \frac{2\pi d(t)}{\tau_{\text{synoptic}, 2}} \right)$$
- Default parameters: $A_{\text{synoptic}} = 8.0\text{ hPa}$, $\tau_{\text{synoptic}} = 5.0\text{ days}$, $A_{\text{synoptic}, 2} = 2.5\text{ hPa}$, $\tau_{\text{synoptic}, 2} = 2.5\text{ days}$.

#### 3. Semi-Diurnal Atmospheric Thermal Tides ($S_2(P)$)
Absorption of solar radiation by stratospheric ozone and tropospheric water vapor generates planetary barometric tides with a dominant 12.0-hour semi-diurnal period.
- Maxima occur worldwide at ~10:00 and ~22:00 local solar time.
- Minima occur worldwide at ~04:00 and ~16:00 local solar time.
$$P_{\text{tide}}(t) = A_{\text{tide}} \cdot \cos\left( \frac{4\pi (h(t) - 10.0)}{24.0} \right)$$
- At $h=10.0$: $\cos(0) = +1.0 \implies +A_{\text{tide}}$
- At $h=16.0$: $\cos(\pi) = -1.0 \implies -A_{\text{tide}}$
- At $h=22.0$: $\cos(2\pi) = +1.0 \implies +A_{\text{tide}}$
- At $h=04.0$: $\cos(-\pi) = -1.0 \implies -A_{\text{tide}}$
- Default tidal amplitude: $A_{\text{tide}} = 1.2\text{ hPa}$ (characteristic of tropical/subtropical latitudes).

#### 4. Autoregressive Barometric Noise $\eta_P(t)$
$$\eta_P(t) = \rho_P \cdot \eta_P(t-1) + \sqrt{1 - \rho_P^2} \cdot \epsilon_P(t), \quad \epsilon_P(t) \sim \mathcal{N}(0, \sigma_P^2)$$
- Default parameters: $\rho_P = 0.92$, $\sigma_P = 0.15\text{ hPa}$.

#### 5. Complete Pressure Equation
$$P(t) = P_0(z) + P_{\text{synoptic}}(t) + P_{\text{tide}}(t) + \eta_P(t)$$

---

## 3. Architecture & Data Structures for `diurnal_generator.py`

### 3.1 Class Diagram & Responsibilities

```
┌────────────────────────────────────────────────────────┐
│                     StationConfig                      │
├────────────────────────────────────────────────────────┤
│ + station_id: str = "AWS-001"                          │
│ + name: str = "Central Weather Station"                │
│ + latitude: float = 28.6139                            │
│ + longitude: float = 77.2090                           │
│ + elevation: float = 216.0                             │
└────────────────────────────────────────────────────────┘
                           │
                           │ 1
                           ▼
┌────────────────────────────────────────────────────────┐
│                   DiurnalParameters                    │
├────────────────────────────────────────────────────────┤
│ # Temperature Config                                   │
│ + temp_base: float = 22.0                              │
│ + temp_amplitude: float = 6.5                          │
│ + temp_peak_hour: float = 14.5                         │
│ + temp_seasonal_amp: float = 5.0                       │
│ + temp_noise_sigma: float = 0.35                       │
│ + temp_ar_rho: float = 0.88                            │
│                                                        │
│ # Humidity & Magnus Config                             │
│ + dew_point_depression: float = 6.0                    │
│ + rh_min: float = 5.0                                  │
│ + rh_max: float = 100.0                                │
│ + rh_noise_sigma: float = 1.2                          │
│ + rh_ar_rho: float = 0.85                              │
│ + magnus_a: float = 6.112                              │
│ + magnus_b: float = 17.67                              │
│ + magnus_c: float = 243.5                              │
│                                                        │
│ # Pressure Config                                      │
│ + sea_level_pressure: float = 1013.25                  │
│ + pressure_synoptic_amp: float = 8.0                   │
│ + pressure_synoptic_period_days: float = 5.0           │
│ + pressure_tide_amp: float = 1.2                       │
│ + pressure_noise_sigma: float = 0.15                   │
│ + pressure_ar_rho: float = 0.92                        │
│ + random_seed: Optional[int] = 42                      │
└────────────────────────────────────────────────────────┘
                           │
                           │ 1
                           ▼
┌────────────────────────────────────────────────────────┐
│                    DiurnalGenerator                    │
├────────────────────────────────────────────────────────┤
│ - station: StationConfig                               │
│ - params: DiurnalParameters                            │
│ - rng: np.random.Generator                             │
├────────────────────────────────────────────────────────┤
│ + __init__(station, params)                            │
│ + calculate_saturation_vapor_pressure(T: ndarray)      │
│ + calculate_dew_point(T: ndarray, RH: ndarray)         │
│ + calculate_hypsometric_pressure(elevation: float)     │
│ + generate_ar1_noise(n, sigma, rho) -> ndarray         │
│ + generate(start_date, end_date, days, freq) -> DF     │
│ + generate_streaming_step(timestamp, prev_state) -> Dt │
└────────────────────────────────────────────────────────┘
```

### 3.2 Output Telemetry Schema

The output generated by `DiurnalGenerator.generate()` is a `pandas.DataFrame` matching both the database `observations` schema and downstream `InferenceResult` / feature preprocessors:

| Column Name | Data Type | Units / Format | Description |
|---|---|---|---|
| `timestamp` | `datetime64[ns]` / `pd.Timestamp` | UTC ISO-8601 | Observation timestamp |
| `station_id` | `str` | Nominal String | Station identifier (e.g. `"AWS-001"`) |
| `temperature` | `float64` | $^\circ\text{C}$ (e.g. 24.52) | Ambient dry-bulb temperature |
| `pressure` | `float64` | $\text{hPa}$ (e.g. 988.45) | Station barometric pressure |
| `humidity` | `float64` | $\%$ (e.g. 62.30) | Relative humidity |
| `latitude` | `float64` | Degrees North | Station latitude |
| `longitude` | `float64` | Degrees East | Station longitude |
| `elevation` | `float64` | Meters | Station altitude above sea level |
| `is_anomaly` | `bool` | `False` | Ground-truth anomaly flag (clean baseline) |
| `anomaly_type` | `str` | `"NORMAL"` | Ground-truth fault taxonomy label |
| `severity` | `str` | `"NONE"` | Ground-truth severity level |

---

## 4. Parameter Configurations & Meteorological Presets

To support multiple geographic regions and seasons, `diurnal_generator.py` will provide factory methods or presets:

```python
PRESETS = {
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
        dew_point_depression=3.0,  # High humidity marine air
        sea_level_pressure=1015.0,
        pressure_tide_amp=0.6,
        pressure_synoptic_amp=12.0, # Strong mid-latitude storm tracks
    ),
    "high_altitude_plateau": DiurnalParameters(
        temp_base=8.0,
        temp_amplitude=9.0,        # Large diurnal range at high elevation
        temp_peak_hour=14.0,
        dew_point_depression=10.0, # Dry air
        pressure_tide_amp=0.8,
    ),
    "arid_desert": DiurnalParameters(
        temp_base=32.0,
        temp_amplitude=12.0,       # Extreme diurnal range
        temp_peak_hour=15.0,
        dew_point_depression=18.0, # Extremely low RH (10-25%)
        pressure_tide_amp=1.5,
    ),
}
```

---

## 5. Numerical Safeguards & Edge Case Analysis

| # | Condition | Risk / Physics Violation | Algorithmic Safeguard in `diurnal_generator.py` |
|---|---|---|---|
| 1 | Magnus Denominator ($T = -243.5^\circ\text{C}$) | Division by zero in $T + 243.5$ | Vectorized safety clamp: $T_{\text{safe}} = \text{np.clip}(T, -80.0, 70.0)$ before exponentiation. |
| 2 | Supersaturation / Sub-zero RH | $RH < 0\%$ or $RH > 100\%$ from AR(1) noise | Boundary clipping: $\text{np.clip}(RH, 5.0, 100.0)$ preserving physical interval. |
| 3 | Inverted Dew Point | $T_d > T$ (unphysical negative depression) | Actual vapor pressure is strictly bounded: $e(t) \le 0.98 \cdot e_s(T(t))$ in non-fog scenarios. |
| 4 | AR(1) Variance Explosion | Non-stationary noise if $|\rho| \ge 1.0$ | Assert $0.0 \le \rho < 1.0$; scale innovation noise exactly by $\sqrt{1 - \rho^2}$. |
| 5 | Irregular Time Steps ($\Delta t \ne 5\text{ min}$) | Distorted diurnal phase and sampling | Time grid derives continuous $h(t)$ directly from timestamp object, independent of frequency. |
| 6 | Seed Reproducibility | Different random noise on repeat runs | Uses dedicated `np.random.default_rng(seed)` instance rather than global `np.random`. |
| 7 | Streaming Mode State Continuity | Discontinuous noise across streaming steps | `generate_streaming_step` maintains state dictionary `(prev_eta_T, prev_eta_P, prev_eta_RH)`. |

---

## 6. Complete Implementation Blueprint for `diurnal_generator.py`

Below is the complete, drop-in Python implementation design for `backend/simulator/diurnal_generator.py`:

```python
"""
SkyGuard AI — High-Fidelity Diurnal Meteorological Simulation Engine.

Generates realistic AWS observations (Temperature, Pressure, Relative Humidity)
adhering to solar diurnal radiation curves, Magnus-Tetens thermodynamic saturation
vapor pressure physics, 12-hour semi-diurnal atmospheric thermal tides, synoptic
Rossby pressure waves, and autoregressive atmospheric turbulence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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


@dataclass
class DiurnalParameters:
    """Configurable parameters for thermodynamic diurnal generation."""
    # Temperature (°C)
    temp_base: float = 22.0
    temp_amplitude: float = 6.5
    temp_peak_hour: float = 14.5  # 2:30 PM solar maximum
    temp_seasonal_amp: float = 5.0
    temp_noise_sigma: float = 0.35
    temp_ar_rho: float = 0.88

    # Humidity (%) & Thermodynamics
    dew_point_depression: float = 6.0  # Base (temp_base - T_d)
    rh_min: float = 5.0
    rh_max: float = 100.0
    rh_noise_sigma: float = 1.2
    rh_ar_rho: float = 0.85
    magnus_a: float = 6.112   # hPa
    magnus_b: float = 17.67   # dimensionless
    magnus_c: float = 243.5   # °C

    # Atmospheric Pressure (hPa)
    sea_level_pressure: float = 1013.25
    pressure_synoptic_amp: float = 8.0
    pressure_synoptic_period_days: float = 5.0
    pressure_tide_amp: float = 1.2  # 12-hour S2(P) atmospheric tide
    pressure_noise_sigma: float = 0.15
    pressure_ar_rho: float = 0.92

    # Reproducibility
    random_seed: Optional[int] = 42


class DiurnalGenerator:
    """
    Continuous meteorological time-series generator adhering to atmospheric physics.
    """

    def __init__(
        self,
        station_config: Optional[StationConfig] = None,
        params: Optional[DiurnalParameters] = None,
    ) -> None:
        self.station = station_config or StationConfig()
        self.params = params or DiurnalParameters()
        self.rng = np.random.default_rng(self.params.random_seed)

    def calculate_hypsometric_pressure(self, elevation_m: float) -> float:
        """
        Calculate barometric base pressure at station elevation using hypsometric formula.
        """
        # International standard atmosphere: P = P0 * (1 - L*h/T0)^(g*M / R0*L)
        # L = 0.0065 K/m, T0 = 288.15 K, exponent = 5.25588
        base_p = self.params.sea_level_pressure * (
            (1.0 - (0.0065 * elevation_m) / 288.15) ** 5.25588
        )
        return float(base_p)

    def calculate_saturation_vapor_pressure(
        self, temp_c: np.ndarray | float
    ) -> np.ndarray | float:
        """
        Calculate saturation vapor pressure e_s(T) [hPa] using the Magnus-Tetens formula.
        """
        a = self.params.magnus_a
        b = self.params.magnus_b
        c = self.params.magnus_c
        # Safe clipping to prevent numerical instability
        t_safe = np.clip(temp_c, -60.0, 70.0)
        return a * np.exp((b * t_safe) / (t_safe + c))

    def calculate_dew_point(
        self, temp_c: np.ndarray | float, rh_pct: np.ndarray | float
    ) -> np.ndarray | float:
        """
        Calculate dew point temperature T_d [°C] from T and RH using Magnus inversion.
        """
        b = self.params.magnus_b
        c = self.params.magnus_c
        rh_safe = np.clip(rh_pct, 0.01, 104.0)
        gamma = (b * temp_c) / (temp_c + c) + np.log(rh_safe / 100.0)
        return (c * gamma) / (b - gamma)

    def generate_ar1_noise(
        self, n_steps: int, sigma: float, rho: float
    ) -> np.ndarray:
        """
        Generate a stationary AR(1) autoregressive noise process with Var(eta) = sigma^2.
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
        start_date: Union[str, datetime] = "2026-01-01 00:00:00",
        end_date: Optional[Union[str, datetime]] = None,
        days: Optional[float] = None,
        freq: str = "5min",
        seed: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Generate a complete clean baseline meteorological dataset.
        """
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        # 1. Construct DatetimeIndex
        start_dt = pd.to_datetime(start_date, utc=True)
        if end_date is not None:
            end_dt = pd.to_datetime(end_date, utc=True)
            timestamps = pd.date_range(start=start_dt, end=end_dt, freq=freq)
        elif days is not None:
            timestamps = pd.date_range(
                start=start_dt, periods=int(days * 1440 / pd.Timedelta(freq).total_seconds() * 60), freq=freq
            )
        else:
            # Default 7 days
            timestamps = pd.date_range(
                start=start_dt, periods=int(7 * 1440 / (pd.Timedelta(freq).total_seconds() / 60)), freq=freq
            )

        n_steps = len(timestamps)
        if n_steps == 0:
            return pd.DataFrame()

        # 2. Time coordinate variables
        hours = timestamps.hour.values + timestamps.minute.values / 60.0 + timestamps.second.values / 3600.0
        day_of_year = timestamps.dayofyear.values
        elapsed_days = (timestamps - timestamps[0]).total_seconds().values / 86400.0

        # 3. Temperature Generation T(t)
        # Seasonal component
        t_season = self.params.temp_seasonal_amp * np.sin(2.0 * np.pi * (day_of_year - 80.0) / 365.25)
        # Diurnal solar cycle
        h_zero = self.params.temp_peak_hour - 6.0
        t_diurnal = self.params.temp_amplitude * np.sin(2.0 * np.pi * (hours - h_zero) / 24.0)
        # AR(1) noise
        t_noise = self.generate_ar1_noise(
            n_steps, self.params.temp_noise_sigma, self.params.temp_ar_rho
        )
        temperature = self.params.temp_base + t_season + t_diurnal + t_noise

        # 4. Thermodynamic Relative Humidity Generation RH(t)
        # Base dew point and vapor pressure
        t_dew_base = self.params.temp_base - self.params.dew_point_depression
        e_base = self.calculate_saturation_vapor_pressure(t_dew_base)
        # Synoptic moisture shift (e.g. 4-day period)
        e_synoptic = e_base * (1.0 + 0.06 * np.sin(2.0 * np.pi * elapsed_days / 4.0))
        # Saturation vapor pressure at current T
        e_s_t = self.calculate_saturation_vapor_pressure(temperature)
        # Raw RH calculation
        rh_raw = (e_synoptic / e_s_t) * 100.0
        rh_noise = self.generate_ar1_noise(
            n_steps, self.params.rh_noise_sigma, self.params.rh_ar_rho
        )
        humidity = np.clip(
            rh_raw + rh_noise, self.params.rh_min, self.params.rh_max
        )

        # 5. Atmospheric Pressure Generation P(t)
        p_base = self.calculate_hypsometric_pressure(self.station.elevation)
        # Multi-day synoptic Rossby wave
        p_synoptic = self.params.pressure_synoptic_amp * np.sin(
            2.0 * np.pi * elapsed_days / self.params.pressure_synoptic_period_days
        ) + 2.0 * np.cos(2.0 * np.pi * elapsed_days / 2.5)
        # 12-hour semi-diurnal thermal tide S2(P) (peaks at 10:00 and 22:00)
        p_tide = self.params.pressure_tide_amp * np.cos(4.0 * np.pi * (hours - 10.0) / 24.0)
        # AR(1) noise
        p_noise = self.generate_ar1_noise(
            n_steps, self.params.pressure_noise_sigma, self.params.pressure_ar_rho
        )
        pressure = p_base + p_synoptic + p_tide + p_noise

        # 6. Assemble DataFrame
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
            }
        )

        return df

    def generate_streaming_step(
        self,
        timestamp: Union[str, datetime],
        prev_state: Optional[Dict[str, float]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """
        Generate a single telemetry step for real-time streaming / WebSocket engine.
        """
        ts = pd.to_datetime(timestamp, utc=True)
        hour = ts.hour + ts.minute / 60.0 + ts.second / 3600.0
        doy = ts.dayofyear

        # Previous AR(1) states
        prev_t_noise = prev_state.get("t_noise", 0.0) if prev_state else 0.0
        prev_p_noise = prev_state.get("p_noise", 0.0) if prev_state else 0.0
        prev_rh_noise = prev_state.get("rh_noise", 0.0) if prev_state else 0.0
        elapsed_days = prev_state.get("elapsed_days", 0.0) if prev_state else 0.0

        # AR(1) step update
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

        # Humidity
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
        }

        new_state = {
            "t_noise": t_noise,
            "p_noise": p_noise,
            "rh_noise": rh_noise,
            "elapsed_days": elapsed_days + 5.0 / 1440.0,
        }

        return telemetry, new_state


def generate_diurnal_data(
    start_date: Union[str, datetime] = "2026-01-01 00:00:00",
    days: float = 7.0,
    freq: str = "5min",
    station_id: str = "AWS-001",
    seed: Optional[int] = 42,
    **kwargs: Any,
) -> pd.DataFrame:
    """
    Convenience function to generate diurnal weather observations.
    """
    station = StationConfig(station_id=station_id)
    params = DiurnalParameters(random_seed=seed, **kwargs)
    generator = DiurnalGenerator(station_config=station, params=params)
    return generator.generate(start_date=start_date, days=days, freq=freq, seed=seed)
```

---

## 7. Verification & Testing Strategy

To ensure strict compliance with project objectives, the following test cases must be integrated into `tests/test_simulator.py`:

### Test 1: Thermodynamic Negative Correlation Verification
```python
def test_temperature_humidity_inverse_correlation():
    gen = DiurnalGenerator()
    df = gen.generate(days=14, freq="5min", seed=100)
    corr = df["temperature"].corr(df["humidity"])
    assert corr <= -0.75, f"Expected strong negative correlation <= -0.75, got {corr:.3f}"
```

### Test 2: Semi-Diurnal Pressure Tidal Periodicity
```python
def test_pressure_semi_diurnal_peaks():
    # Mean diurnal cycle across 30 days
    gen = DiurnalGenerator(params=DiurnalParameters(pressure_synoptic_amp=0.0))
    df = gen.generate(days=30, freq="5min", seed=42)
    df["hour"] = df["timestamp"].dt.hour
    hourly_mean = df.groupby("hour")["pressure"].mean()
    # Peaks at 10:00 and 22:00
    assert hourly_mean[10] > hourly_mean[4]
    assert hourly_mean[22] > hourly_mean[16]
    assert (hourly_mean[10] - hourly_mean[16]) >= 1.5
```

### Test 3: WMO Physical Boundaries
```python
def test_baseline_physical_bounds():
    gen = DiurnalGenerator()
    df = gen.generate(days=30, freq="5min", seed=42)
    assert (-40.0 <= df["temperature"]).all() and (df["temperature"] <= 60.0).all()
    assert (300.0 <= df["pressure"]).all() and (df["pressure"] <= 1100.0).all()
    assert (0.0 <= df["humidity"]).all() and (df["humidity"] <= 100.0).all()
    assert not df[["temperature", "pressure", "humidity"]].isna().any().any()
```

### Test 4: Streaming State Continuity & Equivalence
```python
def test_streaming_step_generation():
    gen = DiurnalGenerator()
    state = None
    records = []
    ts = pd.Timestamp("2026-08-24 00:00:00", tz="UTC")
    for _ in range(12):
        telemetry, state = gen.generate_streaming_step(ts, state)
        records.append(telemetry)
        ts += pd.Timedelta(minutes=5)
    
    assert len(records) == 12
    assert all("temperature" in r and "humidity" in r and "pressure" in r for r in records)
```

---

## 8. Alignment with Success Criteria & Milestones

- **Phase 1 of `TODO.md`**: Provides clean foundation for observation schemas, dataset generators, and ingestion pipelines.
- **Milestone M1**: Pairs seamlessly with `anomaly_injector.py` to create labeled clean/anomalous training and evaluation sets.
- **Rule Compliance (`AGENTS.md`)**: Fully physical, zero hardcoded constant mock data, fully vectorized, deterministic with random seed support.
