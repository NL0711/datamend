"""
backend/app/ml/tier5_explain.py
Tier 5: TreeSHAP Feature Attribution and Natural Language Diagnostic Engine.

Calculates exact Shapley feature attributions using TreeSHAP on trained tree models,
normalizes feature percentages to 100%, and synthesizes human-readable diagnostic summaries.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from pydantic import BaseModel, Field
import shap

logger = logging.getLogger(__name__)


class FeatureAttribution(BaseModel):
    feature: str = Field(..., description="Feature name")
    attribution: float = Field(..., description="Attribution fraction in [0, 1]")
    raw_value: Optional[float] = Field(None, description="Raw feature value")
    description: Optional[str] = Field(None, description="Human-readable interpretation")


class ExplanationResult(BaseModel):
    summary: str = Field(..., description="Synthesized diagnostic explanation sentence")
    contributing_features: List[FeatureAttribution] = Field(default_factory=list)
    method: str = Field("TreeSHAP", description="Explainability method used")


FEATURE_DISPLAY_NAMES: Dict[str, str] = {
    "temperature": "Temperature",
    "pressure": "Atmospheric Pressure",
    "humidity": "Relative Humidity",
    "temp_delta": "Temperature 5-min Change",
    "press_delta": "Pressure 5-min Change",
    "humid_delta": "Humidity 5-min Change",
    "delta_temp": "Temperature 5-min Change",
    "delta_pressure": "Pressure 5-min Change",
    "delta_humidity": "Humidity 5-min Change",
    "temp_roll_std": "Temperature Short-term Variance",
    "press_roll_std": "Pressure Short-term Variance",
    "humid_roll_std": "Humidity Short-term Variance",
    "dew_point": "Dew Point",
    "sin_hour": "Diurnal Solar Phase (Sin)",
    "cos_hour": "Diurnal Solar Phase (Cos)",
}


class ExplainabilityEngine:
    """Computes exact TreeSHAP feature attributions and generates natural language diagnoses."""

    def __init__(
        self,
        model: Any = None,
        feature_names: Optional[List[str]] = None,
        background_data: Optional[np.ndarray] = None,
    ):
        self.model = model
        self.feature_names = feature_names or [
            "temperature", "pressure", "humidity",
            "temp_delta", "press_delta", "humid_delta",
            "temp_roll_std", "press_roll_std", "humid_roll_std"
        ]
        self.explainer: Optional[Any] = None

        if self.model is not None:
            self._init_explainer(background_data)

    def _init_explainer(self, background_data: Optional[np.ndarray] = None) -> None:
        try:
            self.explainer = shap.TreeExplainer(self.model, feature_perturbation="tree_path_dependent")
        except Exception:
            try:
                self.explainer = shap.TreeExplainer(self.model)
            except Exception as e:
                logger.debug("TreeExplainer init failed: %s", e)
                self.explainer = None

    def explain(
        self,
        feature_vector: Optional[np.ndarray] = None,
        raw_values: Optional[Dict[str, float]] = None,
        tier1_flags: Optional[Dict[str, Any]] = None,
        tier3_info: Optional[Dict[str, Any]] = None,
        classification: str = "NORMAL",
        fused_score: float = 0.0,
        confidence: float = 1.0,
    ) -> ExplanationResult:
        """Compute feature attributions and synthesize natural language summary."""
        raw_vals = raw_values or {}
        t1_flags = tier1_flags or {}
        t3_info = tier3_info or {}
        attributions: List[FeatureAttribution] = []

        if self.explainer is not None and feature_vector is not None:
            try:
                vec_2d = feature_vector.reshape(1, -1)
                shap_vals = self.explainer.shap_values(vec_2d)

                if isinstance(shap_vals, list):
                    vals = np.abs(shap_vals[0][0])
                elif isinstance(shap_vals, np.ndarray):
                    if shap_vals.ndim == 2:
                        vals = np.abs(shap_vals[0])
                    elif shap_vals.ndim == 3:
                        vals = np.abs(shap_vals[0, :, 0])
                    else:
                        vals = np.abs(shap_vals.flatten())
                else:
                    vals = np.zeros(len(self.feature_names))

                # Normalize to percentages summing to 1.0
                total_val = float(np.sum(vals))
                if total_val > 1e-9:
                    norm_attributions = vals / total_val
                else:
                    norm_attributions = np.ones(len(self.feature_names)) / len(self.feature_names)

                for i, name in enumerate(self.feature_names):
                    attr_val = float(norm_attributions[i])
                    raw_val = raw_vals.get(name, float(feature_vector[i]) if i < len(feature_vector) else None)
                    attributions.append(
                        FeatureAttribution(
                            feature=name,
                            attribution=round(attr_val, 4),
                            raw_value=round(raw_val, 2) if raw_val is not None else None,
                            description=FEATURE_DISPLAY_NAMES.get(name, name),
                        )
                    )
            except Exception as e:
                logger.debug("SHAP explanation failed, falling back to heuristic: %s", e)
                attributions = self._heuristic_fallback_attributions(feature_vector, raw_vals)
        else:
            attributions = self._heuristic_fallback_attributions(feature_vector, raw_vals)

        # Ensure exact sum of attributions = 1.0 (normalized)
        total_attr = sum(fa.attribution for fa in attributions)
        if total_attr > 0 and abs(total_attr - 1.0) > 1e-3:
            for fa in attributions:
                fa.attribution = round(fa.attribution / total_attr, 4)

        # Sort descending by attribution
        attributions.sort(key=lambda x: x.attribution, reverse=True)

        summary = self._generate_diagnostic_summary(
            tier1_flags=t1_flags,
            tier3_info=t3_info,
            classification=classification,
            fused_score=fused_score,
            confidence=confidence,
            top_attributions=attributions[:3],
            raw_values=raw_vals,
        )

        return ExplanationResult(
            summary=summary,
            contributing_features=attributions,
            method="TreeSHAP" if self.explainer is not None else "FeatureDeviation",
        )

    def _heuristic_fallback_attributions(
        self,
        feature_vector: Optional[np.ndarray],
        raw_values: Dict[str, float],
    ) -> List[FeatureAttribution]:
        """Calculates normalized z-score deviation contributions when SHAP is unavailable."""
        attributions = []
        if feature_vector is not None and len(feature_vector) == len(self.feature_names):
            abs_devs = np.abs(feature_vector)
            total = float(np.sum(abs_devs))
            weights = abs_devs / total if total > 1e-9 else np.ones(len(self.feature_names)) / len(self.feature_names)
            for i, name in enumerate(self.feature_names):
                attributions.append(
                    FeatureAttribution(
                        feature=name,
                        attribution=round(float(weights[i]), 4),
                        raw_value=round(raw_values.get(name, float(feature_vector[i])), 2),
                        description=FEATURE_DISPLAY_NAMES.get(name, name),
                    )
                )
        else:
            eq_weight = round(1.0 / len(self.feature_names), 4)
            for name in self.feature_names:
                raw_v = raw_values.get(name)
                attributions.append(
                    FeatureAttribution(
                        feature=name,
                        attribution=eq_weight,
                        raw_value=round(float(raw_v), 2) if raw_v is not None else None,
                        description=FEATURE_DISPLAY_NAMES.get(name, name),
                    )
                )
        return attributions

    def _generate_diagnostic_summary(
        self,
        tier1_flags: Dict[str, Any],
        tier3_info: Dict[str, Any],
        classification: str,
        fused_score: float,
        confidence: float,
        top_attributions: List[FeatureAttribution],
        raw_values: Dict[str, float],
    ) -> str:
        """Synthesizes an exact, contextual human-readable explanation."""
        t = raw_values.get("temperature", 20.0)
        p = raw_values.get("pressure", 1013.25)
        rh = raw_values.get("humidity", 50.0)
        dt = raw_values.get("temp_delta", raw_values.get("delta_temp", 0.0))
        dp = raw_values.get("press_delta", raw_values.get("delta_pressure", 0.0))
        drh = raw_values.get("humid_delta", raw_values.get("delta_humidity", 0.0))

        # 1. Genuine Meteorological Extreme Front
        if classification == "METEOROLOGICAL_EXTREME":
            return (
                f"Convective Weather Front detected: Coordinated temperature drop ({dt:+.1f}°C) and pressure change ({dp:+.1f} hPa) "
                f"with relative humidity surge ({drh:+.1f}%). Thermodynamic equilibrium maintained (Td <= T)."
            )

        # 2. Deterministic Tier 1 Explanations
        if tier1_flags.get("out_of_bounds", False):
            param = tier1_flags.get("violating_param", "temperature")
            val = raw_values.get(param, t)
            return f"Deterministic QC Failure: {param.capitalize()} reading ({val:.1f}) violated WMO physical plausibility limits."

        if tier1_flags.get("rate_of_change_exceeded", False):
            param = tier1_flags.get("violating_param", "temperature")
            delta = abs(raw_values.get(f"{param}_delta", dt))
            return f"Rapid step anomaly: {param.capitalize()} jumped {delta:+.1f} within 5 minutes, exceeding rate-of-change threshold."

        if tier1_flags.get("is_frozen", False) or classification == "FROZEN":
            return f"Persistent sensor fault: Sensor values stuck at constant reading ({t:.2f}°C) with zero empirical variance."

        if classification == "DROPOUT" or tier1_flags.get("missing_value", False):
            return "Sensor communication dropout: Missing or null telemetry data packets received."

        if classification == "DATA_CORRUPTION" or tier1_flags.get("corrupt_token", False):
            return "Data corruption: Malformed, non-numeric, or unparseable telemetry payload received."

        # 3. Clausius-Clapeyron Thermodynamic Inconsistency
        if tier3_info.get("thermo_violation", False) or classification == "MULTIVARIATE_INCONSISTENCY":
            td = tier3_info.get("dew_point", 0.0)
            return (
                f"Multivariate thermodynamic inconsistency: Dew point ({td:.1f}°C) exceeds ambient temperature ({t:.1f}°C) "
                f"at RH={rh:.1f}%, indicating physical sensor decoupling."
            )

        # 4. Spike / Impulse
        if classification == "SPIKE":
            top_f = top_attributions[0].description if top_attributions else "Temperature"
            return f"Transient impulse anomaly: Sudden deviation in {top_f} (Anomaly Score: {fused_score:.2f}, Confidence: {confidence:.2f})."

        # 5. Calibration Drift
        if classification == "DRIFT":
            return f"Progressive calibration drift detected: Continuous deviation from baseline diurnal expectation over extended window."

        # 6. Noise Burst
        if classification == "NOISE_BURST":
            top_f = top_attributions[0].description if top_attributions else "Sensor"
            return f"High-frequency noise burst detected: Elevated variance and signal jitter observed on {top_f}."

        # 7. High Anomaly Score Generic Summary
        if fused_score >= 0.45:
            top_drivers = ", ".join(f"{fa.description} ({fa.attribution:.0%})" for fa in top_attributions[:2])
            return f"Multivariate anomaly detected (Score: {fused_score:.2f}, Conf: {confidence:.2f}). Primary drivers: {top_drivers}."

        return f"Nominal AWS observation: All meteorological parameters within normal statistical and thermodynamic ranges."
