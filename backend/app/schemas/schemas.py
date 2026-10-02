"""
backend/app/schemas/schemas.py
SkyGuard AI — Pydantic v2 Schemas for Requests, Responses, and Pipeline Telemetry Contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. Core Telemetry & Observation Schemas
# ---------------------------------------------------------------------------
class ObservationBase(BaseModel):
    timestamp: Union[datetime, str] = Field(..., description="Observation timestamp (ISO 8601 or string)")
    station_id: str = Field(..., min_length=1, max_length=64, description="AWS Station identifier")
    temperature: float = Field(..., ge=-100.0, le=100.0, description="Temperature in Celsius")
    pressure: float = Field(..., ge=100.0, le=1500.0, description="Atmospheric pressure in hPa")
    humidity: float = Field(..., ge=-20.0, le=150.0, description="Relative humidity in %")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Station latitude")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Station longitude")
    elevation: Optional[float] = Field(None, ge=-500.0, le=9000.0, description="Station elevation in meters")


class ObservationCreate(ObservationBase):
    pass


class ObservationResponse(BaseModel):
    id: int
    station_id: str
    timestamp: datetime
    temperature: Optional[float] = None
    pressure: Optional[float] = None
    humidity: Optional[float] = None
    validation_status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ObservationListResponse(BaseModel):
    items: List[ObservationResponse]
    total: int
    page: int = 1
    page_size: int = 50


# ---------------------------------------------------------------------------
# 2. ML Inference, Tier Scores & Explainability Schemas
# ---------------------------------------------------------------------------
class FeatureAttributionSchema(BaseModel):
    feature: str = Field(..., description="Feature name (e.g. temp_delta)")
    attribution: float = Field(..., description="TreeSHAP / feature attribution weight")
    raw_value: Optional[float] = Field(None, description="Observed feature value")
    description: Optional[str] = Field(None, description="Operator-friendly feature description")


class ExplanationResultSchema(BaseModel):
    summary: str = Field(..., description="Human-readable root cause explanation")
    contributing_features: List[FeatureAttributionSchema] = Field(default_factory=list)
    method: str = Field("TreeSHAP", description="Explainability method")


class TierScoresSchema(BaseModel):
    tier1_qc_flag: bool = Field(..., description="Tier 1 deterministic QC violation flag")
    tier2_point_score: float = Field(..., description="Tier 2 Isolation Forest score [0, 1]")
    tier2_temporal_score: float = Field(..., description="Tier 2 GRU Autoencoder score [0, 1]")
    tier3_multivariate_score: float = Field(..., description="Tier 3 Mahalanobis/Thermo score [0, 1]")
    tier1_hard: Optional[float] = Field(0.0, description="Tier 1 hard override score")
    tier1_soft: Optional[float] = Field(0.0, description="Tier 1 soft continuous score")


class InferenceResultSchema(BaseModel):
    timestamp: str
    station_id: str
    is_anomaly: bool
    anomaly_score: float
    confidence: float
    severity: str
    classification: str
    is_fault: bool = True
    reason: str
    explanation: ExplanationResultSchema
    tier_scores: TierScoresSchema
    sensor_health: float
    sensor_status: str
    recommended_action: str
    degradation_risk: str = "STABLE"
    estimated_hours_to_failure: Optional[float] = None
    multivariate_diagnostics: Optional[Dict[str, Any]] = Field(default_factory=dict)
    raw_values: Optional[Dict[str, float]] = Field(default_factory=dict)
    model_config = ConfigDict(from_attributes=True)


class ObservationIngestResponse(BaseModel):
    observation: ObservationResponse
    inference: InferenceResultSchema
    persisted: bool = True
    execution_time_ms: float


# ---------------------------------------------------------------------------
# 3. Anomaly Event Schemas
# ---------------------------------------------------------------------------
class AnomalyEventResponse(BaseModel):
    id: int
    observation_id: Optional[int] = None
    station_id: str
    timestamp: datetime
    is_anomaly: bool = True
    anomaly_score: float
    confidence: float
    severity: str
    anomaly_type: Optional[str] = None
    classification: str
    is_fault: bool = True
    reason: Optional[str] = None
    explanation: Optional[Dict[str, Any]] = None
    tier_scores: Optional[Dict[str, Any]] = None
    recommended_action: Optional[str] = None
    raw_values: Optional[Dict[str, Any]] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AnomalyEventDetailResponse(AnomalyEventResponse):
    observation: Optional[ObservationResponse] = None
    station: Optional[StationResponse] = None


class AnomalyEventListResponse(BaseModel):
    items: List[AnomalyEventResponse]
    total: int
    page: int = 1
    page_size: int = 50


class AnomalyStatsResponse(BaseModel):
    period_hours: int
    total_anomalies: int
    by_severity: Dict[str, int]
    by_classification: Dict[str, int]
    sensor_faults: int
    meteorological_extremes: int


# ---------------------------------------------------------------------------
# 4. Station Management Schemas
# ---------------------------------------------------------------------------
class StationCreate(BaseModel):
    station_id: str = Field(..., min_length=1, max_length=64)
    name: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    elevation: Optional[float] = Field(None, ge=-500.0, le=9000.0)
    status: str = Field("ACTIVE", max_length=32)


class StationUpdate(BaseModel):
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation: Optional[float] = None
    status: Optional[str] = None


class StationResponse(BaseModel):
    id: int
    station_id: str
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation: Optional[float] = None
    status: str
    health_score: Optional[float] = None
    health_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class StationDetailResponse(StationResponse):
    latest_observation: Optional[ObservationResponse] = None
    recent_anomalies_count: int = 0


class StationListResponse(BaseModel):
    items: List[StationResponse]
    total: int


# ---------------------------------------------------------------------------
# 5. Sensor Health & Fleet Overview Schemas
# ---------------------------------------------------------------------------
class SensorHealthRecord(BaseModel):
    id: Optional[int] = None
    station_id: str
    timestamp: datetime
    health_score: float
    health_status: str
    anomaly_rate: float = 0.0
    drift_score: float = 0.0
    data_quality_score: float = 1.0
    degradation_risk: str = "STABLE"
    estimated_hours_to_failure: Optional[float] = None
    recommended_action: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class StationHealthDetailResponse(BaseModel):
    station_id: str
    current_health: float
    health_status: str
    degradation_risk: str
    estimated_hours_to_failure: Optional[float] = None
    recommended_action: Optional[str] = None
    recent_history: List[SensorHealthRecord] = Field(default_factory=list)


class FleetHealthSummaryResponse(BaseModel):
    total_stations: int
    active_stations: int
    degraded_stations: int
    critical_stations: int
    offline_stations: int
    average_health_score: float
    status_distribution: Dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 6. Live Simulation & Anomaly Injection Schemas
# ---------------------------------------------------------------------------
class SimulationStartRequest(BaseModel):
    station_ids: Optional[List[str]] = Field(default=None, description="Station IDs to simulate (default: all 4 presets)")
    interval_seconds: float = Field(1.0, ge=0.05, le=60.0, description="Step interval in seconds")
    noise_level: float = Field(0.05, ge=0.0, le=1.0, description="Noise multiplier")
    scenario: str = Field("diurnal", description="Simulation scenario preset")


class AnomalyInjectRequest(BaseModel):
    station_id: Optional[str] = Field(None, description="Target station ID (None applies to all or first active)")
    anomaly_type: str = Field(..., description="Fault type: SPIKE, DRIFT, FROZEN, DROPOUT, NOISE_BURST, MULTIVARIATE_INCONSISTENCY, METEOROLOGICAL_EXTREME, DATA_CORRUPTION")
    magnitude: Optional[float] = Field(None, description="Anomaly magnitude (e.g. +25.0°C or -15 hPa)")
    duration_steps: int = Field(1, ge=1, le=200, description="Duration in simulation steps")
    parameter: str = Field("temperature", description="Target parameter: temperature, pressure, humidity")
    decay: bool = Field(False, description="Whether spike decays exponentially")


class SimulationStatusResponse(BaseModel):
    running: bool
    interval_seconds: Optional[float] = None
    active_stations: List[str] = Field(default_factory=list)
    step_count: int = 0
    pending_injections_count: int = 0
    message: str


class AnomalyInjectResponse(BaseModel):
    success: bool
    anomaly_type: str
    station_id: Optional[str] = None
    parameter: str
    magnitude: Optional[float] = None
    duration_steps: int
    message: str


# ---------------------------------------------------------------------------
# 7. CSV Upload Schemas
# ---------------------------------------------------------------------------
class UploadRowError(BaseModel):
    row: int
    error: str
    raw_data: Optional[Dict[str, Any]] = None


class UploadSummaryResponse(BaseModel):
    total_rows: int
    valid_rows: int
    anomalies_detected: int
    faults_detected: int
    stations_updated: List[str]
    execution_time_ms: float
    anomalies_summary: Dict[str, int] = Field(default_factory=dict)
    sample_anomalies: List[InferenceResultSchema] = Field(default_factory=list)
    errors: List[UploadRowError] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 8. Analytics & Metrics Schemas
# ---------------------------------------------------------------------------
class MetricsResponse(BaseModel):
    total_observations: int
    total_anomalies: int
    anomaly_rate_pct: float
    anomaly_by_type: Dict[str, int]
    anomaly_by_severity: Dict[str, int]
    average_inference_latency_ms: float
    p50_inference_latency_ms: float
    p95_inference_latency_ms: float
    p99_inference_latency_ms: float
    fleet_health_summary: Dict[str, Any]
    system_status: str


# ---------------------------------------------------------------------------
# 9. Ad-Hoc Inference Request Schema
# ---------------------------------------------------------------------------
class InferenceRequest(BaseModel):
    timestamp: Optional[Union[datetime, str]] = None
    station_id: str = "AWS-001"
    temperature: float = Field(..., ge=-100.0, le=100.0)
    pressure: float = Field(..., ge=100.0, le=1500.0)
    humidity: float = Field(..., ge=-20.0, le=150.0)
    persist: bool = False
