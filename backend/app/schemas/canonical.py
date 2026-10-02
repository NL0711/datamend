"""
backend/app/schemas/canonical.py
SkyGuard AI — Canonical Telemetry Schema & Data Source Status Contract.
Provides a provider-agnostic normalized interface for all incoming weather telemetry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DataSourceType(str, Enum):
    """Normalized classification of telemetry origin."""
    SIMULATED = "SIMULATED"
    EXTERNAL_API = "EXTERNAL_API"
    PHYSICAL_AWS = "PHYSICAL_AWS"


class SourceConnectionStatus(str, Enum):
    """Operational connection states for data sources."""
    CONNECTED = "CONNECTED"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class CanonicalTelemetry(BaseModel):
    """
    Canonical Telemetry Contract for SkyGuard AI.
    All data sources (Simulator, External API, Physical ESP32) MUST normalize into this schema
    before passing into the 5-Tier ML Quality Control and Anomaly Pipeline.
    """
    station_id: str = Field(..., min_length=1, max_length=64, description="AWS station identifier (e.g. AWS-001, PUNE-EXT-001)")
    timestamp: str = Field(..., description="Observation timestamp in ISO 8601 UTC string")
    temperature: float = Field(..., ge=-100.0, le=100.0, description="Temperature in Celsius (°C)")
    pressure: float = Field(..., ge=100.0, le=1500.0, description="Atmospheric pressure in hPa")
    humidity: float = Field(..., ge=-20.0, le=150.0, description="Relative humidity in percentage (%)")
    
    # Provenance & Source Metadata
    source_type: DataSourceType = Field(DataSourceType.SIMULATED, description="Origin classification")
    source_id: str = Field("diurnal_generator", description="Specific source adapter ID (e.g. open_meteo, esp32_bme280)")
    provider: Optional[str] = Field(None, description="External provider or manufacturer name (e.g. Open-Meteo, Adafruit)")
    device_id: Optional[str] = Field(None, description="Physical hardware identifier or MAC address")
    
    # Location Metadata
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    elevation: Optional[float] = Field(None, ge=-500.0, le=9000.0, description="Elevation in meters")
    
    # Transport & Integrity Metadata
    unit_system: str = Field("metric", description="Unit system (always metric internally)")
    sequence_number: Optional[int] = Field(None, description="Sequence counter from hardware or stream")
    received_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="UTC timestamp when received by backend")
    data_quality: str = Field("GOOD", description="Initial ingestion quality assessment (GOOD, SUSPECT, INVALID)")
    connectivity_status: SourceConnectionStatus = Field(SourceConnectionStatus.CONNECTED, description="Source connection health")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Original unparsed payload fields")

    model_config = ConfigDict(from_attributes=True)

    def to_ml_input_dict(self) -> Dict[str, Any]:
        """Converts canonical telemetry into dictionary format expected by SkyGuardPipeline."""
        return {
            "station_id": self.station_id,
            "timestamp": self.timestamp,
            "temperature": self.temperature,
            "pressure": self.pressure,
            "humidity": self.humidity,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation": self.elevation,
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "provider": self.provider,
            "device_id": self.device_id,
        }


class DataSourceStatus(BaseModel):
    """Runtime health and configuration state for a telemetry source."""
    source_type: DataSourceType
    source_id: str
    name: str
    description: str
    status: SourceConnectionStatus
    is_active: bool = False
    is_available: bool = True
    station_id: str
    provider: Optional[str] = None
    last_received_at: Optional[str] = None
    last_successful_fetch: Optional[str] = None
    last_error_at: Optional[str] = None
    error_message: Optional[str] = None
    data_age_seconds: Optional[float] = None
    is_stale: bool = False
    packet_count: int = 0
    polling_interval_seconds: Optional[float] = None
    coordinates: Optional[Dict[str, float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class DataSourceSelectRequest(BaseModel):
    """Request payload to switch the active telemetry data source."""
    source_type: DataSourceType = Field(..., description="Target data source type to activate")
    source_id: Optional[str] = Field(None, description="Optional specific adapter ID")
    station_id: Optional[str] = Field(None, description="Optional station ID to target")


class ExternalSourceConfigRequest(BaseModel):
    """Request payload to configure geographic coordinates for Open-Meteo external feed."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Geographic latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Geographic longitude")
    station_id: Optional[str] = Field(None, description="Optional custom station identifier")
    station_name: Optional[str] = Field(None, description="Optional human-readable station name / city")


class DataSourceListResponse(BaseModel):
    """List of all registered telemetry data sources with runtime statuses."""
    active_source: DataSourceType
    active_source_id: str
    sources: List[DataSourceStatus]
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
