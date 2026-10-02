"""
backend/app/services/ingestion_service.py
SkyGuard AI — Real-Time Telemetry Ingestion, 5-Tier ML Inference, Persistence & Batch Upload Service.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from backend.app.api.websocket import ws_manager
from backend.app.db.database import get_db_context
from backend.app.db.models import utcnow
from backend.app.db.repositories import (
    AnomalyRepository,
    HealthRepository,
    ObservationRepository,
    StationRepository,
    parse_datetime,
)
from backend.app.ml.pipeline import InferenceResult, SkyGuardPipeline
from backend.app.schemas.schemas import (
    ExplanationResultSchema,
    FeatureAttributionSchema,
    InferenceResultSchema,
    ObservationIngestResponse,
    ObservationResponse,
    TierScoresSchema,
    UploadRowError,
    UploadSummaryResponse,
)
from backend.app.services.analytics_service import analytics_service

logger = logging.getLogger(__name__)


class IngestionService:
    """Master ingestion service coordinating ML pipeline inference, DB persistence, and live streaming."""

    def __init__(self, pipeline: Optional[SkyGuardPipeline] = None) -> None:
        self.pipeline = pipeline or SkyGuardPipeline(auto_load=True)
        self._station_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _get_station_lock(self, station_id: str) -> asyncio.Lock:
        return self._station_locks[station_id]

    async def ingest_observation(
        self,
        obs_data: Dict[str, Any],
        save_db: bool = True,
        broadcast: bool = True,
    ) -> ObservationIngestResponse:
        """
        Executes full real-time ingestion:
        1. Acquires per-station asyncio lock.
        2. Executes 5-Tier ML Pipeline in worker thread.
        3. Persists records to database (Observation, AnomalyEvent, SensorHealth, Station status).
        4. Broadcasts telemetry and alerts to WebSocket subscribers.
        5. Profiles and logs execution latency.
        """
        data = dict(obs_data)
        station_id = str(data.get("station_id") or "AWS-001")
        data["station_id"] = station_id

        # Normalize timestamp
        ts_val = data.get("timestamp")
        if not ts_val:
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        elif isinstance(ts_val, datetime):
            data["timestamp"] = ts_val.isoformat()
        else:
            data["timestamp"] = str(ts_val)

        # Per-station concurrency locking to preserve time-series buffer continuity
        lock = self._get_station_lock(station_id)
        async with lock:
            t0 = time.perf_counter()

            # Execute CPU-bound 5-tier ML pipeline in thread pool
            inference_res: InferenceResult = await asyncio.to_thread(
                self.pipeline.process_observation, data
            )

            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            analytics_service.record_latency(latency_ms)

            # Build Pydantic inference schema
            inf_schema = InferenceResultSchema(
                timestamp=inference_res.timestamp,
                station_id=inference_res.station_id,
                is_anomaly=inference_res.is_anomaly,
                anomaly_score=inference_res.anomaly_score,
                confidence=inference_res.confidence,
                severity=inference_res.severity,
                classification=inference_res.classification,
                is_fault=inference_res.is_fault,
                reason=inference_res.reason,
                explanation=ExplanationResultSchema(
                    summary=inference_res.explanation.summary,
                    contributing_features=[
                        FeatureAttributionSchema(
                            feature=f.feature,
                            attribution=f.attribution,
                            raw_value=f.raw_value,
                            description=f.description,
                        )
                        for f in inference_res.explanation.contributing_features
                    ],
                    method=inference_res.explanation.method,
                ),
                tier_scores=TierScoresSchema(
                    tier1_qc_flag=inference_res.tier_scores.tier1_qc_flag,
                    tier2_point_score=inference_res.tier_scores.tier2_point_score,
                    tier2_temporal_score=inference_res.tier_scores.tier2_temporal_score,
                    tier3_multivariate_score=inference_res.tier_scores.tier3_multivariate_score,
                    tier1_hard=inference_res.tier_scores.tier1_hard,
                    tier1_soft=inference_res.tier_scores.tier1_soft,
                ),
                sensor_health=inference_res.sensor_health,
                sensor_status=inference_res.sensor_status,
                recommended_action=inference_res.recommended_action,
                degradation_risk=inference_res.degradation_risk,
                estimated_hours_to_failure=inference_res.estimated_hours_to_failure,
                multivariate_diagnostics=inference_res.multivariate_diagnostics,
                raw_values=inference_res.raw_values,
            )

            dt_parsed = parse_datetime(inference_res.timestamp) or utcnow()
            raw_t = data.get("temperature")
            raw_p = data.get("pressure")
            raw_rh = data.get("humidity")

            # Try to safely cast numeric raw values
            def _to_float(v: Any) -> Optional[float]:
                if v is None:
                    return None
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return None

            float_t = _to_float(raw_t)
            float_p = _to_float(raw_p)
            float_rh = _to_float(raw_rh)

            obs_id = 0
            persisted = False

            if save_db:
                async with get_db_context() as session:
                    station_repo = StationRepository(session)
                    obs_repo = ObservationRepository(session)
                    anomaly_repo = AnomalyRepository(session)
                    health_repo = HealthRepository(session)

                    # 1. Ensure Station entity exists
                    await station_repo.get_or_create(
                        station_id=station_id,
                        latitude=data.get("latitude"),
                        longitude=data.get("longitude"),
                        elevation=data.get("elevation"),
                    )

                    # 2. Insert Observation record
                    qc_flag = inference_res.tier_scores.tier1_qc_flag
                    obs_db = await obs_repo.create({
                        "station_id": station_id,
                        "timestamp": dt_parsed,
                        "temperature": float_t,
                        "pressure": float_p,
                        "humidity": float_rh,
                        "validation_status": "QC_FLAGGED" if qc_flag else "VALID",
                        "source_type": data.get("source_type", "SIMULATED"),
                        "source_id": data.get("source_id", "diurnal_generator"),
                        "provider": data.get("provider"),
                        "device_id": data.get("device_id"),
                    })
                    obs_id = obs_db.id

                    # 3. If Anomaly detected, insert AnomalyEvent
                    if inference_res.is_anomaly:
                        await anomaly_repo.create({
                            "observation_id": obs_id,
                            "station_id": station_id,
                            "timestamp": dt_parsed,
                            "is_anomaly": True,
                            "anomaly_score": inference_res.anomaly_score,
                            "confidence": inference_res.confidence,
                            "severity": inference_res.severity,
                            "anomaly_type": inference_res.classification,
                            "classification": inference_res.classification,
                            "is_fault": inference_res.is_fault,
                            "source_type": data.get("source_type", "SIMULATED"),
                            "source_id": data.get("source_id", "diurnal_generator"),
                            "reason": inference_res.reason,
                            "explanation": inference_res.explanation.model_dump(),
                            "tier_scores": inference_res.tier_scores.model_dump(),
                            "recommended_action": inference_res.recommended_action,
                            "raw_values": inference_res.raw_values,
                        })

                    # 4. Insert SensorHealth record
                    await health_repo.create({
                        "station_id": station_id,
                        "timestamp": dt_parsed,
                        "health_score": inference_res.sensor_health,
                        "health_status": inference_res.sensor_status,
                        "anomaly_rate": 0.0,
                        "drift_score": 0.0,
                        "data_quality_score": 0.5 if qc_flag else 1.0,
                        "degradation_risk": inference_res.degradation_risk,
                        "estimated_hours_to_failure": inference_res.estimated_hours_to_failure,
                        "recommended_action": inference_res.recommended_action,
                    })

                    # 5. Update Station status
                    new_station_status = (
                        inference_res.sensor_status
                        if inference_res.sensor_status in ["DEGRADED", "CRITICAL"]
                        else "ACTIVE"
                    )
                    await station_repo.update_status(station_id, new_station_status)
                    persisted = True

            # Construct ObservationResponse
            obs_resp = ObservationResponse(
                id=obs_id,
                station_id=station_id,
                timestamp=dt_parsed,
                temperature=float_t,
                pressure=float_p,
                humidity=float_rh,
                validation_status="QC_FLAGGED" if inference_res.tier_scores.tier1_qc_flag else "VALID",
                created_at=dt_parsed,
            )

            # Broadcast canonical observation & inference verdict via WebSocket
            if broadcast:
                broadcast_data = inf_schema.model_dump()
                broadcast_data["temperature"] = float_t
                broadcast_data["pressure"] = float_p
                broadcast_data["humidity"] = float_rh
                broadcast_data["latitude"] = data.get("latitude")
                broadcast_data["longitude"] = data.get("longitude")
                broadcast_data["elevation"] = data.get("elevation")
                broadcast_data["latency_ms"] = latency_ms
                broadcast_data["source"] = {
                    "type": data.get("source_type", "SIMULATED"),
                    "id": data.get("source_id", "diurnal_generator"),
                    "provider": data.get("provider", "SkyGuard-DiurnalEngine"),
                    "device_id": data.get("device_id"),
                }
                await ws_manager.broadcast_observation(station_id, broadcast_data)

                # Send explicit alert notification for severe anomalies
                if inference_res.is_anomaly and inference_res.severity in ["HIGH", "CRITICAL"]:
                    await ws_manager.broadcast_alert(
                        station_id=station_id,
                        severity=inference_res.severity,
                        message_text=f"{inference_res.classification}: {inference_res.reason}",
                        details={
                            "anomaly_score": inference_res.anomaly_score,
                            "confidence": inference_res.confidence,
                            "classification": inference_res.classification,
                            "recommended_action": inference_res.recommended_action,
                            "source_type": data.get("source_type", "SIMULATED"),
                        },
                    )

            return ObservationIngestResponse(
                observation=obs_resp,
                inference=inf_schema,
                persisted=persisted,
                execution_time_ms=latency_ms,
            )

    async def ingest_batch(
        self,
        observations: List[Dict[str, Any]],
        station_id: Optional[str] = None,
        save_db: bool = True,
    ) -> List[ObservationIngestResponse]:
        """Ingests a list of observations sequentially per station, preserving state continuity."""
        results: List[ObservationIngestResponse] = []
        for obs in observations:
            if station_id:
                obs["station_id"] = station_id
            res = await self.ingest_observation(obs, save_db=save_db, broadcast=False)
            results.append(res)
        return results

    async def process_csv_upload(
        self,
        file_content: bytes,
        filename: str,
        station_id: Optional[str] = None,
        reset_state: bool = False,
    ) -> UploadSummaryResponse:
        """
        Parses and ingests an uploaded CSV dataset:
        1. Normalizes flexible column headers.
        2. Validates schema and required columns.
        3. Sorts chronologically.
        4. Runs full sequential 5-tier pipeline inference.
        5. Persists records in transactional chunks (500 rows).
        6. Returns detailed summary with breakdown by fault taxonomy.
        """
        t0 = time.perf_counter()
        if not file_content:
            raise ValueError("Uploaded CSV file is empty (0 bytes).")

        try:
            df = pd.read_csv(io.BytesIO(file_content))
        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {e}")

        if df.empty:
            raise ValueError("Uploaded CSV contains no rows.")

        # Normalize column names: lowercase and stripped
        col_map: Dict[str, str] = {}
        for c in df.columns:
            clean_c = str(c).strip().lower()
            if clean_c in ["timestamp", "time", "datetime", "date", "ts"]:
                col_map[c] = "timestamp"
            elif clean_c in ["temperature", "temp", "t", "temp_c", "temperature_c"]:
                col_map[c] = "temperature"
            elif clean_c in ["pressure", "press", "p", "pressure_hpa", "baro"]:
                col_map[c] = "pressure"
            elif clean_c in ["humidity", "rh", "rel_humidity", "rel_hum", "hum", "humidity_pct"]:
                col_map[c] = "humidity"
            elif clean_c in ["station_id", "station", "stn_id", "stn"]:
                col_map[c] = "station_id"
            elif clean_c in ["latitude", "lat"]:
                col_map[c] = "latitude"
            elif clean_c in ["longitude", "lon", "long"]:
                col_map[c] = "longitude"
            elif clean_c in ["elevation", "elev", "altitude", "alt"]:
                col_map[c] = "elevation"

        df = df.rename(columns=col_map)

        required_cols = ["timestamp", "temperature", "pressure", "humidity"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required CSV columns: {', '.join(missing_cols)}")

        # Assign station_id if missing from CSV
        if "station_id" not in df.columns or df["station_id"].isna().all():
            df["station_id"] = station_id or "AWS-001"
        else:
            df["station_id"] = df["station_id"].fillna(station_id or "AWS-001").astype(str)

        # Sort chronologically by timestamp
        try:
            df["_parsed_ts"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_values("_parsed_ts").drop(columns=["_parsed_ts"])
        except Exception:
            pass

        unique_stations = df["station_id"].unique().tolist()

        if reset_state:
            for st in unique_stations:
                self.pipeline.reset_station(st)

        total_rows = len(df)
        valid_rows = 0
        anomalies_detected = 0
        faults_detected = 0
        anomalies_summary: Dict[str, int] = defaultdict(int)
        sample_anomalies: List[InferenceResultSchema] = []
        errors: List[UploadRowError] = []

        chunk_size = 500
        records = df.to_dict(orient="records")

        # Buffers for chunked DB persistence
        chunk_stations: Dict[str, Dict[str, Any]] = {}
        chunk_obs: List[Dict[str, Any]] = []
        chunk_anomalies: List[Tuple[Dict[str, Any], int]] = []
        chunk_health: List[Dict[str, Any]] = []
        chunk_latest_station_status: Dict[str, str] = {}

        async def _flush_db_chunk() -> None:
            if not chunk_obs:
                return
            async with get_db_context() as session:
                station_repo = StationRepository(session)
                obs_repo = ObservationRepository(session)
                anomaly_repo = AnomalyRepository(session)
                health_repo = HealthRepository(session)

                for st_id_key, st_meta in chunk_stations.items():
                    await station_repo.get_or_create(
                        station_id=st_id_key,
                        latitude=st_meta.get("latitude"),
                        longitude=st_meta.get("longitude"),
                        elevation=st_meta.get("elevation"),
                    )

                created_obs = await obs_repo.create_batch(chunk_obs)

                if chunk_anomalies:
                    anomaly_records = []
                    for anomaly_item, obs_idx in chunk_anomalies:
                        anomaly_item["observation_id"] = created_obs[obs_idx].id
                        anomaly_records.append(anomaly_item)
                    await anomaly_repo.create_batch(anomaly_records)

                if chunk_health:
                    await health_repo.create_batch(chunk_health)

                for st_id_key, st_status in chunk_latest_station_status.items():
                    await station_repo.update_status(st_id_key, st_status)

            chunk_stations.clear()
            chunk_obs.clear()
            chunk_anomalies.clear()
            chunk_health.clear()
            chunk_latest_station_status.clear()

        # Process observations sequentially
        for idx, row in enumerate(records, start=1):
            try:
                # Fast numeric conversion verification
                t_val = float(row["temperature"])
                p_val = float(row["pressure"])
                rh_val = float(row["humidity"])
            except (ValueError, TypeError) as e:
                errors.append(UploadRowError(row=idx, error=f"Invalid numeric data: {e}", raw_data=row))
                continue

            valid_rows += 1
            st_id = str(row["station_id"])

            if st_id not in chunk_stations:
                chunk_stations[st_id] = {
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "elevation": row.get("elevation"),
                }

            # Inference
            inf_res: InferenceResult = self.pipeline.process_observation(row)

            if inf_res.is_anomaly:
                anomalies_detected += 1
                if inf_res.is_fault:
                    faults_detected += 1
                anomalies_summary[inf_res.classification] += 1

                if len(sample_anomalies) < 10:
                    sample_anomalies.append(
                        InferenceResultSchema(
                            timestamp=inf_res.timestamp,
                            station_id=inf_res.station_id,
                            is_anomaly=inf_res.is_anomaly,
                            anomaly_score=inf_res.anomaly_score,
                            confidence=inf_res.confidence,
                            severity=inf_res.severity,
                            classification=inf_res.classification,
                            is_fault=inf_res.is_fault,
                            reason=inf_res.reason,
                            explanation=ExplanationResultSchema(
                                summary=inf_res.explanation.summary,
                                contributing_features=[
                                    FeatureAttributionSchema(
                                        feature=f.feature,
                                        attribution=f.attribution,
                                        raw_value=f.raw_value,
                                        description=f.description,
                                    )
                                    for f in inf_res.explanation.contributing_features
                                ],
                                method=inf_res.explanation.method,
                            ),
                            tier_scores=TierScoresSchema(
                                tier1_qc_flag=inf_res.tier_scores.tier1_qc_flag,
                                tier2_point_score=inf_res.tier_scores.tier2_point_score,
                                tier2_temporal_score=inf_res.tier_scores.tier2_temporal_score,
                                tier3_multivariate_score=inf_res.tier_scores.tier3_multivariate_score,
                                tier1_hard=inf_res.tier_scores.tier1_hard,
                                tier1_soft=inf_res.tier_scores.tier1_soft,
                            ),
                            sensor_health=inf_res.sensor_health,
                            sensor_status=inf_res.sensor_status,
                            recommended_action=inf_res.recommended_action,
                            degradation_risk=inf_res.degradation_risk,
                            estimated_hours_to_failure=inf_res.estimated_hours_to_failure,
                            multivariate_diagnostics=inf_res.multivariate_diagnostics,
                            raw_values=inf_res.raw_values,
                        )
                    )

            dt_parsed = parse_datetime(inf_res.timestamp) or utcnow()
            current_obs_idx = len(chunk_obs)

            chunk_obs.append({
                "station_id": st_id,
                "timestamp": dt_parsed,
                "temperature": t_val,
                "pressure": p_val,
                "humidity": rh_val,
                "validation_status": "QC_FLAGGED" if inf_res.tier_scores.tier1_qc_flag else "VALID",
            })

            if inf_res.is_anomaly:
                chunk_anomalies.append((
                    {
                        "station_id": st_id,
                        "timestamp": dt_parsed,
                        "is_anomaly": True,
                        "anomaly_score": inf_res.anomaly_score,
                        "confidence": inf_res.confidence,
                        "severity": inf_res.severity,
                        "anomaly_type": inf_res.classification,
                        "classification": inf_res.classification,
                        "is_fault": inf_res.is_fault,
                        "reason": inf_res.reason,
                        "explanation": inf_res.explanation.model_dump(),
                        "tier_scores": inf_res.tier_scores.model_dump(),
                        "recommended_action": inf_res.recommended_action,
                        "raw_values": inf_res.raw_values,
                    },
                    current_obs_idx,
                ))

            chunk_health.append({
                "station_id": st_id,
                "timestamp": dt_parsed,
                "health_score": inf_res.sensor_health,
                "health_status": inf_res.sensor_status,
                "anomaly_rate": 0.0,
                "drift_score": 0.0,
                "data_quality_score": 0.5 if inf_res.tier_scores.tier1_qc_flag else 1.0,
                "degradation_risk": inf_res.degradation_risk,
                "estimated_hours_to_failure": inf_res.estimated_hours_to_failure,
                "recommended_action": inf_res.recommended_action,
            })

            chunk_latest_station_status[st_id] = (
                inf_res.sensor_status if inf_res.sensor_status in ["DEGRADED", "CRITICAL"] else "ACTIVE"
            )

            # Flush chunk when reaching batch threshold
            if len(chunk_obs) >= chunk_size:
                await _flush_db_chunk()

        # Flush any remaining items in final chunk
        await _flush_db_chunk()

        exec_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        return UploadSummaryResponse(
            total_rows=total_rows,
            valid_rows=valid_rows,
            anomalies_detected=anomalies_detected,
            faults_detected=faults_detected,
            stations_updated=unique_stations,
            execution_time_ms=exec_ms,
            anomalies_summary=dict(anomalies_summary),
            sample_anomalies=sample_anomalies,
            errors=errors,
        )


# Global ingestion service singleton
ingestion_service = IngestionService()
