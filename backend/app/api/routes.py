"""
backend/app/api/routes.py
SkyGuard AI — REST API Endpoints for Stations, Observations, Anomalies, Health, Simulation & Data Upload.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.database import get_db
from backend.app.db.repositories import (
    AnomalyRepository,
    HealthRepository,
    ObservationRepository,
    StationRepository,
)
from backend.app.schemas.schemas import (
    AnomalyEventDetailResponse,
    AnomalyEventListResponse,
    AnomalyEventResponse,
    AnomalyInjectRequest,
    AnomalyInjectResponse,
    AnomalyStatsResponse,
    FleetHealthSummaryResponse,
    InferenceRequest,
    InferenceResultSchema,
    ObservationCreate,
    ObservationIngestResponse,
    ObservationListResponse,
    ObservationResponse,
    SimulationStartRequest,
    SimulationStatusResponse,
    StationCreate,
    StationDetailResponse,
    StationListResponse,
    StationResponse,
    StationUpdate,
    StationHealthDetailResponse,
    UploadSummaryResponse,
    MetricsResponse,
)
from backend.app.services.analytics_service import analytics_service
from backend.app.services.ingestion_service import ingestion_service
from backend.app.services.simulation_service import simulation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


# ---------------------------------------------------------------------------
# 1. Station Endpoints
# ---------------------------------------------------------------------------
@router.get("/stations", response_model=StationListResponse, summary="List all registered AWS stations")
async def list_stations(
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE, DEGRADED, CRITICAL, OFFLINE"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    repo = StationRepository(db)
    health_repo = HealthRepository(db)

    stations = await repo.get_all(skip=offset, limit=limit, status=status)
    total = await repo.count(status=status)

    items: List[StationResponse] = []
    for s in stations:
        latest_h = await health_repo.get_latest(s.station_id)
        items.append(
            StationResponse(
                id=s.id,
                station_id=s.station_id,
                name=s.name,
                latitude=s.latitude,
                longitude=s.longitude,
                elevation=s.elevation,
                status=s.status,
                health_score=latest_h.health_score if latest_h else 100.0,
                health_status=latest_h.health_status if latest_h else "EXCELLENT",
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
        )

    return StationListResponse(items=items, total=total)


@router.post("/stations", response_model=StationResponse, status_code=status.HTTP_201_CREATED, summary="Register a new AWS station")
async def create_station(
    station_in: StationCreate,
    db: AsyncSession = Depends(get_db),
):
    repo = StationRepository(db)
    existing = await repo.get_by_id(station_in.station_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Station with ID '{station_in.station_id}' already exists.",
        )

    station = await repo.create(station_in.model_dump())
    return StationResponse(
        id=station.id,
        station_id=station.station_id,
        name=station.name,
        latitude=station.latitude,
        longitude=station.longitude,
        elevation=station.elevation,
        status=station.status,
        health_score=100.0,
        health_status="EXCELLENT",
        created_at=station.created_at,
        updated_at=station.updated_at,
    )


@router.get("/stations/{station_id}", response_model=StationDetailResponse, summary="Get station details and health")
async def get_station(
    station_id: str,
    db: AsyncSession = Depends(get_db),
):
    repo = StationRepository(db)
    obs_repo = ObservationRepository(db)
    health_repo = HealthRepository(db)
    anomaly_repo = AnomalyRepository(db)

    station = await repo.get_by_id(station_id)
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{station_id}' not found.",
        )

    latest_obs = await obs_repo.get_latest(station_id)
    latest_health = await health_repo.get_latest(station_id)
    recent_anomalies = await anomaly_repo.get_recent(station_id=station_id, limit=50)

    obs_resp = (
        ObservationResponse(
            id=latest_obs.id,
            station_id=latest_obs.station_id,
            timestamp=latest_obs.timestamp,
            temperature=latest_obs.temperature,
            pressure=latest_obs.pressure,
            humidity=latest_obs.humidity,
            validation_status=latest_obs.validation_status,
            created_at=latest_obs.created_at,
        )
        if latest_obs
        else None
    )

    return StationDetailResponse(
        id=station.id,
        station_id=station.station_id,
        name=station.name,
        latitude=station.latitude,
        longitude=station.longitude,
        elevation=station.elevation,
        status=station.status,
        health_score=latest_health.health_score if latest_health else 100.0,
        health_status=latest_health.health_status if latest_health else "EXCELLENT",
        created_at=station.created_at,
        updated_at=station.updated_at,
        latest_observation=obs_resp,
        recent_anomalies_count=len(recent_anomalies),
    )


@router.delete("/stations/{station_id}", summary="Delete an AWS station")
async def delete_station(
    station_id: str,
    db: AsyncSession = Depends(get_db),
):
    repo = StationRepository(db)
    deleted = await repo.delete(station_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{station_id}' not found.",
        )
    return {"message": f"Station '{station_id}' successfully deleted."}


# ---------------------------------------------------------------------------
# 2. Observation Endpoints
# ---------------------------------------------------------------------------
@router.post("/observations", response_model=ObservationIngestResponse, status_code=status.HTTP_201_CREATED, summary="Ingest single AWS observation")
async def ingest_observation(
    obs: ObservationCreate,
):
    try:
        res = await ingestion_service.ingest_observation(
            obs_data=obs.model_dump(),
            save_db=True,
            broadcast=True,
        )
        return res
    except Exception as e:
        logger.error("Observation ingestion failed: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/observations/batch", response_model=List[ObservationIngestResponse], summary="Batch ingest observations")
async def ingest_observations_batch(
    observations: List[ObservationCreate],
):
    try:
        raw_list = [o.model_dump() for o in observations]
        results = await ingestion_service.ingest_batch(raw_list, save_db=True)
        return results
    except Exception as e:
        logger.error("Batch ingestion failed: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/observations", response_model=ObservationListResponse, summary="Query historical observations")
async def get_observations(
    station_id: Optional[str] = Query(None, description="Station identifier"),
    start_time: Optional[str] = Query(None, description="Start ISO timestamp"),
    end_time: Optional[str] = Query(None, description="End ISO timestamp"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    order: str = Query("desc", description="Sort order: asc or desc"),
    db: AsyncSession = Depends(get_db),
):
    repo = ObservationRepository(db)
    items, total = await repo.get_paginated(
        station_id=station_id,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
        order=order,
    )

    resp_items = [
        ObservationResponse(
            id=o.id,
            station_id=o.station_id,
            timestamp=o.timestamp,
            temperature=o.temperature,
            pressure=o.pressure,
            humidity=o.humidity,
            validation_status=o.validation_status,
            created_at=o.created_at,
        )
        for o in items
    ]

    return ObservationListResponse(
        items=resp_items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# 3. Anomaly Event Endpoints
# ---------------------------------------------------------------------------
@router.get("/anomalies", response_model=AnomalyEventListResponse, summary="Query detected anomalies with operational filters")
async def get_anomalies(
    station_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, description="Severity: NONE, LOW, MEDIUM, HIGH, CRITICAL"),
    classification: Optional[str] = Query(None, description="Fault type"),
    is_fault: Optional[bool] = Query(None, description="Filter hardware faults vs genuine weather extremes"),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    limit: Optional[int] = Query(None, description="Compatibility alias for page_size"),
    fleet_balanced: bool = Query(True, description="When true and no station_id is specified, balances results across all stations to ensure fleet-wide visibility"),
    db: AsyncSession = Depends(get_db),
):
    effective_page_size = limit if limit is not None else page_size
    repo = AnomalyRepository(db)
    items, total = await repo.get_paginated(
        station_id=station_id,
        severity=severity,
        classification=classification,
        is_fault_only=is_fault,
        start_time=start_time,
        end_time=end_time,
        min_score=min_score,
        page=page,
        page_size=effective_page_size,
        fleet_balanced=fleet_balanced,
    )

    resp_items = [
        AnomalyEventResponse(
            id=e.id,
            observation_id=e.observation_id,
            station_id=e.station_id,
            timestamp=e.timestamp,
            is_anomaly=e.is_anomaly,
            anomaly_score=e.anomaly_score,
            confidence=e.confidence,
            severity=e.severity,
            anomaly_type=e.anomaly_type,
            classification=e.classification,
            is_fault=e.is_fault,
            reason=e.reason,
            explanation=e.explanation,
            tier_scores=e.tier_scores,
            recommended_action=e.recommended_action,
            raw_values=e.raw_values,
            created_at=e.created_at,
        )
        for e in items
    ]

    return AnomalyEventListResponse(
        items=resp_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/anomalies/alerts/active", response_model=List[AnomalyEventResponse], summary="Get active operational alerts")
async def get_active_alerts(
    station_id: Optional[str] = Query(None),
    min_severity: str = Query("MEDIUM", description="Minimum severity: MEDIUM, HIGH, CRITICAL"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    repo = AnomalyRepository(db)
    alerts = await repo.get_active_alerts(
        station_id=station_id,
        min_severity=min_severity,
        limit=limit,
    )

    return [
        AnomalyEventResponse(
            id=e.id,
            observation_id=e.observation_id,
            station_id=e.station_id,
            timestamp=e.timestamp,
            is_anomaly=e.is_anomaly,
            anomaly_score=e.anomaly_score,
            confidence=e.confidence,
            severity=e.severity,
            anomaly_type=e.anomaly_type,
            classification=e.classification,
            is_fault=e.is_fault,
            reason=e.reason,
            explanation=e.explanation,
            tier_scores=e.tier_scores,
            recommended_action=e.recommended_action,
            raw_values=e.raw_values,
            created_at=e.created_at,
        )
        for e in alerts
    ]


@router.get("/anomalies/stats", response_model=AnomalyStatsResponse, summary="Get anomaly statistics summary")
@router.get("/anomalies/stats/summary", response_model=AnomalyStatsResponse, summary="Get anomaly statistics summary (alias)")
async def get_anomaly_stats(
    station_id: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    repo = AnomalyRepository(db)
    stats = await repo.get_stats(station_id=station_id, hours=hours)
    return AnomalyStatsResponse(**stats)


@router.get("/anomalies/{anomaly_id}", response_model=AnomalyEventDetailResponse, summary="Get anomaly diagnostic detail")
async def get_anomaly_detail(
    anomaly_id: int,
    db: AsyncSession = Depends(get_db),
):
    repo = AnomalyRepository(db)
    obs_repo = ObservationRepository(db)
    station_repo = StationRepository(db)

    event = await repo.get_by_id(anomaly_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anomaly event '{anomaly_id}' not found.",
        )

    obs = await obs_repo.get_by_id(event.observation_id) if event.observation_id else None
    obs_resp = (
        ObservationResponse(
            id=obs.id,
            station_id=obs.station_id,
            timestamp=obs.timestamp,
            temperature=obs.temperature,
            pressure=obs.pressure,
            humidity=obs.humidity,
            validation_status=obs.validation_status,
            created_at=obs.created_at,
        )
        if obs
        else None
    )

    st = await station_repo.get_by_id(event.station_id)
    st_resp = (
        StationResponse(
            id=st.id,
            station_id=st.station_id,
            name=st.name,
            latitude=st.latitude,
            longitude=st.longitude,
            elevation=st.elevation,
            status=st.status,
            created_at=st.created_at,
            updated_at=st.updated_at,
        )
        if st
        else None
    )

    return AnomalyEventDetailResponse(
        id=event.id,
        observation_id=event.observation_id,
        station_id=event.station_id,
        timestamp=event.timestamp,
        is_anomaly=event.is_anomaly,
        anomaly_score=event.anomaly_score,
        confidence=event.confidence,
        severity=event.severity,
        anomaly_type=event.anomaly_type,
        classification=event.classification,
        is_fault=event.is_fault,
        reason=event.reason,
        explanation=event.explanation,
        tier_scores=event.tier_scores,
        recommended_action=event.recommended_action,
        raw_values=event.raw_values,
        created_at=event.created_at,
        observation=obs_resp,
        station=st_resp,
    )


# ---------------------------------------------------------------------------
# 4. Sensor Health Endpoints
# ---------------------------------------------------------------------------
@router.get("/health", response_model=FleetHealthSummaryResponse, summary="Get fleet sensor health overview")
async def get_fleet_health(
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.get_fleet_summary(db)


@router.get("/health/{station_id}", response_model=StationHealthDetailResponse, summary="Get station sensor health details")
async def get_station_health(
    station_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    detail = await analytics_service.get_station_health_detail(db, station_id=station_id, limit=limit)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{station_id}' not found.",
        )
    return detail


# ---------------------------------------------------------------------------
# 5. Live Simulation Controls
# ---------------------------------------------------------------------------
@router.post("/simulate/start", response_model=SimulationStatusResponse, summary="Start background synthetic AWS simulation")
async def start_simulation(
    req: SimulationStartRequest = SimulationStartRequest(),
):
    return await simulation_service.start(
        station_ids=req.station_ids,
        interval_seconds=req.interval_seconds,
        noise_level=req.noise_level,
        scenario=req.scenario,
    )


@router.post("/simulate/stop", response_model=SimulationStatusResponse, summary="Stop background simulation")
async def stop_simulation():
    return await simulation_service.stop()


@router.post("/simulate/inject", response_model=AnomalyInjectResponse, summary="Inject on-the-fly anomaly into simulation")
async def inject_anomaly(
    req: AnomalyInjectRequest,
):
    return await simulation_service.inject_anomaly(req)


@router.get("/simulate/status", response_model=SimulationStatusResponse, summary="Get current simulation status")
async def get_simulation_status():
    return simulation_service.get_status()


# ---------------------------------------------------------------------------
# 6. Batch CSV Upload
# ---------------------------------------------------------------------------
@router.post("/upload", response_model=UploadSummaryResponse, summary="Upload CSV dataset for batch 5-tier inference")
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with timestamp, temperature, pressure, humidity"),
    station_id: Optional[str] = Form(None),
    reset_state: bool = Form(False),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files (.csv) are supported.",
        )

    try:
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        summary = await ingestion_service.process_csv_upload(
            file_content=content,
            filename=file.filename,
            station_id=station_id,
            reset_state=reset_state,
        )
        return summary
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Upload error: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ---------------------------------------------------------------------------
# 7. System Analytics & Performance Metrics
# ---------------------------------------------------------------------------
@router.get("/metrics", response_model=MetricsResponse, summary="Get ML inference metrics and latency percentiles")
async def get_metrics(
    station_id: Optional[str] = Query(None),
    window_hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.get_metrics(db, station_id=station_id, window_hours=window_hours)


# ---------------------------------------------------------------------------
# 8. Ad-Hoc Inference Endpoint
# ---------------------------------------------------------------------------
@router.post("/infer", response_model=InferenceResultSchema, summary="Execute immediate 5-tier ML inference on payload")
async def adhoc_infer(
    req: InferenceRequest,
):
    data = req.model_dump()
    if req.persist:
        res = await ingestion_service.ingest_observation(data, save_db=True, broadcast=False)
        return res.inference
    else:
        # Run inference in worker thread without saving to DB
        inf_res = await asyncio.to_thread(ingestion_service.pipeline.process_observation, data)
        return InferenceResultSchema(
            timestamp=inf_res.timestamp,
            station_id=inf_res.station_id,
            is_anomaly=inf_res.is_anomaly,
            anomaly_score=inf_res.anomaly_score,
            confidence=inf_res.confidence,
            severity=inf_res.severity,
            classification=inf_res.classification,
            is_fault=inf_res.is_fault,
            reason=inf_res.reason,
            explanation=inf_res.explanation.model_dump(),
            tier_scores=inf_res.tier_scores.model_dump(),
            sensor_health=inf_res.sensor_health,
            sensor_status=inf_res.sensor_status,
            recommended_action=inf_res.recommended_action,
            degradation_risk=inf_res.degradation_risk,
            estimated_hours_to_failure=inf_res.estimated_hours_to_failure,
            multivariate_diagnostics=inf_res.multivariate_diagnostics,
            raw_values=inf_res.raw_values,
        )


# ---------------------------------------------------------------------------
# 9. Data Source Management Endpoints
# ---------------------------------------------------------------------------
from backend.app.schemas.canonical import (
    DataSourceListResponse,
    DataSourceSelectRequest,
    DataSourceStatus,
    DataSourceType,
    ExternalSourceConfigRequest,
)
from backend.app.sources.manager import data_source_manager


@router.get("/data-sources", response_model=DataSourceListResponse, summary="List all registered data sources and runtime status")
async def list_data_sources():
    """Retrieves all available telemetry sources (Simulator, Open-Meteo, Physical MQTT) and connection health."""
    return await data_source_manager.list_sources()


@router.get("/data-sources/status", response_model=DataSourceStatus, summary="Get active data source status")
async def get_active_data_source_status():
    """Returns the operational status, packet count, latency, and data age of the currently active source."""
    return await data_source_manager.get_active_status()


@router.post("/data-sources/select", response_model=DataSourceStatus, summary="Switch active telemetry data source")
async def select_data_source(req: DataSourceSelectRequest):
    """Gracefully switches the active telemetry data source without disrupting ML pipelines."""
    try:
        return await data_source_manager.select_source(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error switching data source: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/data-sources/external/configure", response_model=DataSourceStatus, summary="Reconfigure geographic coordinates for Open-Meteo feed")
async def configure_external_weather_source(req: ExternalSourceConfigRequest):
    """Dynamically updates latitude, longitude, and station identity for Open-Meteo live weather queries."""
    try:
        return await data_source_manager.configure_external_source(
            latitude=req.latitude,
            longitude=req.longitude,
            station_id=req.station_id,
            station_name=req.station_name,
        )
    except Exception as e:
        logger.error("Failed to reconfigure external weather source: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/data-sources/external/preview", summary="Live test fetch from Open-Meteo External API")
async def preview_external_weather_feed():
    """Executes an immediate live test query to Open-Meteo API to test connectivity and view current readings."""
    ext_source = data_source_manager.get_source(DataSourceType.EXTERNAL_API)
    if not ext_source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External weather adapter not found.")
    try:
        telemetry = await ext_source.fetch_live_observation()
        return {
            "success": True,
            "provider": "Open-Meteo",
            "telemetry": telemetry.model_dump(),
        }
    except Exception as e:
        logger.error("External weather preview failed: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Open-Meteo fetch failed: {e}")


@router.post("/data-sources/physical/virtual-packet", response_model=InferenceResultSchema, summary="Ingest virtual hardware packet for physical testing")
async def ingest_virtual_physical_packet(payload: Dict[str, Any]):
    """Allows developers and tests to inject a physical ESP32/BME280 formatted packet directly into the pipeline."""
    phy_source = data_source_manager.get_source(DataSourceType.PHYSICAL_AWS)
    if not phy_source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical AWS adapter not found.")
    try:
        canonical = await phy_source.ingest_virtual_packet(payload)
        res = await ingestion_service.ingest_observation(canonical.to_ml_input_dict(), save_db=True, broadcast=True)
        return res.inference
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Virtual physical packet ingestion failed: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

