"""
backend/app/ml/stage1_stl.py
SkyGuard AI / DataMend — Stage 1: Per-Station Seasonal-Trend Decomposition (STL) & Cold-Start Inheritance.

Extracts diurnal meteorological cycles using Seasonal-Trend decomposition using LOESS (STL).
Isolates true sensor hardware and physical anomalies by scoring de-trended, de-seasonalized residuals:
    Residual(t) = Raw(t) - Trend(t) - Seasonal(t)

For stations with < 7 days of observation history, prevents overfitting and erroneous variance
by inheriting the seasonal baseline of the top-1 correlated established cluster member.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CHANNELS: List[str] = ["temperature_c", "pressure_hpa", "humidity_pct"]
RESIDUAL_COLUMNS: List[str] = ["temperature_c_resid", "pressure_hpa_resid", "humidity_pct_resid"]
COLD_START_MIN_DAYS: float = 7.0


def infer_diurnal_period(n_samples: int, samples_per_day: Optional[int] = None) -> int:
    """
    Infers diurnal cycle periodicity from sample count or explicit metadata.
    96 steps = 15-min intervals, 24 steps = 1-hour intervals.
    """
    if samples_per_day is not None and samples_per_day >= 4:
        return int(samples_per_day)
    # Default to 96 (standard IMD/AWS 15-minute telemetry interval) or 24 (hourly)
    if n_samples >= 192:
        return 96
    if n_samples >= 48:
        return 24
    return 24


def decompose_series_stl(series: np.ndarray, period: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Decomposes 1D series into (trend, seasonal, resid).
    Employs statsmodels robust STL with fallback to centered moving-average and periodic averaging.
    """
    series_clean = np.asarray(series, dtype=float)
    # Handle NaNs using linear interpolation and forward/backward fill
    if np.isnan(series_clean).any():
        s_series = pd.Series(series_clean).interpolate().bfill().ffill()
        series_clean = s_series.to_numpy(dtype=float)

    n = len(series_clean)
    if n < period * 2:
        # Insufficient span for full LOESS; return mean-centered residual
        trend = np.full(n, np.nanmean(series_clean))
        seasonal = np.zeros(n)
        resid = series_clean - trend
        return trend, seasonal, resid

    try:
        from statsmodels.tsa.seasonal import STL

        stl = STL(series_clean, period=period, robust=True)
        res = stl.fit()
        return np.asarray(res.trend), np.asarray(res.seasonal), np.asarray(res.resid)
    except Exception as exc:
        # Fallback to centered convolution filter and periodic hourly mean
        logger.debug("Falling back to rolling convolution STL: %s", exc)
        window = max(3, period)
        trend = np.convolve(series_clean, np.ones(window) / window, mode="same")
        detrended = series_clean - trend
        seasonal = np.zeros(n)
        for p in range(period):
            idx = np.arange(p, n, period)
            if len(idx) > 0:
                seasonal[idx] = float(np.nanmean(detrended[idx]))
        resid = series_clean - trend - seasonal
        return trend, seasonal, resid


