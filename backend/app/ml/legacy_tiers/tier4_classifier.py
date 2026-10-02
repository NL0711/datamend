"""
backend/app/ml/tier4_classifier.py
Tier 4: Fault Taxonomy Classifier (Distinguishing Meteorological Fronts from Sensor Hardware Faults).

Classifies AWS telemetry states into:
- NORMAL
- METEOROLOGICAL_EXTREME (Genuine convective squall front: is_fault=False)
- SPIKE
- DRIFT
- FROZEN
- DROPOUT
- NOISE_BURST
- MULTIVARIATE_INCONSISTENCY
- DATA_CORRUPTION
- UNCERTAIN_EVENT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd

from backend.app.ml.fusion import FusionResult, Severity
from backend.app.ml.tier1_qc import Tier1QCResult
from backend.app.ml.tier3_multivariate import Tier3Result, calculate_dew_point

logger = logging.getLogger(__name__)


class FaultClass(str, Enum):
    NORMAL = "NORMAL"
    SPIKE = "SPIKE"
    DRIFT = "DRIFT"
    FROZEN = "FROZEN"
    DROPOUT = "DROPOUT"
    NOISE_BURST = "NOISE_BURST"
    MULTIVARIATE_INCONSISTENCY = "MULTIVARIATE_INCONSISTENCY"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    METEOROLOGICAL_EXTREME = "METEOROLOGICAL_EXTREME"
    UNCERTAIN_EVENT = "UNCERTAIN_EVENT"


@dataclass
class ClassificationResult:
    fault_class: FaultClass
    is_fault: bool
    confidence: float
    reason: str
    rule_triggered: str
    classification: str = ""
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.classification:
            self.classification = self.fault_class.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fault_class": self.fault_class.value,
            "classification": self.classification,
            "is_fault": self.is_fault,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "rule_triggered": self.rule_triggered,
            "diagnostics": self.diagnostics,
        }


class FaultClassifier:
    """
    Tier 4 Fault Classifier with hybrid rule-based and meteorological physics logic.
    """

    def __init__(
        self,
        frozen_variance_threshold: float = 1e-6,
        frozen_window: int = 6,
        noise_burst_factor: float = 5.0,
        front_temp_drop_threshold: float = -3.0,
        front_pressure_jump_threshold: float = 1.5,
        front_humidity_surge_threshold: float = 15.0,
    ) -> None:
        self.frozen_var_thresh = frozen_variance_threshold
        self.frozen_window = frozen_window
        self.noise_burst_factor = noise_burst_factor
        self.front_temp_drop = front_temp_drop_threshold
        self.front_p_jump = front_pressure_jump_threshold
        self.front_rh_surge = front_humidity_surge_threshold

        self.nominal_stds = {"temperature": 0.35, "pressure": 0.15, "humidity": 1.2}
        self.ml_model: Optional[Any] = None

    def save(self, filepath: Union[str, Path]) -> None:
        """Persist classifier artifact."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "version": "1.0.0",
            "ml_model": self.ml_model,
            "nominal_stds": self.nominal_stds,
            "frozen_window": self.frozen_window,
        }
        joblib.dump(artifact, path)

    def load(self, filepath: Union[str, Path]) -> "FaultClassifier":
        """Load classifier artifact."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Classifier artifact not found at {path}")
        artifact = joblib.load(path)
        if isinstance(artifact, dict):
            self.ml_model = artifact.get("ml_model")
            self.nominal_stds = artifact.get("nominal_stds", self.nominal_stds)
            self.frozen_window = artifact.get("frozen_window", self.frozen_window)
        else:
            self.ml_model = artifact
        return self

    def _check_frozen(self, buffer_df: Optional[pd.DataFrame], column: str) -> bool:
        if buffer_df is None or len(buffer_df) < self.frozen_window or column not in buffer_df.columns:
            return False
        recent = buffer_df[column].tail(self.frozen_window).to_numpy(dtype=np.float64)
        if np.any(np.isnan(recent)):
            return False
        return float(np.var(recent)) < self.frozen_var_thresh

    def _check_noise_burst(self, buffer_df: Optional[pd.DataFrame], column: str) -> bool:
        if buffer_df is None or len(buffer_df) < 10 or column not in buffer_df.columns:
            return False
        recent = buffer_df[column].tail(10).to_numpy(dtype=np.float64)
        if np.any(np.isnan(recent)):
            return False
        nominal_std = self.nominal_stds.get(column, 1.0)
        recent_std = float(np.std(recent))
        return recent_std >= (self.noise_burst_factor * nominal_std)

    def _check_drift(self, buffer_df: Optional[pd.DataFrame], column: str) -> Tuple[bool, float]:
        if buffer_df is None or len(buffer_df) < 15 or column not in buffer_df.columns:
            return False, 0.0
        recent = buffer_df[column].tail(24).to_numpy(dtype=np.float64)
        if np.any(np.isnan(recent)):
            return False, 0.0
        x = np.arange(len(recent))
        try:
            slope, _ = np.polyfit(x, recent, 1)
            r_matrix = np.corrcoef(x, recent)
            r_val = r_matrix[0, 1] if r_matrix.shape == (2, 2) else 0.0
            is_drifting = abs(slope) >= 0.03 and abs(r_val) >= 0.80
            return bool(is_drifting), float(slope)
        except Exception:
            return False, 0.0

    def classify(
        self,
        current_observation: Optional[Dict[str, Any]] = None,
        buffer_df: Optional[pd.DataFrame] = None,
        tier1_result: Optional[Tier1QCResult] = None,
        tier3_result: Optional[Tier3Result] = None,
        fusion_result: Optional[FusionResult] = None,
        raw_features: Optional[Dict[str, float]] = None,
        fused_score: Optional[float] = None,
        is_anomaly: Optional[bool] = None,
    ) -> ClassificationResult:
        """
        Classify telemetry event into fault taxonomy.
        """
        # Merge observation inputs and raw feature dictionary
        obs: Dict[str, Any] = {}
        if current_observation:
            obs.update(current_observation)
        if raw_features:
            obs.update(raw_features)

        temp = obs.get("temperature")
        pres = obs.get("pressure")
        hum = obs.get("humidity")

        dt = float(obs.get("temp_delta", obs.get("delta_temp", 0.0)))
        dp = float(obs.get("press_delta", obs.get("delta_pressure", 0.0)))
        drh = float(obs.get("humid_delta", obs.get("delta_humidity", 0.0)))

        eff_fused = fused_score if fused_score is not None else (fusion_result.fused_score if fusion_result else 0.0)
        eff_anomaly = is_anomaly if is_anomaly is not None else (fusion_result.is_anomaly if fusion_result else (eff_fused >= 0.45))
        is_override = fusion_result.override_applied if fusion_result else (tier1_result.is_hard_override if tier1_result else False)

        # 1. Check for Dropouts (NaN / None / Sentinel values)
        if (
            (tier1_result and tier1_result.is_missing)
            or any(v is None or (isinstance(v, (int, float)) and (np.isnan(v) or v == -999.0 or v == 9999.0)) for v in (temp, pres, hum))
        ):
            return ClassificationResult(
                fault_class=FaultClass.DROPOUT,
                is_fault=True,
                confidence=0.99,
                reason="Sensor communication loss or missing telemetry packet (NaN/null/sentinel).",
                rule_triggered="RULE_DATA_DROPOUT",
                diagnostics={"raw_values": {"temperature": temp, "pressure": pres, "humidity": hum}},
            )

        # 2. Check for Data Corruption / Physical Range Violations
        if any(isinstance(v, str) for v in (temp, pres, hum)):
            return ClassificationResult(
                fault_class=FaultClass.DATA_CORRUPTION,
                is_fault=True,
                confidence=0.99,
                reason="Malformed non-numeric token encountered in observation payload.",
                rule_triggered="RULE_STRING_CORRUPTION",
            )

        t_val = float(temp) if temp is not None else 20.0
        p_val = float(pres) if pres is not None else 1013.25
        rh_val = float(hum) if hum is not None else 50.0

        if t_val < -40.0 or t_val > 60.0 or p_val < 300.0 or p_val > 1100.0 or rh_val < 0.0 or rh_val > 104.0:
            return ClassificationResult(
                fault_class=FaultClass.DATA_CORRUPTION,
                is_fault=True,
                confidence=0.98,
                reason=f"Observation outside physical limits: T={t_val:.1f}°C, P={p_val:.1f}hPa, RH={rh_val:.1f}%.",
                rule_triggered="RULE_PHYSICAL_RANGE_BOUNDS",
            )

        # 3. Check for Convective Weather Front (Meteorological Extreme)
        # Evaluated first to ensure genuine squalls are never misclassified as faults
        thermo_ok = True
        td_val = 0.0
        if tier3_result is not None:
            thermo_ok = not tier3_result.thermo_violation
            td_val = tier3_result.dew_point
        else:
            td_val = calculate_dew_point(t_val, rh_val)
            thermo_ok = (td_val <= t_val + 0.5)

        d_t_1 = dt
        d_p_1 = dp
        d_rh_1 = drh
        if buffer_df is not None and len(buffer_df) >= 2:
            t_prev = float(buffer_df["temperature"].iloc[-2])
            p_prev = float(buffer_df["pressure"].iloc[-2])
            rh_prev = float(buffer_df["humidity"].iloc[-2])
            d_t_1 = t_val - t_prev
            d_p_1 = p_val - p_prev
            d_rh_1 = rh_val - rh_prev

        if buffer_df is not None and len(buffer_df) >= 3:
            t_3 = float(buffer_df["temperature"].iloc[-3])
            p_3 = float(buffer_df["pressure"].iloc[-3])
            rh_3 = float(buffer_df["humidity"].iloc[-3])
            d_t_3 = t_val - t_3
            d_p_3 = p_val - p_3
            d_rh_3 = rh_val - rh_3
        else:
            d_t_3 = d_t_1
            d_p_3 = d_p_1
            d_rh_3 = d_rh_1

        is_front = (
            thermo_ok
            and (d_t_1 <= self.front_temp_drop or d_t_3 <= self.front_temp_drop)
            and (abs(d_p_1) >= self.front_p_jump or abs(d_p_3) >= self.front_p_jump)
            and (d_rh_1 >= self.front_rh_surge or d_rh_3 >= self.front_rh_surge)
        )

        if is_front:
            d_t_front = min(d_t_1, d_t_3)
            d_p_front = d_p_1 if abs(d_p_1) >= abs(d_p_3) else d_p_3
            d_rh_front = max(d_rh_1, d_rh_3)
            return ClassificationResult(
                fault_class=FaultClass.METEOROLOGICAL_EXTREME,
                is_fault=False,  # Genuine atmospheric event
                confidence=0.92,
                reason=(
                    f"Genuine convective squall front detected: ΔT={d_t_front:+.1f}°C, "
                    f"ΔP={d_p_front:+.1f}hPa, ΔRH=+{d_rh_front:+.1f}% adhering to Clausius-Clapeyron thermodynamics."
                ),
                rule_triggered="RULE_METEOROLOGICAL_SQUALL_FRONT",
                diagnostics={
                    "delta_T": d_t_front,
                    "delta_P": d_p_front,
                    "delta_RH": d_rh_front,
                    "dew_point_c": td_val,
                },
            )

        # 4. Check for Normal Telemetry if no anomaly detected
        if not eff_anomaly and not is_override:
            return ClassificationResult(
                fault_class=FaultClass.NORMAL,
                is_fault=False,
                confidence=float(np.clip(1.0 - eff_fused, 0.50, 1.00)),
                reason="Telemetry within normal operational and meteorological baselines.",
                rule_triggered="RULE_NORMAL_OPERATION",
                diagnostics={"fused_score": eff_fused},
            )

        # 5. Check for Thermodynamic Multivariate Inconsistency
        if not thermo_ok or (tier3_result and tier3_result.thermo_violation):
            diff = (tier3_result.dew_point_diff if tier3_result else (td_val - t_val))
            return ClassificationResult(
                fault_class=FaultClass.MULTIVARIATE_INCONSISTENCY,
                is_fault=True,
                confidence=0.94,
                reason=(
                    f"Thermodynamic violation: calculated dew point ({td_val:.1f}°C) "
                    f"exceeds dry bulb temperature ({t_val:.1f}°C) by {diff:.1f}°C."
                ),
                rule_triggered="RULE_THERMODYNAMIC_DECOUPLING",
                diagnostics={"dew_point_diff": diff},
            )

        # 6. Check for Spike Impulses (Single variable transient step)
        if abs(dt) > 5.0 or abs(dp) > 3.0 or abs(drh) > 25.0 or (tier1_result and tier1_result.flags.get("rate_of_change_exceeded")):
            affected = []
            if abs(dt) > 5.0:
                affected.append(f"T (Δ={dt:+.1f}°C)")
            if abs(dp) > 3.0:
                affected.append(f"P (Δ={dp:+.1f}hPa)")
            if abs(drh) > 25.0:
                affected.append(f"RH (Δ={drh:+.1f}%)")
            if not affected:
                affected.append("Rate of change exceeded")
            return ClassificationResult(
                fault_class=FaultClass.SPIKE,
                is_fault=True,
                confidence=0.91,
                reason=f"Transient impulse step-change detected in {', '.join(affected)} within 5 minutes.",
                rule_triggered="RULE_TRANSIENT_SPIKE",
                diagnostics={"deltas": {"dT": dt, "dP": dp, "dRH": drh}},
            )

        # 7. Check for Progressive Linear Calibration Drift
        if buffer_df is not None:
            for col in ["temperature", "pressure", "humidity"]:
                is_drift, slope = self._check_drift(buffer_df, col)
                if is_drift:
                    return ClassificationResult(
                        fault_class=FaultClass.DRIFT,
                        is_fault=True,
                        confidence=0.86,
                        reason=f"Progressive calibration drift detected on '{col}' (slope={slope:+.3f} units/step).",
                        rule_triggered=f"RULE_PROGRESSIVE_DRIFT_{col.upper()}",
                        diagnostics={"slope": slope},
                    )

        # 8. Check for Noise Bursts
        if buffer_df is not None:
            for col in ["temperature", "pressure", "humidity"]:
                if self._check_noise_burst(buffer_df, col):
                    return ClassificationResult(
                        fault_class=FaultClass.NOISE_BURST,
                        is_fault=True,
                        confidence=0.88,
                        reason=f"High-frequency noise burst surge detected on parameter '{col}'.",
                        rule_triggered=f"RULE_NOISE_BURST_{col.upper()}",
                    )

        # 9. Check for Frozen Sensors (Zero Variance over K steps)
        if (tier1_result and tier1_result.is_frozen) or (obs.get("is_frozen", False)):
            return ClassificationResult(
                fault_class=FaultClass.FROZEN,
                is_fault=True,
                confidence=0.95,
                reason=f"Sensor repeating identical value with zero empirical variance over >= {self.frozen_window} steps.",
                rule_triggered="RULE_FROZEN_SENSOR",
            )

        if buffer_df is not None:
            for col in ["temperature", "pressure", "humidity"]:
                if self._check_frozen(buffer_df, col):
                    return ClassificationResult(
                        fault_class=FaultClass.FROZEN,
                        is_fault=True,
                        confidence=0.95,
                        reason=f"Sensor '{col}' repeating identical value with zero empirical variance over >= {self.frozen_window} steps.",
                        rule_triggered=f"RULE_FROZEN_{col.upper()}",
                        diagnostics={"stuck_parameter": col},
                    )

        # 10. Check for Statistical Mahalanobis Decoupling
        if tier3_result and tier3_result.mahalanobis_score >= 0.90:
            return ClassificationResult(
                fault_class=FaultClass.MULTIVARIATE_INCONSISTENCY,
                is_fault=True,
                confidence=0.85,
                reason=(
                    f"Multivariate covariance anomaly detected (Mahalanobis D_M={tier3_result.mahalanobis_distance:.2f}, "
                    f"p={tier3_result.mahalanobis_score:.4f})."
                ),
                rule_triggered="RULE_MAHALANOBIS_COVARIANCE_ANOMALY",
            )

        # 11. Fallback for Uncategorized Anomalies
        return ClassificationResult(
            fault_class=FaultClass.UNCERTAIN_EVENT,
            is_fault=True,
            confidence=0.55,
            reason="Ambiguous anomaly detected; signature does not match distinct fault patterns.",
            rule_triggered="RULE_FALLBACK_UNCERTAIN",
            diagnostics={"fused_score": eff_fused},
        )


# Backward-compatible alias
Tier4FaultClassifier = FaultClassifier
