"""
backend/app/ml/pipeline.py
SkyGuard AI — Master 5-Tier ML Pipeline Engine Orchestrator.

Integrates:
- Tier 1: Deterministic Physical QC & Bounds
- Tier 2: Isolation Forest Point & GRU Autoencoder Temporal ML
- Tier 3: Clausius-Clapeyron & Mahalanobis Multivariate Consistency
- Fusion: Multi-Tier Evidence Fusion & Confidence Scoring
- Tier 4: Fault Taxonomy & Convective Front Disambiguation Classifier
- Tier 5: Dynamic Sensor Health Index & TreeSHAP Explainability
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.ml.fusion import AnomalyFusionEngine, FusionResult, TierScores as FusionTierScores
from backend.app.ml.preprocessor import DataPreprocessor, PreprocessorResult
from backend.app.ml.tier1_qc import Tier1QC, Tier1QCResult
from backend.app.ml.tier2_point_ml import IsolationForestPointDetector
from backend.app.ml.tier2_temporal_ml import TemporalAutoencoderDetector
from backend.app.ml.tier3_multivariate import Tier3MultivariateDetector, Tier3Result
from backend.app.ml.tier4_classifier import ClassificationResult, FaultClassifier
from backend.app.ml.tier5_explain import ExplainabilityEngine, ExplanationResult
from backend.app.ml.tier5_health import DegradationRisk, HealthStatus, SensorHealthEngine
from backend.app.spatial.consensus import spatial_consensus_engine, SpatialConsensusResult

logger = logging.getLogger(__name__)


class TierScores(BaseModel):
    tier1_qc_flag: bool = Field(..., description="Tier 1 deterministic QC violation flag")
    tier2_point_score: float = Field(..., description="Tier 2 Isolation Forest anomaly score [0, 1]")
    tier2_temporal_score: float = Field(..., description="Tier 2 GRU Autoencoder reconstruction score [0, 1]")
    tier3_multivariate_score: float = Field(..., description="Tier 3 Thermodynamic & Mahalanobis score [0, 1]")
    tier1_hard: Optional[float] = Field(0.0, description="Tier 1 hard override score")
    tier1_soft: Optional[float] = Field(0.0, description="Tier 1 soft continuous score")


class InferenceResult(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 observation timestamp")
    station_id: str = Field(..., description="Unique AWS station identifier")
    is_anomaly: bool = Field(..., description="Final fused anomaly decision flag")
    anomaly_score: float = Field(..., description="Unified continuous anomaly score [0, 1]")
    confidence: float = Field(..., description="Decision confidence score [0, 1]")
    severity: str = Field(..., description="Severity level: NONE, LOW, MEDIUM, HIGH, CRITICAL")
    classification: str = Field(..., description="Root-cause fault taxonomy classification")
    is_fault: bool = Field(True, description="True for hardware faults; False for normal or meteorological extremes")
    reason: str = Field(..., description="Contextual diagnostic explanation summary")
    explanation: ExplanationResult = Field(..., description="Diagnostic explanation with feature attributions")
    tier_scores: TierScores = Field(..., description="Individual scores from Tiers 1-3")
    sensor_health: float = Field(..., description="Dynamic 24h rolling Sensor Health Index [0, 100]")
    sensor_status: str = Field(..., description="Sensor health status: EXCELLENT, GOOD, DEGRADED, POOR, CRITICAL")
    recommended_action: str = Field(..., description="Actionable operator maintenance recommendation")
    degradation_risk: str = Field("STABLE", description="Degradation risk: STABLE, DEGRADING, HIGH_RISK, MAINTENANCE_REQUIRED")
    estimated_hours_to_failure: Optional[float] = Field(None, description="Estimated hours until SHI < 50")
    multivariate_diagnostics: Optional[Dict[str, Any]] = Field(default_factory=dict)
    raw_values: Optional[Dict[str, float]] = Field(default_factory=dict)
    spatial_consensus: Optional[Dict[str, Any]] = Field(default=None, description="Tier 3.5 spatial consensus buddy-check diagnostics")


class SkyGuardPipeline:
    """Production master orchestrator executing all 5 tiers of real-time AWS anomaly detection."""

    def __init__(
        self,
        model_dir: Union[Path, str] = "models",
        auto_load: bool = True,
    ):
        self.model_dir = Path(model_dir)
        self.preprocessor = DataPreprocessor(window_size=getattr(settings, "INFERENCE_WINDOW_SIZE", 30))
        self.tier1 = Tier1QC()
        self.tier2_point = IsolationForestPointDetector()
        self.tier2_temporal = TemporalAutoencoderDetector(window_size=getattr(settings, "INFERENCE_WINDOW_SIZE", 30))
        self.tier3_multivariate = Tier3MultivariateDetector()
        self.fusion = AnomalyFusionEngine(anomaly_threshold=getattr(settings, "ANOMALY_THRESHOLD", 0.50))
        self.tier4_classifier = FaultClassifier()
        self.tier5_health = SensorHealthEngine(
            window_size=getattr(settings, "HEALTH_ROLLING_WINDOW", 288),
            ema_alpha=getattr(settings, "HEALTH_EMA_ALPHA", 0.10),
        )
        self.tier5_explain = ExplainabilityEngine()

        if auto_load and self.model_dir.exists():
            self.load_models(self.model_dir)

    def load_models(self, model_dir: Union[Path, str]) -> None:
        """Loads all persisted model artifacts from disk."""
        self.model_dir = Path(model_dir)
        if not self.model_dir.exists():
            return

        # 1. Preprocessor scaler
        p_prep = self.model_dir / "preprocessor.joblib"
        if not p_prep.exists():
            p_prep = self.model_dir / "scaler.joblib"
        if p_prep.exists():
            try:
                self.preprocessor.load(p_prep)
            except Exception as e:
                logger.warning("Could not load preprocessor from %s: %s", p_prep, e)

        # 2. Tier 2 Isolation Forest
        p_iforest = self.model_dir / "isolation_forest.joblib"
        if p_iforest.exists():
            try:
                self.tier2_point.load(p_iforest)
            except Exception as e:
                logger.warning("Could not load Isolation Forest from %s: %s", p_iforest, e)

        # 3. Tier 2 Temporal GRU Autoencoder
        p_ae = self.model_dir / "temporal_autoencoder.pt"
        if not p_ae.exists():
            p_ae = self.model_dir / "autoencoder.pt"
        if p_ae.exists():
            try:
                self.tier2_temporal.load(p_ae)
            except Exception as e:
                logger.warning("Could not load Temporal Autoencoder from %s: %s", p_ae, e)

        # 4. Tier 3 Mahalanobis covariance
        p_maha = self.model_dir / "mahalanobis.joblib"
        if p_maha.exists():
            try:
                self.tier3_multivariate.load(p_maha)
            except Exception as e:
                logger.warning("Could not load Mahalanobis artifact from %s: %s", p_maha, e)

        # 5. Tier 4 Fault Classifier
        p_clf = self.model_dir / "fault_classifier.joblib"
        if p_clf.exists():
            try:
                self.tier4_classifier.load(p_clf)
            except Exception as e:
                logger.warning("Could not load Fault Classifier from %s: %s", p_clf, e)

        # 6. Tier 5 TreeSHAP Explainer initialization
        if self.tier2_point.model is not None:
            self.tier5_explain = ExplainabilityEngine(
                model=self.tier2_point.model,
                feature_names=self.preprocessor.feature_names,
                background_data=getattr(self.tier2_point, "background_sample", None),
            )

    def process_observation(
        self,
        obs: Union[Dict[str, Any], Any],
        neighbor_observations: Optional[List[Dict[str, Any]]] = None,
    ) -> InferenceResult:
        """Executes full 5-tier inference on a single real-time telemetry observation."""
        if hasattr(obs, "model_dump"):
            data = obs.model_dump()
        elif hasattr(obs, "dict"):
            data = obs.dict()
        else:
            data = dict(obs)

        station_id = str(data.get("station_id", "AWS-001"))
        timestamp = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        if isinstance(timestamp, datetime):
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = str(timestamp)

        raw_t = data.get("temperature")
        raw_p = data.get("pressure")
        raw_rh = data.get("humidity")

        # Safely convert to float if possible for preprocessor
        try:
            t = float(raw_t) if raw_t is not None else 20.0
        except (ValueError, TypeError):
            t = 20.0

        try:
            p = float(raw_p) if raw_p is not None else 1013.25
        except (ValueError, TypeError):
            p = 1013.25

        try:
            rh = float(raw_rh) if raw_rh is not None else 50.0
        except (ValueError, TypeError):
            rh = 50.0

        # Step 1: Update Preprocessor sliding buffer
        prep_res: PreprocessorResult = self.preprocessor.update(
            station_id=station_id,
            timestamp=timestamp,
            temperature=t,
            pressure=p,
            humidity=rh,
        )
        feat_vector = prep_res.scaled_vector
        raw_feat_dict = prep_res.raw_feature_dict
        seq_tensor = prep_res.sequence_tensor

        # Step 2: Tier 1 Deterministic QC
        t1_res: Tier1QCResult = self.tier1.evaluate(
            temperature=raw_t,
            pressure=raw_p,
            humidity=raw_rh,
            temp_history=prep_res.recent_temperatures[:-1] if len(prep_res.recent_temperatures) > 1 else None,
            press_history=prep_res.recent_pressures[:-1] if len(prep_res.recent_pressures) > 1 else None,
            humid_history=prep_res.recent_humidities[:-1] if len(prep_res.recent_humidities) > 1 else None,
            timestamp=timestamp,
        )

        # Step 3: Tier 2 Point & Temporal ML
        if t1_res.is_hard_override:
            s_point = 1.0
            s_temporal = 1.0
        else:
            s_point = float(self.tier2_point.predict_score(feat_vector))
            if prep_res.is_warm:
                s_temporal = float(self.tier2_temporal.predict_score(seq_tensor))
            else:
                s_temporal = 0.0

        # Step 4: Tier 3 Multivariate Consistency
        t3_res: Tier3Result = self.tier3_multivariate.evaluate(temperature=t, pressure=p, humidity=rh)
        s_tier3 = t3_res.tier3_score

        # Step 5: Anomaly Fusion Layer
        fusion_tier_scores = FusionTierScores(
            tier1_hard_flag=t1_res.is_hard_override,
            tier1_soft_score=t1_res.score,
            tier2_point_score=s_point,
            tier2_temporal_score=s_temporal,
            tier3_multivariate_score=s_tier3,
        )
        fusion_res: FusionResult = self.fusion.fuse(
            tier_scores=fusion_tier_scores,
            buffer_length=prep_res.buffer_length,
        )

        # Build buffer dataframe for temporal fault classification
        buffer_df = pd.DataFrame({
            "temperature": prep_res.recent_temperatures,
            "pressure": prep_res.recent_pressures,
            "humidity": prep_res.recent_humidities,
        })

        # Step 6: Tier 4 Fault Classifier
        clf_res: ClassificationResult = self.tier4_classifier.classify(
            current_observation=data,
            buffer_df=buffer_df,
            tier1_result=t1_res,
            tier3_result=t3_res,
            fusion_result=fusion_res,
            raw_features=raw_feat_dict,
            fused_score=fusion_res.fused_score,
            is_anomaly=fusion_res.is_anomaly,
        )

        # If meteorological front detected, mark is_anomaly = True for weather tracking, but is_fault = False
        is_final_anomaly = fusion_res.is_anomaly or (clf_res.fault_class.value == "METEOROLOGICAL_EXTREME")

        # Step 7: Tier 5 Dynamic Sensor Health Index
        shi, health_status, rec_action, deg_risk, ttf = self.tier5_health.update(
            station_id=station_id,
            timestamp=timestamp,
            is_anomaly=is_final_anomaly,
            is_frozen=t1_res.is_frozen,
            is_missing=t1_res.is_missing,
            temperature=t,
            fused_score=fusion_res.fused_score,
            fault_type=clf_res.classification,
        )

        # Step 8: Tier 5 TreeSHAP Explainability
        explanation: ExplanationResult = self.tier5_explain.explain(
            feature_vector=feat_vector,
            raw_values=raw_feat_dict,
            tier1_flags=t1_res.flags,
            tier3_info=t3_res.metadata,
            classification=clf_res.classification,
            fused_score=fusion_res.fused_score,
            confidence=fusion_res.confidence,
        )

        # Step 9: Tier 3.5 Additive Spatial Consensus Diagnostic
        spatial_dict = None
        if neighbor_observations is not None:
            try:
                spatial_res = spatial_consensus_engine.evaluate_consensus(
                    target_station_id=station_id,
                    target_lat=data.get("latitude"),
                    target_lon=data.get("longitude"),
                    target_telemetry={"temperature": t, "pressure": p, "humidity": rh},
                    neighbor_observations=neighbor_observations,
                )
                spatial_dict = spatial_res.model_dump()
            except Exception as e:
                logger.warning("Spatial consensus evaluation failed: %s", e)

        return InferenceResult(
            timestamp=timestamp_str,
            station_id=station_id,
            is_anomaly=is_final_anomaly,
            anomaly_score=round(fusion_res.fused_score, 4),
            confidence=round(fusion_res.confidence, 4),
            severity=fusion_res.severity,
            classification=clf_res.classification,
            is_fault=clf_res.is_fault,
            reason=explanation.summary,
            explanation=explanation,
            tier_scores=TierScores(
                tier1_qc_flag=t1_res.qc_flag,
                tier2_point_score=round(s_point, 4),
                tier2_temporal_score=round(s_temporal, 4),
                tier3_multivariate_score=round(s_tier3, 4),
                tier1_hard=1.0 if t1_res.is_hard_override else 0.0,
                tier1_soft=round(t1_res.score, 4),
            ),
            sensor_health=round(shi, 2),
            sensor_status=health_status.value,
            recommended_action=rec_action,
            degradation_risk=deg_risk.value,
            estimated_hours_to_failure=round(ttf, 1) if ttf is not None else None,
            multivariate_diagnostics=t3_res.diagnostics,
            raw_values={
                "temperature": t,
                "pressure": p,
                "humidity": rh,
            },
            spatial_consensus=spatial_dict,
        )

    def process_batch(self, df: pd.DataFrame, station_id: Optional[str] = None) -> List[InferenceResult]:
        """Processes historical time series sequentially, preserving temporal state continuity."""
        results: List[InferenceResult] = []
        df_sorted = df.copy()
        if "timestamp" in df_sorted.columns:
            try:
                df_sorted["_dt"] = pd.to_datetime(df_sorted["timestamp"])
                df_sorted = df_sorted.sort_values("_dt").drop(columns=["_dt"])
            except Exception:
                pass

        for rec in df_sorted.to_dict(orient="records"):
            if station_id:
                rec["station_id"] = station_id
            results.append(self.process_observation(rec))
        return results

    def reset_station(self, station_id: str) -> None:
        """Resets sliding state and health tracking for a station."""
        self.preprocessor.reset_station(station_id)
        self.tier5_health.reset_station(station_id)

    def reset(self) -> None:
        """Resets all rolling buffers and stations."""
        self.preprocessor = DataPreprocessor(window_size=getattr(settings, "INFERENCE_WINDOW_SIZE", 30))
        self.tier1 = Tier1QC()
        self.tier5_health = SensorHealthEngine(
            window_size=getattr(settings, "HEALTH_ROLLING_WINDOW", 288),
            ema_alpha=getattr(settings, "HEALTH_EMA_ALPHA", 0.10),
        )


AnomalyPipelineOrchestrator = SkyGuardPipeline
