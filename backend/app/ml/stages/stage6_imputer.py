"""
backend/app/ml/stage6_imputer.py
SkyGuard AI / DataMend — Stage 6: Meteorological Safe Imputation & Self-Healing Engine.

Synthesizes:
1. Ashwina-Pal/skyguard/tier2/stage5_explain.py: Dual-strategy imputation mapping:
   - STL Seasonal-Trend Reconstruction (trend + diurnal phase) for spikes, drift, and frozen sensors.
   - Spatial Inverse Distance Weighting (IDW) interpolation from clean neighboring stations for dropouts and corruptions.
2. Safety Gating: Returns None for GENUINE_WEATHER_EVENT and NORMAL observations, strictly protecting genuine atmospheric dynamics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from backend.app.ml.stages.stage1_stl import StationBaseline, CHANNELS
from backend.app.spatial.consensus import haversine_distance_km

logger = logging.getLogger(__name__)


@dataclass
class ImputationResult:
    """Outcome of safe meteorological imputation."""
    parameter: str
    original_value: Optional[float]
    corrected_value: Optional[float]
    method: str  # "STL_RECONSTRUCTION", "SPATIAL_IDW", "PASSTHROUGH", "NONE"
    confidence: float
    is_imputed: bool
    justification: str


class MeteorologicalSafeImputer:
    """
    Surgically restores missing or corrupted meteorological observations
    using diurnal STL baselines and spatial neighbor IDW interpolation.
    """

    def impute_reading(
        self,
        station_id: str,
        timestamp: datetime,
        parameter: str,
        original_value: Optional[float],
        predicted_class: str,
        baseline: Optional[StationBaseline],
        neighbor_observations: Optional[List[Dict[str, Any]]] = None,
        target_lat: Optional[float] = None,
        target_lon: Optional[float] = None,
    ) -> ImputationResult:
        """
        Computes physically consistent replacement values for flagged sensor faults.
        """
        # 1. Safety Gating: Genuine weather events and normal readings are NEVER altered
        if predicted_class in ("NORMAL", "GENUINE_WEATHER_EVENT"):
            return ImputationResult(
                parameter=parameter,
                original_value=original_value,
                corrected_value=None,
                method="PASSTHROUGH",
                confidence=1.0,
                is_imputed=False,
                justification="Reading is physically valid or confirmed genuine weather event. Imputation bypassed.",
            )

        # Map channel parameter names
        norm_param = parameter
        if parameter in ("temperature", "temperature_c"):
            norm_param = "temperature_c"
            raw_key = "temperature"
        elif parameter in ("pressure", "pressure_hpa"):
            norm_param = "pressure_hpa"
            raw_key = "pressure"
        elif parameter in ("humidity", "humidity_pct"):
            norm_param = "humidity_pct"
            raw_key = "humidity"
        else:
            raw_key = parameter

        # Compute STL diurnal baseline reconstruction value
        stl_val: Optional[float] = None
        if baseline is not None and norm_param in baseline.means:
            period = baseline.period
            # Modular time-of-day index: 96 steps = 15-min intervals, 24 steps = hourly
            if period == 96:
                tod_idx = (timestamp.hour * 4 + timestamp.minute // 15) % period
            else:
                tod_idx = timestamp.hour % period

            mean_val = baseline.means[norm_param]
            seasonal_profile = baseline.seasonal_profiles[norm_param]
            seas_val = float(seasonal_profile[tod_idx])
            stl_val = round(mean_val + seas_val, 2)

        # ---------------------------------------------------------------------
        # Strategy A: STL Reconstruction for Spikes, Calibration Drift, Frozen
        # ---------------------------------------------------------------------
        if predicted_class in ("SPIKE", "CALIBRATION_DRIFT", "FROZEN_SENSOR"):
            if stl_val is not None:
                return ImputationResult(
                    parameter=norm_param,
                    original_value=original_value,
                    corrected_value=stl_val,
                    method="STL_RECONSTRUCTION",
                    confidence=0.88,
                    is_imputed=True,
                    justification=f"Reconstructed using station diurnal STL baseline (diurnal phase step {tod_idx}).",
                )

        # ---------------------------------------------------------------------
        # Strategy B: Spatial IDW Interpolation for Dropouts, Corruption, Power Sag
        # ---------------------------------------------------------------------
        if neighbor_observations and target_lat is not None and target_lon is not None:
            valid_vals: List[float] = []
            weights: List[float] = []

            for n in neighbor_observations:
                nid = n.get("station_id")
                nlat = n.get("latitude")
                nlon = n.get("longitude")
                # Look up reading by raw_key or norm_param
                nval = n.get(raw_key) if n.get(raw_key) is not None else n.get(norm_param)

                # Ignore target station, missing coords, or null values
                if nid == station_id or nlat is None or nlon is None or nval is None or np.isnan(nval):
                    continue

                # Filter out neighbors flagged with faults if ground_truth or tier0 flag present
                if n.get("tier0_flag", "PASS") != "PASS" or n.get("is_fault", False):
                    continue

                dist_km = haversine_distance_km(target_lat, target_lon, nlat, nlon)
                if dist_km <= 60.0:
                    w = 1.0 / max(0.5, dist_km)
                    valid_vals.append(float(nval))
                    weights.append(w)

            if valid_vals and sum(weights) > 0:
                total_w = sum(weights)
                norm_w = [w / total_w for w in weights]
                idw_val = round(float(sum(v * w for v, w in zip(valid_vals, norm_w))), 2)
                return ImputationResult(
                    parameter=norm_param,
                    original_value=original_value,
                    corrected_value=idw_val,
                    method="SPATIAL_IDW",
                    confidence=0.92,
                    is_imputed=True,
                    justification=f"Interpolated via Inverse Distance Weighting across {len(valid_vals)} active regional neighbors.",
                )

        # Fallback to STL reconstruction if spatial neighbors unavailable
        if stl_val is not None:
            return ImputationResult(
                parameter=norm_param,
                original_value=original_value,
                corrected_value=stl_val,
                method="STL_RECONSTRUCTION",
                confidence=0.75,
                is_imputed=True,
                justification="Fallback to diurnal STL baseline reconstruction (insufficient clean spatial neighbors).",
            )

        # Fallback: cannot safely impute
        return ImputationResult(
            parameter=norm_param,
            original_value=original_value,
            corrected_value=None,
            method="NONE",
            confidence=0.0,
            is_imputed=False,
            justification="Imputation failed: No STL baseline or valid spatial neighbors available.",
        )


# Global singleton instance
meteorological_safe_imputer = MeteorologicalSafeImputer()
