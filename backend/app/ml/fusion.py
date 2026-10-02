"""
backend/app/ml/fusion.py
Multi-Tier Anomaly Score Fusion, Confidence Estimation, and Severity Engine.

Synthesizes evidence from Tier 1 QC, Tier 2 Point ML, Tier 2 Temporal ML,
and Tier 3 Multivariate Consistency using hard overrides and convex combination.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import numpy as np

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class TierScores:
    tier1_hard_flag: bool = False
    tier1_soft_score: float = 0.0
    tier2_point_score: float = 0.0
    tier2_temporal_score: float = 0.0
    tier3_multivariate_score: float = 0.0


@dataclass
class FusionResult:
    fused_score: float
    confidence: float
    severity: str  # Can store Enum value string ("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")
    is_anomaly: bool
    tier_scores: Dict[str, float]
    override_applied: bool
    contributing_tiers: List[str]
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fused_score": round(self.fused_score, 4),
            "confidence": round(self.confidence, 4),
            "severity": str(self.severity),
            "is_anomaly": self.is_anomaly,
            "tier_scores": {k: round(v, 4) for k, v in self.tier_scores.items()},
            "override_applied": self.override_applied,
            "contributing_tiers": self.contributing_tiers,
            "diagnostics": self.diagnostics,
        }


class AnomalyFusionEngine:
    """
    Synthesizes multi-tier anomaly evidence into unified score, confidence, and severity.
    """

    def __init__(
        self,
        weight_tier1: float = 0.25,
        weight_tier2_point: float = 0.20,
        weight_tier2_temporal: float = 0.25,
        weight_tier3: float = 0.30,
        anomaly_threshold: Optional[float] = None,
        threshold: Optional[float] = None,
        required_buffer_length: int = 30,
    ) -> None:
        self.w1 = weight_tier1
        self.w2_pt = weight_tier2_point
        self.w2_temp = weight_tier2_temporal
        self.w3 = weight_tier3
        self.anomaly_threshold = anomaly_threshold or threshold or 0.45
        self.required_buffer_length = required_buffer_length

        # Normalize weights to sum to 1.0
        total_w = self.w1 + self.w2_pt + self.w2_temp + self.w3
        if total_w > 0:
            self.w1 /= total_w
            self.w2_pt /= total_w
            self.w2_temp /= total_w
            self.w3 /= total_w

    def compute_confidence(
        self,
        scores: List[float],
        buffer_length: int,
        override_applied: bool = False,
    ) -> float:
        """
        Calculate decision confidence based on inter-model concordance and buffer length.
        """
        # Buffer cold-start penalty
        if buffer_length < self.required_buffer_length:
            buffer_penalty = 0.20 * (1.0 - (buffer_length / self.required_buffer_length))
        else:
            buffer_penalty = 0.0

        if override_applied:
            return float(np.clip(1.0 - buffer_penalty, 0.10, 1.00))

        if not scores:
            return float(np.clip(0.85 - buffer_penalty, 0.10, 1.00))

        if len(scores) == 1:
            return float(np.clip(0.90 - buffer_penalty, 0.10, 1.00))

        arr = np.array(scores, dtype=np.float64)
        std_dev = float(np.std(arr))
        # Concordance scaling
        concordance = 1.0 - min(1.0, np.sqrt(3.0) * std_dev)
        raw_conf = concordance - buffer_penalty
        return float(np.clip(raw_conf, 0.10, 1.00))

    def map_severity(self, fused_score: float, override_applied: bool = False) -> str:
        """Map fused anomaly score to standardized Severity string."""
        if override_applied or fused_score >= 0.85:
            return Severity.CRITICAL.value
        elif fused_score >= 0.65:
            return Severity.HIGH.value
        elif fused_score >= 0.45:
            return Severity.MEDIUM.value
        elif fused_score >= 0.25:
            return Severity.LOW.value
        else:
            return Severity.NONE.value

    def fuse(
        self,
        tier_scores: Optional[TierScores] = None,
        buffer_length: int = 30,
        tier1_flag: Optional[bool] = None,
        s_point: Optional[float] = None,
        s_temporal: Optional[float] = None,
        s_tier3: Optional[float] = None,
        history_length: Optional[int] = None,
        tier1_soft_score: Optional[float] = None,
    ) -> FusionResult:
        """
        Execute multi-tier evidence fusion. Supports both TierScores object and direct arguments.
        """
        eff_buffer = history_length if history_length is not None else buffer_length

        if tier_scores is not None:
            t1_hard = tier_scores.tier1_hard_flag
            t1_soft = tier_scores.tier1_soft_score
            pt = tier_scores.tier2_point_score
            temp = tier_scores.tier2_temporal_score
            m3 = tier_scores.tier3_multivariate_score
        else:
            t1_hard = bool(tier1_flag) if tier1_flag is not None else False
            t1_soft = float(tier1_soft_score) if tier1_soft_score is not None else (1.0 if t1_hard else 0.0)
            pt = float(s_point) if s_point is not None else 0.0
            temp = float(s_temporal) if s_temporal is not None else 0.0
            m3 = float(s_tier3) if s_tier3 is not None else 0.0

        # 1. Deterministic Tier 1 Hard Override
        if t1_hard:
            fused_score = 1.0
            override_applied = True
            severity = Severity.CRITICAL.value
            confidence = self.compute_confidence([], eff_buffer, override_applied=True)
            contributing = ["tier1_qc"]
        else:
            override_applied = False
            # 2. Weighted Convex Combination
            # If cold-start, redistribute temporal weight proportionally
            if eff_buffer < self.required_buffer_length:
                active_weights_sum = self.w1 + self.w2_pt + self.w3
                w1_eff = self.w1 / active_weights_sum
                wpt_eff = self.w2_pt / active_weights_sum
                w3_eff = self.w3 / active_weights_sum
                fused_score = (
                    w1_eff * float(np.clip(t1_soft, 0.0, 1.0))
                    + wpt_eff * float(np.clip(pt, 0.0, 1.0))
                    + w3_eff * float(np.clip(m3, 0.0, 1.0))
                )
                active_scores = [pt, m3]
            else:
                fused_score = (
                    self.w1 * float(np.clip(t1_soft, 0.0, 1.0))
                    + self.w2_pt * float(np.clip(pt, 0.0, 1.0))
                    + self.w2_temp * float(np.clip(temp, 0.0, 1.0))
                    + self.w3 * float(np.clip(m3, 0.0, 1.0))
                )
                active_scores = [pt, temp, m3]

            fused_score = float(np.clip(fused_score, 0.0, 1.0))
            severity = self.map_severity(fused_score, override_applied=False)
            confidence = self.compute_confidence(active_scores, eff_buffer, override_applied=False)

            # Identify contributing tiers
            contributing = []
            if t1_soft >= 0.30:
                contributing.append("tier1_qc")
            if pt >= 0.40:
                contributing.append("tier2_point_ml")
            if temp >= 0.40 and eff_buffer >= self.required_buffer_length:
                contributing.append("tier2_temporal_ml")
            if m3 >= 0.40:
                contributing.append("tier3_multivariate")

        is_anomaly = (fused_score >= self.anomaly_threshold) or override_applied

        return FusionResult(
            fused_score=fused_score,
            confidence=confidence,
            severity=severity,
            is_anomaly=is_anomaly,
            tier_scores={
                "tier1_hard": 1.0 if t1_hard else 0.0,
                "tier1_soft": t1_soft,
                "tier2_point": pt,
                "tier2_temporal": temp,
                "tier3_multivariate": m3,
            },
            override_applied=override_applied,
            contributing_tiers=contributing,
            diagnostics={
                "buffer_length": eff_buffer,
                "threshold_applied": self.anomaly_threshold,
                "weights": {
                    "w1": self.w1,
                    "w2_point": self.w2_pt,
                    "w2_temporal": self.w2_temp,
                    "w3": self.w3,
                },
            },
        )
