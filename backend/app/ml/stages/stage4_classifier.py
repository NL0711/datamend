"""
backend/app/ml/stage4_classifier.py
SkyGuard AI / DataMend — Stage 4: Calibrated Evidence Fusion & 8-Class Fault Classifier.

Fuses multi-tier diagnostic evidence into an auditable 8-class meteorological fault taxonomy:
1. SPIKE: High rate-of-change transient or impulse surge confirmed isolated by spatial check.
2. FROZEN_SENSOR: Zero variance / stuck ADC reading while ambient conditions evolve.
3. COMMUNICATION_DROPOUT: High null ratio or packet arrival gap.
4. CALIBRATION_DRIFT: Monotonic residual drift accumulation without sudden step change.
5. POWER_FLUCTUATION: Simultaneous multi-sensor transient step or sudden variance collapse.
6. DATA_CORRUPTION: Impossible physical state (dew point > air temp) or extreme WMO boundary violation.
7. GENUINE_WEATHER_EVENT: Extreme deviation protected by neighbor spatial consensus (Genuine Safety Shield).
8. NORMAL: Routine observation adhering to diurnal baseline and physical constraints.

Computes distinct:
- anomaly_score: [0.0, 1.0] representing fault severity/magnitude.
- confidence: [0.0, 1.0] representing inter-tier evidence agreement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

FAULT_CLASSES: List[str] = [
    "SPIKE",
    "FROZEN_SENSOR",
    "COMMUNICATION_DROPOUT",
    "CALIBRATION_DRIFT",
    "POWER_FLUCTUATION",
    "DATA_CORRUPTION",
    "GENUINE_WEATHER_EVENT",
    "NORMAL",
]


@dataclass
class DiagnosticEvidence:
    """Aggregated evidence vector from Tiers 0-3 for classifier input."""
    residual_norm: float = 0.0          # Normalized residual deviation [0, 1]
    ensemble_score: float = 0.0         # Stage 2 PyOD + AE fused score [0, 1]
    physics_flag: Optional[str] = None  # Stage 3A thermodynamic flag ('MULTIVARIATE_INCONSISTENCY')
    spatial_shield: bool = False        # Stage 3B Genuine-Event Safety Shield active
    spatial_inconsistent: bool = False  # Station diverges from regional neighbors
    tier0_flags: Dict[str, Any] = field(default_factory=dict)
    frozen_ratio: float = 0.0
    missing_ratio: float = 0.0
    drift_slope: float = 0.0
    simultaneous_step_count: int = 0


@dataclass
class ClassificationResult:
    """Classified diagnosis and dual-metric scores."""
    predicted_class: str
    anomaly_score: float
    confidence: float
    is_fault: bool
    evidence_summary: Dict[str, Any]
    justification: str


def compute_evidence_agreement(evidence: DiagnosticEvidence) -> float:
    """
    Computes agreement ratio across independent screening tiers [0.0, 1.0].
    """
    votes = [
        evidence.ensemble_score > 0.50,
        evidence.residual_norm > 0.50,
        evidence.physics_flag is not None,
        evidence.spatial_inconsistent,
        bool(evidence.tier0_flags and evidence.tier0_flags.get("any_tier0_flag", False)),
    ]
    agreement = sum(1 for v in votes if v) / max(1, len(votes))
    return float(np.clip(agreement, 0.0, 1.0))


class EvidenceFusionClassifier:
    """
    Calibrated evidence fusion engine mapping diagnostic signals to the 8-class taxonomy.
    """

    def classify(self, evidence: DiagnosticEvidence) -> ClassificationResult:
        """
        Executes deterministic, auditable hierarchical evidence fusion.
        """
        t0 = evidence.tier0_flags
        ens_score = float(np.clip(evidence.ensemble_score, 0.0, 1.0))
        agreement = compute_evidence_agreement(evidence)

        # 1. Communication Dropout
        if evidence.missing_ratio > 0.40 or t0.get("null_dropout", False) or t0.get("null_dropout_error", False) or t0.get("flag") == "NULL_DROPOUT":
            return ClassificationResult(
                predicted_class="COMMUNICATION_DROPOUT",
                anomaly_score=0.90,
                confidence=0.92,
                is_fault=True,
                evidence_summary={"missing_ratio": evidence.missing_ratio, "tier0": t0},
                justification="Severe telemetry packet loss or null readings detected during transmission.",
            )

        # 2. Data Corruption (Physical Law Violation or Extreme Physical Bound Breach)
        if evidence.physics_flag is not None or t0.get("out_of_range", False) or t0.get("temperature_c_range_error", False) or t0.get("pressure_hpa_range_error", False) or t0.get("flag") == "OUT_OF_RANGE":
            return ClassificationResult(
                predicted_class="DATA_CORRUPTION",
                anomaly_score=0.95,
                confidence=0.94,
                is_fault=True,
                evidence_summary={"physics_flag": evidence.physics_flag, "tier0": t0},
                justification="Telemetry violates thermodynamic atmospheric invariants (Magnus dew point or extreme WMO boundaries).",
            )

        # 3. Frozen Sensor (Zero Variance)
        if evidence.frozen_ratio > 0.70 or t0.get("frozen_sensor", False) or t0.get("any_frozen_error", False) or t0.get("flag") == "FROZEN_SENSOR" or any("frozen" in k and v for k, v in t0.items()):
            return ClassificationResult(
                predicted_class="FROZEN_SENSOR",
                anomaly_score=0.92,
                confidence=0.90,
                is_fault=True,
                evidence_summary={"frozen_ratio": evidence.frozen_ratio, "tier0": t0},
                justification="Sensor output completely flatlined over rolling temporal window despite ambient fluctuations.",
            )

        # 4. Genuine Weather Event (Safety Shield)
        # If neighbors confirm the deviation, suppress fault alarms
        if evidence.spatial_shield and (ens_score > 0.35 or evidence.residual_norm > 0.40):
            return ClassificationResult(
                predicted_class="GENUINE_WEATHER_EVENT",
                anomaly_score=0.05,
                confidence=max(0.85, 1.0 - ens_score * 0.2),
                is_fault=False,
                evidence_summary={
                    "spatial_shield": True,
                    "ensemble_score": ens_score,
                    "residual_norm": evidence.residual_norm,
                },
                justification="Deviation corroborated across regional neighbor stations. Verified as genuine meteorological phenomenon.",
            )

        # 5. Power Fluctuation (Simultaneous Step Changes across multiple sensors)
        if evidence.simultaneous_step_count >= 2 or ((t0.get("step_spike", False) or t0.get("flag") == "STEP_SPIKE") and evidence.simultaneous_step_count >= 2):
            return ClassificationResult(
                predicted_class="POWER_FLUCTUATION",
                anomaly_score=0.88,
                confidence=0.86,
                is_fault=True,
                evidence_summary={"simultaneous_step_count": evidence.simultaneous_step_count},
                justification="Synchronized abrupt step changes observed simultaneously across multiple sensor channels.",
            )

        # 6. Spike (Single-channel impulse surge)
        if t0.get("step_spike", False) or t0.get("step_delta_error", False) or t0.get("flag") == "STEP_SPIKE" or (ens_score > 0.70 and evidence.residual_norm > 0.50):
            return ClassificationResult(
                predicted_class="SPIKE",
                anomaly_score=max(0.85, ens_score),
                confidence=max(0.80, agreement),
                is_fault=True,
                evidence_summary={"ensemble_score": ens_score, "residual_norm": evidence.residual_norm},
                justification="High rate-of-change impulse spike exceeding atmospheric maximum velocity.",
            )

        # 7. Calibration Drift (Persistent low-velocity residual creep)
        if abs(evidence.drift_slope) > 0.05 and ens_score > 0.35 and evidence.spatial_inconsistent:
            return ClassificationResult(
                predicted_class="CALIBRATION_DRIFT",
                anomaly_score=ens_score,
                confidence=0.80,
                is_fault=True,
                evidence_summary={"drift_slope": evidence.drift_slope, "ensemble_score": ens_score},
                justification="Progressive calibration offset accumulating monotonically over consecutive observation cycles.",
            )

        # 8. Unclassified anomaly or Normal
        if ens_score > 0.50:
            return ClassificationResult(
                predicted_class="DATA_CORRUPTION",
                anomaly_score=ens_score,
                confidence=agreement,
                is_fault=True,
                evidence_summary={"ensemble_score": ens_score},
                justification="Multi-tier residual ensemble detected anomalous deviation from diurnal baseline.",
            )

        return ClassificationResult(
            predicted_class="NORMAL",
            anomaly_score=min(0.20, ens_score),
            confidence=max(0.80, 1.0 - ens_score),
            is_fault=False,
            evidence_summary={"ensemble_score": ens_score, "residual_norm": evidence.residual_norm},
            justification="Observation fully consistent with historical diurnal baseline and regional neighbors.",
        )
