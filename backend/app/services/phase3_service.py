"""
backend/app/services/phase3_service.py
DataMend — Phase 3 Diagnostic Orchestrator Service.

Orchestrates all tiers:
Tier 0 (Deterministic Screener)
  -> Stage 1 (STL Diurnal Baseline & Cold-Start Inheritance)
  -> Stage 2 (Multivariate Residual Ensemble: PyOD + Sequence Autoencoder)
  -> Stage 3A (Thermodynamic Consistency: Magnus Dew Point & Hypsometric SLP)
  -> Stage 3B (Spatial Consensus & Genuine-Weather-Event Safety Shield)
  -> Stage 4 (8-Class Calibrated Fault Classifier)
  -> Stage 5 (TreeSHAP Feature Attribution & Forensic Narrative XAI)
  -> Stage 6 (Meteorological Safe Imputation: Dual STL + Spatial IDW)
  -> Tier 3.5 (Sensor Health Degradation & RUL Predictive Maintenance)
  -> TimescaleDB Persistence (anomaly_events & sensor_health hypertables)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from backend.app.ml.screening import tier0_screener, Tier0Result
from backend.app.ml.stages import (
    STLBaselineEngine,
    CHANNELS,
    StationBaseline,
    MultivariateEnsembleDetector,
    ThermodynamicPhysicsValidator,
    DiagnosticEvidence,
    EvidenceFusionClassifier,
    ClassificationResult,
    stage5_explain_engine,
    ExplanationReport,
    meteorological_safe_imputer,
    ImputationResult,
)
from backend.app.spatial.consensus import spatial_consensus_engine, haversine_distance_km
from backend.app.health.tracker import predictive_health_tracker, StationHealthSnapshot

logger = logging.getLogger(__name__)


@dataclass
class Phase3Diagnosis:
    """Full end-to-end diagnostic evaluation for an AWS observation reading."""
    station_id: str
    timestamp: datetime
    predicted_class: str
    anomaly_score: float
    confidence: float
    is_fault: bool
    tier0_passed: bool
    tier0_flags: Dict[str, Any]
    residuals: Dict[str, float]
    ensemble_score: float
    physics_valid: bool
    spatial_supported: bool
    genuine_shield: bool
    justification: str
    # Phase 3 Fields
    explanation: Dict[str, Any]
    imputation: Dict[str, Any]
    sensor_health: Dict[str, Any]
    latency_ms: float


class Phase3PipelineService:
    """
    Singleton service managing the complete Phase 1 through Phase 3 quality control pipeline.
    """

    def __init__(self) -> None:
        self.stl_engine = STLBaselineEngine(default_period=96)
        self.ensemble_detector = MultivariateEnsembleDetector(if_weight=0.55)
        self.physics_validator = ThermodynamicPhysicsValidator()
        self.classifier = EvidenceFusionClassifier()
        self.explain_engine = stage5_explain_engine
        self.imputer = meteorological_safe_imputer
        self.health_tracker = predictive_health_tracker

        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._max_history: int = 192

    def fit_baseline_for_station(self, station_id: str, df: pd.DataFrame) -> StationBaseline:
        """Fits diurnal STL baseline profile for a station."""
        return self.stl_engine.fit_station(station_id, df)

    def evaluate_reading(
        self,
        station_id: str,
        timestamp: datetime,
        temperature_c: Optional[float],
        pressure_hpa: Optional[float],
        humidity_pct: Optional[float],
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        altitude_m: float = 0.0,
        dew_point_c: Optional[float] = None,
        active_neighbor_readings: Optional[List[Dict[str, Any]]] = None,
    ) -> Phase3Diagnosis:
        """
        Executes the full 7-stage diagnostic and restorative pipeline.
        Target SLA latency: <= 20 ms.
        """
        t0_start = time.perf_counter()

        raw_telemetry = {
            "temperature_c": temperature_c,
            "pressure_hpa": pressure_hpa,
            "humidity_pct": humidity_pct,
            "latitude": latitude,
            "longitude": longitude,
            "altitude_m": altitude_m,
            "dew_point_c": dew_point_c,
        }

        # Rolling history buffer
        hist = self._history.setdefault(station_id, [])
        reading_record = {"timestamp": timestamp, **raw_telemetry}
        hist.append(reading_record)
        if len(hist) > self._max_history:
            hist.pop(0)

        # ---------------------------------------------------------------------
        # Tier 0: Ingestion Screening
        # ---------------------------------------------------------------------
        tier0_eval = tier0_screener.screen(
            station_id=station_id,
            reading={
                "temperature": temperature_c,
                "pressure": pressure_hpa,
                "humidity": humidity_pct,
            },
            altitude_m=altitude_m,
        )
        tier0_passed = (tier0_eval.status == "PASS")
        tier0_dict = {
            "status": tier0_eval.status,
            "flag": tier0_eval.flag,
            "violated_param": tier0_eval.violated_param,
            "reason": tier0_eval.reason,
            "any_tier0_flag": (tier0_eval.status != "PASS"),
            "step_spike": (tier0_eval.flag == "STEP_SPIKE"),
            "frozen_sensor": (tier0_eval.flag == "FROZEN_SENSOR"),
            "null_dropout": (tier0_eval.flag == "NULL_DROPOUT"),
            "out_of_range": (tier0_eval.flag == "OUT_OF_RANGE"),
        }

        # ---------------------------------------------------------------------
        # Stage 1: STL Baseline & Residuals
        # ---------------------------------------------------------------------
        t_val = temperature_c if temperature_c is not None else 25.0
        p_val = pressure_hpa if pressure_hpa is not None else 1013.25
        h_val = humidity_pct if humidity_pct is not None else 60.0
        sample_arr = np.array([[t_val, p_val, h_val]], dtype=float)

        raw_residuals = self.stl_engine.get_residuals(station_id, sample_arr)
        t_res, p_res, h_res = float(raw_residuals[0, 0]), float(raw_residuals[0, 1]), float(raw_residuals[0, 2])
        residuals_dict = {
            "temperature_c_resid": round(t_res, 3),
            "pressure_hpa_resid": round(p_res, 3),
            "humidity_pct_resid": round(h_res, 3),
        }
        res_norm = float(np.clip(np.linalg.norm([t_res / 5.0, p_res / 5.0, h_res / 20.0]), 0.0, 1.0))

        # ---------------------------------------------------------------------
        # Stage 2: Multivariate Residual Ensemble
        # ---------------------------------------------------------------------
        ens_res = self.ensemble_detector.score(raw_residuals)
        ensemble_score = float(ens_res.fused_score[0]) if len(ens_res.fused_score) > 0 else 0.0

        # ---------------------------------------------------------------------
        # Stage 3A: Thermodynamic Physics Validator
        # ---------------------------------------------------------------------
        physics_res = self.physics_validator.validate_reading(
            temperature_c=temperature_c,
            pressure_hpa=pressure_hpa,
            humidity_pct=humidity_pct,
            altitude_m=altitude_m,
            dew_point_c=dew_point_c,
            recent_history=hist[:-1],
        )

        # ---------------------------------------------------------------------
        # Stage 3B: Spatial Consensus & Genuine-Weather-Event Safety Shield
        # ---------------------------------------------------------------------
        spatial_telemetry = {
            "temperature": t_val,
            "pressure": p_val,
            "humidity": h_val,
        }
        spatial_eval = spatial_consensus_engine.evaluate_consensus(
            target_station_id=station_id,
            target_lat=latitude,
            target_lon=longitude,
            target_telemetry=spatial_telemetry,
            neighbor_observations=active_neighbor_readings or [],
        )

        # ---------------------------------------------------------------------
        # Stage 4: 8-Class Fault Classifier
        # ---------------------------------------------------------------------
        evidence = DiagnosticEvidence(
            residual_norm=res_norm,
            ensemble_score=ensemble_score,
            physics_flag=physics_res.flag,
            spatial_shield=spatial_eval.genuine_event_shield,
            spatial_inconsistent=not spatial_eval.regional_event_supported,
            tier0_flags=tier0_dict,
            frozen_ratio=1.0 if tier0_eval.flag == "FROZEN_SENSOR" else 0.0,
            missing_ratio=1.0 if tier0_eval.flag == "NULL_DROPOUT" else 0.0,
            drift_slope=t_res / 10.0,
            simultaneous_step_count=1 if tier0_eval.flag == "STEP_SPIKE" else 0,
        )
        classification = self.classifier.classify(evidence)

        # ---------------------------------------------------------------------
        # Stage 5: Explainable AI & TreeSHAP Attribution (Phase 3)
        # ---------------------------------------------------------------------
        # Look up existing health status for narrative context
        existing_health_ch = self.health_tracker._stations.get(station_id, {}).get("temperature_c")
        deg_info = {
            "status": existing_health_ch.status if existing_health_ch else "STABLE",
            "recent_anomaly_rate": existing_health_ch.recent_anomaly_rate if existing_health_ch else 0.0,
            "baseline_anomaly_rate": existing_health_ch.baseline_anomaly_rate if existing_health_ch else 0.0,
            "reasoning": existing_health_ch.recommended_action if existing_health_ch else "",
        } if existing_health_ch else None

        explanation_report = self.explain_engine.explain(
            station_id=station_id,
            predicted_class=classification.predicted_class,
            anomaly_score=classification.anomaly_score,
            confidence=classification.confidence,
            raw_telemetry=raw_telemetry,
            residuals=residuals_dict,
            tier0_flags=tier0_dict,
            degradation_info=deg_info,
        )

        # ---------------------------------------------------------------------
        # Stage 6: Safe Meteorological Imputation & Self-Healing (Phase 3)
        # ---------------------------------------------------------------------
        station_baseline = self.stl_engine.get(station_id)
        # Identify primary corrupted parameter
        primary_param = explanation_report.top_drivers[0] if explanation_report.top_drivers else "temperature_c"
        primary_orig_val = raw_telemetry.get(primary_param)

        imputation_res = self.imputer.impute_reading(
            station_id=station_id,
            timestamp=timestamp,
            parameter=primary_param,
            original_value=primary_orig_val,
            predicted_class=classification.predicted_class,
            baseline=station_baseline,
            neighbor_observations=active_neighbor_readings or [],
            target_lat=latitude,
            target_lon=longitude,
        )

        # ---------------------------------------------------------------------
        # Tier 3.5: Sensor Health & Predictive Maintenance (Phase 3)
        # ---------------------------------------------------------------------
        health_snapshot = self.health_tracker.record_reading(
            station_id=station_id,
            timestamp=timestamp,
            predicted_class=classification.predicted_class,
            anomaly_score=classification.anomaly_score,
            is_fault=classification.is_fault,
            primary_channel=primary_param,
            residual_val=residuals_dict.get(f"{primary_param}_resid", 0.0),
        )

        elapsed_ms = (time.perf_counter() - t0_start) * 1000.0

        return Phase3Diagnosis(
            station_id=station_id,
            timestamp=timestamp,
            predicted_class=classification.predicted_class,
            anomaly_score=round(classification.anomaly_score, 4),
            confidence=round(classification.confidence, 4),
            is_fault=classification.is_fault,
            tier0_passed=tier0_passed,
            tier0_flags=tier0_dict,
            residuals=residuals_dict,
            ensemble_score=round(ensemble_score, 4),
            physics_valid=physics_res.is_valid,
            spatial_supported=spatial_eval.regional_event_supported,
            genuine_shield=spatial_eval.genuine_event_shield,
            justification=classification.justification,
            explanation=explanation_report.to_dict(),
            imputation={
                "parameter": imputation_res.parameter,
                "original_value": imputation_res.original_value,
                "corrected_value": imputation_res.corrected_value,
                "method": imputation_res.method,
                "confidence": imputation_res.confidence,
                "is_imputed": imputation_res.is_imputed,
                "justification": imputation_res.justification,
            },
            sensor_health={
                "health_score": health_snapshot.overall_health_score,
                "health_status": health_snapshot.health_status,
                "degradation_risk": health_snapshot.degradation_risk,
                "anomaly_rate_30d": health_snapshot.anomaly_rate_30d,
                "drift_score": health_snapshot.drift_score,
                "data_quality_score": health_snapshot.data_quality_score,
                "estimated_hours_to_failure": health_snapshot.estimated_hours_to_failure,
                "recommended_action": health_snapshot.recommended_action,
                "channel_health": health_snapshot.channel_health,
            },
            latency_ms=round(elapsed_ms, 2),
        )

    async def persist_to_db(self, diagnosis: Phase3Diagnosis) -> None:
        """
        Asynchronously persists diagnosis to TimescaleDB anomaly_events and sensor_health hypertables.
        """
        try:
            from backend.app.db.database import get_db
            from backend.app.db.models import AnomalyEventModel, SensorHealthModel

            async for session in get_db():
                # Severity determination
                if diagnosis.anomaly_score >= 0.85:
                    severity = "CRITICAL"
                elif diagnosis.anomaly_score >= 0.60:
                    severity = "HIGH"
                elif diagnosis.anomaly_score >= 0.40:
                    severity = "MEDIUM"
                else:
                    severity = "LOW"

                # 1. AnomalyEvent persistence
                if diagnosis.is_fault or diagnosis.predicted_class == "GENUINE_WEATHER_EVENT":
                    event = AnomalyEventModel(
                        event_id=f"EVT_{diagnosis.timestamp.strftime('%Y%m%d%H%M%S')}_{diagnosis.station_id[-4:]}",
                        station_id=diagnosis.station_id,
                        timestamp=diagnosis.timestamp,
                        parameter=diagnosis.imputation.get("parameter", "multivariate"),
                        anomaly_score=diagnosis.anomaly_score,
                        confidence=diagnosis.confidence,
                        severity=severity,
                        root_cause=diagnosis.predicted_class,
                        explanation=diagnosis.explanation.get("summary", diagnosis.justification),
                        corrected_value=diagnosis.imputation.get("corrected_value"),
                        spatial_supported=diagnosis.spatial_supported,
                    )
                    session.add(event)

                # 2. SensorHealth persistence
                sh = diagnosis.sensor_health
                health_rec = SensorHealthModel(
                    station_id=diagnosis.station_id,
                    timestamp=diagnosis.timestamp,
                    health_score=sh["health_score"],
                    health_status=sh["health_status"],
                    anomaly_rate=sh["anomaly_rate_30d"],
                    drift_score=sh["drift_score"],
                    data_quality_score=sh["data_quality_score"],
                    degradation_risk=sh["degradation_risk"],
                    estimated_hours_to_failure=sh["estimated_hours_to_failure"],
                    recommended_action=sh["recommended_action"],
                )
                session.add(health_rec)

                await session.commit()
                break
        except Exception as exc:
            logger.debug("Database persistence bypass (TimescaleDB not running or test env): %s", exc)


# Global singleton instance
phase3_pipeline_service = Phase3PipelineService()
