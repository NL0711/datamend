"""
backend/app/services/phase2_service.py
SkyGuard AI / DataMend — Phase 2 Diagnostic Orchestrator Service.

Orchestrates the entire Phase 2 ML anomaly engine:
Tier 0 (Ingestion Screener)
  -> Stage 1 (STL Diurnal Baseline & Cold-Start Inheritance)
  -> Stage 2 (Multivariate Residual Ensemble: PyOD + Autoencoder)
  -> Stage 3A (Thermodynamic Consistency: Magnus Dew Point + Hypsometric SLP)
  -> Stage 3B (Spatial Consensus + Genuine-Weather-Event Safety Shield)
  -> Stage 4 (8-Class Calibrated Fault Classifier)
  -> TimescaleDB Persistence (anomaly_events hypertable)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

import numpy as np
import pandas as pd

from backend.app.ml.tier0_screener import tier0_screener, Tier0Result
from backend.app.ml.stage1_stl import STLBaselineEngine, CHANNELS
from backend.app.ml.stage2_ensemble import MultivariateEnsembleDetector
from backend.app.ml.stage3_physics import ThermodynamicPhysicsValidator
from backend.app.spatial.consensus import spatial_consensus_engine, haversine_distance_km
from backend.app.ml.stage4_classifier import (
    DiagnosticEvidence,
    EvidenceFusionClassifier,
    ClassificationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class Phase2Diagnosis:
    """End-to-end diagnostic evaluation for an observation reading."""
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
    latency_ms: float


class Phase2PipelineService:
    """
    Singleton service managing the lifecycle and execution of the Phase 2 ML core.
    """

    def __init__(self) -> None:
        self.stl_engine = STLBaselineEngine(default_period=96)
        self.ensemble_detector = MultivariateEnsembleDetector(if_weight=0.55)
        self.physics_validator = ThermodynamicPhysicsValidator()
        self.classifier = EvidenceFusionClassifier()
        # In-memory station history buffers: station_id -> list of recent readings
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._max_history: int = 192  # 48 hours of 15-min observations

    def initialize_baselines_from_dataframe(self, df: pd.DataFrame) -> None:
        """
        Pre-fits STL baselines across all station series present in the historical dataset.
        """
        grouped = df.groupby("station_id")
        for sid, group in grouped:
            clean_group = group.sort_values("timestamp")
            if len(clean_group) >= 48:
                self.stl_engine.fit_station(str(sid), clean_group)
                logger.info("Fitted STL baseline for station %s (%d records)", sid, len(clean_group))

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
    ) -> Phase2Diagnosis:
        """
        Processes a single incoming AWS reading through the full 5-stage Phase 2 pipeline.
        Target SLA latency: <= 15 ms.
        """
        t0_start = time.perf_counter()

        reading_dict = {
            "station_id": station_id,
            "timestamp": timestamp,
            "temperature_c": temperature_c,
            "pressure_hpa": pressure_hpa,
            "humidity_pct": humidity_pct,
            "latitude": latitude,
            "longitude": longitude,
            "altitude_m": altitude_m,
            "dew_point_c": dew_point_c,
        }

        # Maintain temporal rolling history for station
        hist = self._history.setdefault(station_id, [])
        hist.append(reading_dict)
        if len(hist) > self._max_history:
            hist.pop(0)

        # ---------------------------------------------------------------------
        # 1. Tier 0: Ingestion Screening
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
        # 2. Stage 1: STL Baseline & Residual Extraction
        # ---------------------------------------------------------------------
        # Prepare 1x3 vector for [T, P, RH]
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
        # 3. Stage 2: Multivariate Residual Ensemble
        # ---------------------------------------------------------------------
        ens_res = self.ensemble_detector.score(raw_residuals)
        ensemble_score = float(ens_res.fused_score[0]) if len(ens_res.fused_score) > 0 else 0.0

        # ---------------------------------------------------------------------
        # 4. Stage 3A: Thermodynamic Physics Validator
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
        # 5. Stage 3B: Spatial Consensus & Genuine-Weather-Event Safety Shield
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
        # 6. Stage 4: Evidence Fusion Classifier
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
        elapsed_ms = (time.perf_counter() - t0_start) * 1000.0

        return Phase2Diagnosis(
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
            latency_ms=round(elapsed_ms, 2),
        )

    async def persist_anomaly_event_to_db(self, diagnosis: Phase2Diagnosis) -> None:
        """
        Asynchronously writes diagnosed anomalies directly into TimescaleDB anomaly_events hypertable.
        """
        if not diagnosis.is_fault and diagnosis.predicted_class != "GENUINE_WEATHER_EVENT":
            return

        try:
            from backend.app.db.database import get_db
            from backend.app.db.models import AnomalyEventModel
            from sqlalchemy.ext.asyncio import AsyncSession

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

                event = AnomalyEventModel(
                    event_id=f"EVT_{diagnosis.timestamp.strftime('%Y%m%d%H%M%S')}_{diagnosis.station_id[-4:]}",
                    station_id=diagnosis.station_id,
                    timestamp=diagnosis.timestamp,
                    parameter="multivariate",
                    anomaly_score=diagnosis.anomaly_score,
                    confidence=diagnosis.confidence,
                    severity=severity,
                    root_cause=diagnosis.predicted_class,
                    explanation=diagnosis.justification,
                    corrected_value=None,
                    spatial_supported=diagnosis.spatial_supported,
                )
                session.add(event)
                await session.commit()
                logger.info("Persisted Phase 2 AnomalyEvent to TimescaleDB: %s (%s)", event.event_id, event.root_cause)
                break
        except Exception as exc:
            logger.debug("Database persistence bypass (TimescaleDB not running or test env): %s", exc)


# Global singleton service
phase2_pipeline_service = Phase2PipelineService()
