"""
backend/app/ml/stage5_explain.py
DataMend — Stage 5: Explainable AI (XAI) & TreeSHAP Attribution Engine.

Synthesizes:
1. akshitbuilds/agent4/explainability.py: Narrative generation, FEATURE_PHRASES, and degradation context.
2. prakhar28singh-creator/shap_explainer.py: Multi-tier additive contributions, directionality, and waterfall export.
3. datamend/ml/tier5_explain.py: Exact TreeSHAP with high-performance standardized z-score fallback (<2 ms).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Check for shap library availability
_HAS_SHAP = False
try:
    import shap
    _HAS_SHAP = True
except ImportError:
    pass

FEATURE_PHRASES: Dict[str, str] = {
    "temperature_c": "Ambient Air Temperature (°C)",
    "pressure_hpa": "Barometric Atmospheric Pressure (hPa)",
    "humidity_pct": "Relative Humidity (%)",
    "temperature_c_resid": "De-seasonalized Temperature Residual Deviation",
    "pressure_hpa_resid": "Barometric Pressure Residual Deviation",
    "humidity_pct_resid": "Relative Humidity Residual Deviation",
    "magnus_dew_point": "Thermodynamic Clausius-Clapeyron Dew Point Margin",
    "spatial_divergence": "Haversine Spatial Neighbor Variance Deviation",
}

CHANNELS = ["temperature_c", "pressure_hpa", "humidity_pct"]
RESIDUAL_CHANNELS = ["temperature_c_resid", "pressure_hpa_resid", "humidity_pct_resid"]


@dataclass
class FeatureContribution:
    """Additive feature contribution for diagnostic attribution and waterfall plots."""
    feature: str
    attribution: float  # Normalized percentage in [0.0, 1.0]
    raw_value: Optional[float]
    residual_value: Optional[float]
    direction: str      # "increases" or "decreases"
    meaning: str


@dataclass
class ExplanationReport:
    """Comprehensive XAI explanation report."""
    summary: str
    top_drivers: List[str]
    contributions: List[FeatureContribution]
    method: str
    latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """Exports waterfall-compatible dictionary structure."""
        return {
            "summary": self.summary,
            "method": self.method,
            "latency_ms": self.latency_ms,
            "top_drivers": self.top_drivers,
            "contributions": [
                {
                    "feature": c.feature,
                    "attribution": round(c.attribution, 4),
                    "raw_value": c.raw_value,
                    "residual_value": c.residual_value,
                    "direction": c.direction,
                    "meaning": c.meaning,
                }
                for c in self.contributions
            ],
        }


class Stage5ExplainEngine:
    """
    Stage 5 Explainable AI (XAI) Engine.
    Emits feature attributions summing to 1.0 and plain-language diagnostic narratives.
    """

    def __init__(self) -> None:
        self.surrogate_model: Optional[Any] = None
        self._explainer: Optional[Any] = None

    def fit_surrogate(self, residuals: np.ndarray, labels: np.ndarray) -> None:
        """
        Fits a lightweight surrogate Random Forest classifier on residuals
        to initialize the TreeSHAP explainer.
        """
        if not _HAS_SHAP or len(residuals) < 20:
            return

        try:
            from sklearn.ensemble import RandomForestClassifier

            rf = RandomForestClassifier(n_estimators=30, max_depth=4, random_state=42)
            if len(np.unique(labels)) > 1:
                rf.fit(residuals, labels)
                self.surrogate_model = rf
                self._explainer = shap.TreeExplainer(rf)
                logger.info("Initialized TreeSHAP explainer with surrogate Random Forest.")
        except Exception as exc:
            logger.debug("Surrogate TreeSHAP initialization fallback: %s", exc)
            self.surrogate_model = None
            self._explainer = None

    def explain(
        self,
        station_id: str,
        predicted_class: str,
        anomaly_score: float,
        confidence: float,
        raw_telemetry: Dict[str, Optional[float]],
        residuals: Dict[str, float],
        tier0_flags: Optional[Dict[str, Any]] = None,
        degradation_info: Optional[Dict[str, Any]] = None,
    ) -> ExplanationReport:
        """
        Generates parameter-level attributions and a forensic narrative in <= 5 ms.
        """
        t0 = time.perf_counter()

        t_val = raw_telemetry.get("temperature_c") or raw_telemetry.get("temperature")
        p_val = raw_telemetry.get("pressure_hpa") or raw_telemetry.get("pressure")
        h_val = raw_telemetry.get("humidity_pct") or raw_telemetry.get("humidity")

        t_res = residuals.get("temperature_c_resid", 0.0)
        p_res = residuals.get("pressure_hpa_resid", 0.0)
        h_res = residuals.get("humidity_pct_resid", 0.0)

        res_vector = np.array([t_res, p_res, h_res], dtype=float)
        raw_vals = [t_val, p_val, h_val]

        used_shap = False
        raw_contribs = np.zeros(3)

        # 1. TreeSHAP Attribution via surrogate if fitted
        if _HAS_SHAP and self._explainer is not None:
            try:
                x_2d = res_vector.reshape(1, -1)
                shap_vals = self._explainer.shap_values(x_2d)
                if isinstance(shap_vals, list):
                    c = np.abs(shap_vals[1][0]) if len(shap_vals) > 1 else np.abs(shap_vals[0][0])
                elif isinstance(shap_vals, np.ndarray):
                    c = np.abs(shap_vals[0, :, 1]) if shap_vals.ndim == 3 else np.abs(shap_vals[0])
                else:
                    c = np.zeros(3)
                raw_contribs = np.asarray(c, dtype=float)
                used_shap = True
            except Exception as exc:
                logger.debug("TreeSHAP pass fallback: %s", exc)
                used_shap = False

        # 2. Ultra-fast normalized residual Z-score fallback (always guaranteed <= 1 ms)
        if not used_shap or np.sum(raw_contribs) < 1e-6:
            # Scaled deviations: standard AWS standard deviations (~3°C, ~3 hPa, ~15% RH)
            z_t = abs(t_res) / 3.0
            z_p = abs(p_res) / 3.0
            z_h = abs(h_res) / 15.0
            raw_contribs = np.array([z_t, z_p, z_h], dtype=float)

        # Normalize attributions to sum strictly to 1.0 (100%)
        total = float(np.sum(raw_contribs))
        if total > 1e-6:
            norm_attributions = raw_contribs / total
        else:
            norm_attributions = np.array([0.3334, 0.3333, 0.3333], dtype=float)

        contributions: List[FeatureContribution] = []
        for i, col in enumerate(CHANNELS):
            attr = float(norm_attributions[i])
            res = float(res_vector[i])
            direction = "increases" if abs(res) > 1.0 else "decreases"
            contributions.append(
                FeatureContribution(
                    feature=col,
                    attribution=round(attr, 4),
                    raw_value=round(raw_vals[i], 2) if raw_vals[i] is not None else None,
                    residual_value=round(res, 3),
                    direction=direction,
                    meaning=FEATURE_PHRASES.get(col, col),
                )
            )

        # Sort descending by attribution
        contributions.sort(key=lambda c: c.attribution, reverse=True)
        top_drivers = [c.feature for c in contributions if c.attribution >= 0.25]
        if not top_drivers:
            top_drivers = [contributions[0].feature]

        # 3. Forensic narrative generation (akshitbuilds narrative pattern)
        primary = contributions[0]
        summary = self._build_narrative(
            station_id=station_id,
            predicted_class=predicted_class,
            anomaly_score=anomaly_score,
            confidence=confidence,
            primary_contribution=primary,
            tier0_flags=tier0_flags or {},
            degradation_info=degradation_info,
        )

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return ExplanationReport(
            summary=summary,
            top_drivers=top_drivers,
            contributions=contributions,
            method="TreeSHAP" if used_shap else "ResidualZScore",
            latency_ms=latency_ms,
        )

    def _build_narrative(
        self,
        station_id: str,
        predicted_class: str,
        anomaly_score: float,
        confidence: float,
        primary_contribution: FeatureContribution,
        tier0_flags: Dict[str, Any],
        degradation_info: Optional[Dict[str, Any]],
    ) -> str:
        """Synthesizes human-readable operational forensic summary."""
        feat_name = {
            "temperature_c": "Temperature",
            "pressure_hpa": "Barometric Pressure",
            "humidity_pct": "Relative Humidity",
        }.get(primary_contribution.feature, primary_contribution.feature)

        unit = "°C" if primary_contribution.feature == "temperature_c" else (
            " hPa" if primary_contribution.feature == "pressure_hpa" else "%"
        )
        res_str = f"{primary_contribution.residual_value:+.2f}{unit}" if primary_contribution.residual_value is not None else "0.0"

        # Forensic phrasing by fault class
        if predicted_class == "SPIKE":
            narrative = (
                f"Station {station_id} flagged for isolated transient impulse spike on {feat_name} "
                f"({primary_contribution.attribution:.1%} driver, deviation {res_str}) "
                f"with {confidence * 100:.0f}% confidence. Rate of change exceeds atmospheric maximum."
            )
        elif predicted_class == "FROZEN_SENSOR":
            narrative = (
                f"Station {station_id} exhibits stuck/flatlined sensor on {feat_name} "
                f"with zero rolling empirical variance across consecutive intervals."
            )
        elif predicted_class == "COMMUNICATION_DROPOUT":
            narrative = (
                f"Station {station_id} telemetry loss detected: Null or missing telemetry packets "
                f"prevented continuous time-series reception."
            )
        elif predicted_class == "CALIBRATION_DRIFT":
            narrative = (
                f"Station {station_id} exhibits progressive monotonic calibration drift on {feat_name} "
                f"({primary_contribution.attribution:.1%} driver, accumulated offset {res_str}) "
                f"diverging steadily from diurnal baseline."
            )
        elif predicted_class == "POWER_FLUCTUATION":
            narrative = (
                f"Station {station_id} telemetry indicates synchronized multi-channel step transients, "
                f"consistent with edge power sag or solar battery voltage collapse."
            )
        elif predicted_class == "DATA_CORRUPTION":
            narrative = (
                f"Station {station_id} violated thermodynamic atmospheric invariants "
                f"(Clausius-Clapeyron Magnus dew point or WMO physical range limit)."
            )
        elif predicted_class == "GENUINE_WEATHER_EVENT":
            narrative = (
                f"Station {station_id} observed significant deviation in {feat_name} ({res_str}), "
                f"fully corroborated by regional spatial neighbor consensus (Genuine-Weather-Event Safety Shield active)."
            )
        else:
            narrative = (
                f"Station {station_id} routine observation: All atmospheric parameters nominal "
                f"and consistent with historical diurnal baseline."
            )

        # Incorporate historical sensor degradation context if available (from akshitbuilds pattern)
        if degradation_info:
            deg_status = degradation_info.get("status")
            if deg_status in ("DEGRADING", "CRITICAL"):
                narrative += (
                    f" Warning: Sensor is in {deg_status} state "
                    f"(recent anomaly rate {degradation_info.get('recent_anomaly_rate', 0.0) * 100:.0f}% vs "
                    f"{degradation_info.get('baseline_anomaly_rate', 0.0) * 100:.0f}% baseline) — "
                    f"{degradation_info.get('reasoning', 'elevated failure risk')}."
                )
            elif deg_status == "WATCH":
                narrative += f" Note: Sensor on watch list ({degradation_info.get('reasoning', 'minor elevated variance')})."

        return narrative


# Global singleton instance
stage5_explain_engine = Stage5ExplainEngine()