@dataclass
class StationBaseline:
    """Cached diurnal baseline profile for an individual AWS station."""
    station_id: str
    period: int
    means: Dict[str, float]
    stds: Dict[str, float]
    seasonal_profiles: Dict[str, np.ndarray]  # (period,) diurnal shape per parameter
    inherited: bool = False
    donor_id: Optional[str] = None
    history_days: float = 0.0

    def compute_residuals(self, df_or_arr: pd.DataFrame | np.ndarray) -> np.ndarray:
        """
        Computes residual vector [T_resid, P_resid, RH_resid] for an incoming window.
        Uses time-of-day modular indexing into the stored diurnal profile.
        """
        if isinstance(df_or_arr, pd.DataFrame):
            df = df_or_arr
            n = len(df)
            if isinstance(df.index, pd.DatetimeIndex):
                tod_idx = (df.index.hour * (self.period // 24) + df.index.minute // (1440 // self.period)) % self.period
            else:
                tod_idx = np.arange(n) % self.period

            resids = []
            for col in CHANNELS:
                vals = pd.to_numeric(df.get(col, 0.0), errors="coerce").fillna(self.means.get(col, 0.0)).to_numpy()
                seas = np.array([self.seasonal_profiles[col][idx] for idx in tod_idx])
                mean = self.means[col]
                # Residual = observed - expected baseline (mean + diurnal phase)
                resids.append(vals - (mean + seas))
            return np.column_stack(resids)

        # Raw numpy array (n, 3) format
        arr = np.asarray(df_or_arr, dtype=float)
        n = arr.shape[0]
        tod_idx = np.arange(n) % self.period
        resids = []
        for i, col in enumerate(CHANNELS):
            vals = arr[:, i]
            seas = np.array([self.seasonal_profiles[col][idx] for idx in tod_idx])
            mean = self.means[col]
            resids.append(vals - (mean + seas))
        return np.column_stack(resids)


class STLBaselineEngine:
    """Manages fitting, caching, and evaluation of per-station STL baselines."""

    def __init__(self, default_period: int = 96) -> None:
        self.default_period = default_period
        self.baselines: Dict[str, StationBaseline] = {}

    def fit_station(
        self,
        station_id: str,
        df: pd.DataFrame,
        history_days: Optional[float] = None,
        samples_per_day: Optional[int] = None,
    ) -> StationBaseline:
        """
        Fits robust STL diurnal profiles for temperature, pressure, and humidity.
        """
        n_samples = len(df)
        period = infer_diurnal_period(n_samples, samples_per_day)
        calc_days = history_days if history_days is not None else (n_samples / max(1, period))

        means: Dict[str, float] = {}
        stds: Dict[str, float] = {}
        seasonal_profiles: Dict[str, np.ndarray] = {}

        for col in CHANNELS:
            vals = pd.to_numeric(df.get(col, 0.0), errors="coerce").interpolate().bfill().ffill().to_numpy()
            mean_val = float(np.nanmean(vals)) if len(vals) > 0 else 0.0
            std_val = float(np.nanstd(vals)) if len(vals) > 0 and np.nanstd(vals) > 0 else 1.0
            means[col] = mean_val
            stds[col] = std_val

            _, seasonal, _ = decompose_series_stl(vals, period)
            # Average the seasonal component across days to construct a robust 24-hour master profile
            hourly_idx = np.arange(len(seasonal)) % period
            profile = np.zeros(period)
            for h in range(period):
                mask = hourly_idx == h
                profile[h] = float(np.nanmean(seasonal[mask])) if np.any(mask) else 0.0
            seasonal_profiles[col] = profile

        baseline = StationBaseline(
            station_id=station_id,
            period=period,
            means=means,
            stds=stds,
            seasonal_profiles=seasonal_profiles,
            inherited=False,
            donor_id=None,
            history_days=calc_days,
        )
        self.baselines[station_id] = baseline
        return baseline

    def transfer_baseline(
        self,
        target_station_id: str,
        donor_station_id: str,
        target_df: pd.DataFrame,
        history_days: float = 1.0,
    ) -> StationBaseline:
        """
        Transfers the diurnal profile shape from a donor station to a cold-start station,
        rescaling the amplitudes by local target standard deviation.
        """
        donor = self.baselines.get(donor_station_id)
        if donor is None:
            raise KeyError(f"Donor station '{donor_station_id}' not found in registered baselines.")

        means: Dict[str, float] = {}
        stds: Dict[str, float] = {}
        seasonal_profiles: Dict[str, np.ndarray] = {}

        for col in CHANNELS:
            vals = pd.to_numeric(target_df.get(col, 0.0), errors="coerce").interpolate().bfill().ffill().to_numpy()
            mean_val = float(np.nanmean(vals)) if len(vals) > 0 else donor.means[col]
            std_val = float(np.nanstd(vals)) if len(vals) > 0 and np.nanstd(vals) > 0 else donor.stds[col]
            means[col] = mean_val
            stds[col] = std_val

            donor_std = donor.stds.get(col, 1.0)
            scale = std_val / donor_std if donor_std > 0 else 1.0
            seasonal_profiles[col] = donor.seasonal_profiles[col] * scale

        baseline = StationBaseline(
            station_id=target_station_id,
            period=donor.period,
            means=means,
            stds=stds,
            seasonal_profiles=seasonal_profiles,
            inherited=True,
            donor_id=donor_station_id,
            history_days=history_days,
        )
        self.baselines[target_station_id] = baseline
        return baseline

    def get_residuals(self, station_id: str, df_or_arr: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Computes de-trended residual vector for a station."""
        baseline = self.baselines.get(station_id)
        if baseline is None:
            # Fallback: compute residual against available baseline or standard atmosphere
            if isinstance(df_or_arr, pd.DataFrame):
                arr = df_or_arr[CHANNELS].to_numpy(dtype=float)
            else:
                arr = np.asarray(df_or_arr, dtype=float)
            if len(arr) > 1:
                ref = np.nanmedian(arr, axis=0)
            elif self.baselines:
                first_b = next(iter(self.baselines.values()))
                ref = np.array([first_b.means["temperature_c"], first_b.means["pressure_hpa"], first_b.means["humidity_pct"]])
            else:
                ref = np.array([20.0, 1013.25, 60.0])
            return arr - ref
        return baseline.compute_residuals(df_or_arr)

    def get(self, station_id: str) -> Optional[StationBaseline]:
        """Retrieves cached baseline for a station."""
        return self.baselines.get(station_id)


def cluster_and_initialize_baselines(
    all_station_data: Dict[str, pd.DataFrame],
    min_history_days: float = COLD_START_MIN_DAYS,
) -> STLBaselineEngine:
    """
    Fits STL baselines across all available stations.
    Automatically identifies cold-start stations and pairs them with the highest-correlated
    established donor station via Pearson correlation on detrended temperature overlap.
    """
    engine = STLBaselineEngine()
    established: List[str] = []
    cold_start: List[str] = []

    for sid, df in all_station_data.items():
        # Minimum threshold: 7 days * 24 points/day = 168 points minimum
        if len(df) >= int(min_history_days * 24):
            established.append(sid)
        else:
            cold_start.append(sid)

    # 1. Fit all established stations
    for sid in established:
        engine.fit_station(sid, all_station_data[sid])

    # 2. Assign donors to cold-start stations via correlation clustering
    for sid in cold_start:
        target_df = all_station_data[sid]
        target_temp = target_df.get("temperature_c", pd.Series(dtype=float)).interpolate().bfill().ffill()

        best_donor: Optional[str] = None
        best_corr: float = -2.0

        for donor_id in established:
            donor_df = all_station_data[donor_id]
            donor_temp = donor_df.get("temperature_c", pd.Series(dtype=float)).interpolate().bfill().ffill()
            m = min(len(target_temp), len(donor_temp))
            if m >= 12:
                s_t = float(np.std(target_temp[:m]))
                s_d = float(np.std(donor_temp[:m]))
                if s_t > 1e-4 and s_d > 1e-4:
                    corr = float(np.corrcoef(target_temp[:m], donor_temp[:m])[0, 1])
                    if not np.isnan(corr) and corr > best_corr:
                        best_corr = corr
                        best_donor = donor_id

        if best_donor is not None:
            engine.transfer_baseline(sid, best_donor, target_df)
        elif established:
            # Fallback to first established station
            engine.transfer_baseline(sid, established[0], target_df)
        else:
            # No established stations available; fit directly on available sample
            engine.fit_station(sid, target_df)

    return engine
