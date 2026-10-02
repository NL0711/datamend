"""
backend/app/db/repositories.py
SkyGuard AI — Async Repository Pattern Implementations for Clean Data Access.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    AnomalyEvent,
    ModelRun,
    Observation,
    SensorHealth,
    Station,
    utcnow,
)


def parse_datetime(dt: Union[datetime, str, None]) -> Optional[datetime]:
    """Helper to safely parse ISO strings or datetime objects to timezone-aware UTC datetime."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    try:
        clean_str = str(dt).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(clean_str)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. Station Repository
# ---------------------------------------------------------------------------
class StationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, station_data: Dict[str, Any]) -> Station:
        station = Station(**station_data)
        self.session.add(station)
        await self.session.flush()
        return station

    async def get_by_id(self, station_id: str) -> Optional[Station]:
        stmt = select(Station).where(Station.station_id == station_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all(
        self, skip: int = 0, limit: int = 100, status: Optional[str] = None
    ) -> List[Station]:
        stmt = select(Station)
        if status:
            stmt = stmt.where(Station.status == status.upper())
        stmt = stmt.offset(skip).limit(limit).order_by(Station.station_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create(
        self,
        station_id: str,
        name: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        elevation: Optional[float] = None,
    ) -> Station:
        station = await self.get_by_id(station_id)
        if station:
            return station
        station = Station(
            station_id=station_id,
            name=name or f"Station {station_id}",
            latitude=latitude if latitude is not None else 28.6139,
            longitude=longitude if longitude is not None else 77.2090,
            elevation=elevation if elevation is not None else 216.0,
            status="ACTIVE",
        )
        self.session.add(station)
        await self.session.flush()
        return station

    async def update_status(self, station_id: str, status: str) -> Optional[Station]:
        stmt = (
            update(Station)
            .where(Station.station_id == station_id)
            .values(status=status.upper(), updated_at=utcnow())
            .returning(Station)
        )
        result = await self.session.execute(stmt)
        updated = result.scalars().first()
        await self.session.flush()
        return updated

    async def delete(self, station_id: str) -> bool:
        stmt = delete(Station).where(Station.station_id == station_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return (result.rowcount or 0) > 0

    async def count(self, status: Optional[str] = None) -> int:
        stmt = select(func.count(Station.id))
        if status:
            stmt = stmt.where(Station.status == status.upper())
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_fleet_summary(self) -> Dict[str, Any]:
        total = await self.count()
        active = await self.count(status="ACTIVE")
        degraded = await self.count(status="DEGRADED")
        critical = await self.count(status="CRITICAL")
        offline = await self.count(status="OFFLINE")
        return {
            "total_stations": total,
            "active_stations": active,
            "degraded_stations": degraded,
            "critical_stations": critical,
            "offline_stations": offline,
        }


# ---------------------------------------------------------------------------
# 2. Observation Repository
# ---------------------------------------------------------------------------
class ObservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, obs_data: Dict[str, Any]) -> Observation:
        data = dict(obs_data)
        if "timestamp" in data:
            data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
        obs = Observation(**data)
        self.session.add(obs)
        await self.session.flush()
        return obs

    async def create_batch(self, obs_list: List[Dict[str, Any]]) -> List[Observation]:
        records: List[Observation] = []
        for item in obs_list:
            data = dict(item)
            if "timestamp" in data:
                data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
            records.append(Observation(**data))
        self.session.add_all(records)
        await self.session.flush()
        return records

    async def get_by_id(self, obs_id: int) -> Optional[Observation]:
        stmt = select(Observation).where(Observation.id == obs_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest(self, station_id: str) -> Optional[Observation]:
        stmt = (
            select(Observation)
            .where(Observation.station_id == station_id)
            .order_by(desc(Observation.timestamp))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_history(
        self,
        station_id: str,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        limit: int = 288,
        sort_desc: bool = True,
    ) -> List[Observation]:
        stmt = select(Observation).where(Observation.station_id == station_id)
        dt_start = parse_datetime(start_time)
        dt_end = parse_datetime(end_time)
        if dt_start:
            stmt = stmt.where(Observation.timestamp >= dt_start)
        if dt_end:
            stmt = stmt.where(Observation.timestamp <= dt_end)
        
        if sort_desc:
            stmt = stmt.order_by(desc(Observation.timestamp))
        else:
            stmt = stmt.order_by(Observation.timestamp)
            
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_window(self, station_id: str, window_size: int = 30) -> List[Observation]:
        """Fetches the last N observations in ascending chronological order for ML window buffering."""
        subq = (
            select(Observation)
            .where(Observation.station_id == station_id)
            .order_by(desc(Observation.timestamp))
            .limit(window_size)
            .subquery()
        )
        stmt = select(Observation).from_statement(
            select(subq).order_by(subq.c.timestamp)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_paginated(
        self,
        station_id: Optional[str] = None,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        page: int = 1,
        page_size: int = 50,
        order: str = "desc",
    ) -> Tuple[List[Observation], int]:
        stmt = select(Observation)
        count_stmt = select(func.count(Observation.id))

        if station_id:
            stmt = stmt.where(Observation.station_id == station_id)
            count_stmt = count_stmt.where(Observation.station_id == station_id)
        
        dt_start = parse_datetime(start_time)
        dt_end = parse_datetime(end_time)
        if dt_start:
            stmt = stmt.where(Observation.timestamp >= dt_start)
            count_stmt = count_stmt.where(Observation.timestamp >= dt_start)
        if dt_end:
            stmt = stmt.where(Observation.timestamp <= dt_end)
            count_stmt = count_stmt.where(Observation.timestamp <= dt_end)

        total_count = (await self.session.execute(count_stmt)).scalar() or 0
        
        offset = max(0, (page - 1) * page_size)
        if order.lower() == "asc":
            stmt = stmt.order_by(Observation.timestamp).offset(offset).limit(page_size)
        else:
            stmt = stmt.order_by(desc(Observation.timestamp)).offset(offset).limit(page_size)
            
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def count(self, station_id: Optional[str] = None) -> int:
        stmt = select(func.count(Observation.id))
        if station_id:
            stmt = stmt.where(Observation.station_id == station_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0


# ---------------------------------------------------------------------------
# 3. Anomaly Repository
# ---------------------------------------------------------------------------
class AnomalyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event_data: Dict[str, Any]) -> AnomalyEvent:
        data = dict(event_data)
        if "timestamp" in data:
            data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
        event = AnomalyEvent(**data)
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_batch(self, events_list: List[Dict[str, Any]]) -> List[AnomalyEvent]:
        records: List[AnomalyEvent] = []
        for item in events_list:
            data = dict(item)
            if "timestamp" in data:
                data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
            records.append(AnomalyEvent(**data))
        self.session.add_all(records)
        await self.session.flush()
        return records

    async def get_by_id(self, event_id: int) -> Optional[AnomalyEvent]:
        stmt = select(AnomalyEvent).where(AnomalyEvent.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_recent(
        self,
        station_id: Optional[str] = None,
        severity: Optional[str] = None,
        classification: Optional[str] = None,
        is_fault_only: Optional[bool] = None,
        min_score: float = 0.0,
        limit: int = 50,
    ) -> List[AnomalyEvent]:
        stmt = select(AnomalyEvent)
        if station_id:
            stmt = stmt.where(AnomalyEvent.station_id == station_id)
        if severity:
            stmt = stmt.where(AnomalyEvent.severity == severity.upper())
        if classification:
            stmt = stmt.where(AnomalyEvent.classification == classification.upper())
        if is_fault_only is not None:
            stmt = stmt.where(AnomalyEvent.is_fault == is_fault_only)
        if min_score > 0.0:
            stmt = stmt.where(AnomalyEvent.anomaly_score >= min_score)
        
        stmt = stmt.order_by(desc(AnomalyEvent.timestamp)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_paginated(
        self,
        station_id: Optional[str] = None,
        severity: Optional[str] = None,
        classification: Optional[str] = None,
        is_fault_only: Optional[bool] = None,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        min_score: float = 0.0,
        page: int = 1,
        page_size: int = 50,
        fleet_balanced: bool = False,
    ) -> Tuple[List[AnomalyEvent], int]:
        stmt = select(AnomalyEvent)
        count_stmt = select(func.count(AnomalyEvent.id))

        if station_id:
            stmt = stmt.where(AnomalyEvent.station_id == station_id)
            count_stmt = count_stmt.where(AnomalyEvent.station_id == station_id)
        if severity:
            stmt = stmt.where(AnomalyEvent.severity == severity.upper())
            count_stmt = count_stmt.where(AnomalyEvent.severity == severity.upper())
        if classification:
            stmt = stmt.where(AnomalyEvent.classification == classification.upper())
            count_stmt = count_stmt.where(AnomalyEvent.classification == classification.upper())
        if is_fault_only is not None:
            stmt = stmt.where(AnomalyEvent.is_fault == is_fault_only)
            count_stmt = count_stmt.where(AnomalyEvent.is_fault == is_fault_only)
        if min_score > 0.0:
            stmt = stmt.where(AnomalyEvent.anomaly_score >= min_score)
            count_stmt = count_stmt.where(AnomalyEvent.anomaly_score >= min_score)

        dt_start = parse_datetime(start_time)
        dt_end = parse_datetime(end_time)
        if dt_start:
            stmt = stmt.where(AnomalyEvent.timestamp >= dt_start)
            count_stmt = count_stmt.where(AnomalyEvent.timestamp >= dt_start)
        if dt_end:
            stmt = stmt.where(AnomalyEvent.timestamp <= dt_end)
            count_stmt = count_stmt.where(AnomalyEvent.timestamp <= dt_end)

        total_count = (await self.session.execute(count_stmt)).scalar() or 0

        # Fleet-balanced multi-station retrieval when querying all stations
        if fleet_balanced and not station_id:
            # Query distinct active station IDs
            stations_stmt = select(AnomalyEvent.station_id).distinct()
            if severity:
                stations_stmt = stations_stmt.where(AnomalyEvent.severity == severity.upper())
            if classification:
                stations_stmt = stations_stmt.where(AnomalyEvent.classification == classification.upper())
            if is_fault_only is not None:
                stations_stmt = stations_stmt.where(AnomalyEvent.is_fault == is_fault_only)
            if min_score > 0.0:
                stations_stmt = stations_stmt.where(AnomalyEvent.anomaly_score >= min_score)

            distinct_stations = (await self.session.execute(stations_stmt)).scalars().all()
            if distinct_stations:
                per_station_limit = max(5, page_size // len(distinct_stations))
                balanced_events: List[AnomalyEvent] = []
                for s in distinct_stations:
                    sub_stmt = select(AnomalyEvent).where(AnomalyEvent.station_id == s)
                    if severity:
                        sub_stmt = sub_stmt.where(AnomalyEvent.severity == severity.upper())
                    if classification:
                        sub_stmt = sub_stmt.where(AnomalyEvent.classification == classification.upper())
                    if is_fault_only is not None:
                        sub_stmt = sub_stmt.where(AnomalyEvent.is_fault == is_fault_only)
                    if min_score > 0.0:
                        sub_stmt = sub_stmt.where(AnomalyEvent.anomaly_score >= min_score)
                    if dt_start:
                        sub_stmt = sub_stmt.where(AnomalyEvent.timestamp >= dt_start)
                    if dt_end:
                        sub_stmt = sub_stmt.where(AnomalyEvent.timestamp <= dt_end)

                    sub_stmt = sub_stmt.order_by(desc(AnomalyEvent.timestamp)).limit(per_station_limit)
                    s_res = (await self.session.execute(sub_stmt)).scalars().all()
                    balanced_events.extend(s_res)

                balanced_events.sort(key=lambda e: e.timestamp or datetime.min, reverse=True)
                return balanced_events[:page_size], total_count

        offset = max(0, (page - 1) * page_size)
        stmt = stmt.order_by(desc(AnomalyEvent.timestamp)).offset(offset).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def get_active_alerts(
        self,
        station_id: Optional[str] = None,
        min_severity: str = "MEDIUM",
        limit: int = 20,
    ) -> List[AnomalyEvent]:
        severity_order = ["MEDIUM", "HIGH", "CRITICAL"] if min_severity.upper() == "MEDIUM" else ["HIGH", "CRITICAL"]
        stmt = select(AnomalyEvent).where(AnomalyEvent.severity.in_(severity_order))
        if station_id:
            stmt = stmt.where(AnomalyEvent.station_id == station_id)
        stmt = stmt.order_by(desc(AnomalyEvent.timestamp)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(
        self, station_id: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        since = utcnow() - timedelta(hours=hours)
        base_filter = [AnomalyEvent.timestamp >= since]
        if station_id:
            base_filter.append(AnomalyEvent.station_id == station_id)

        # Total anomalies
        tot_stmt = select(func.count(AnomalyEvent.id)).where(*base_filter)
        total_anomalies = (await self.session.execute(tot_stmt)).scalar() or 0

        # By severity
        sev_stmt = (
            select(AnomalyEvent.severity, func.count(AnomalyEvent.id))
            .where(*base_filter)
            .group_by(AnomalyEvent.severity)
        )
        sev_res = await self.session.execute(sev_stmt)
        by_severity = {row[0]: row[1] for row in sev_res.all()}

        # By classification
        clf_stmt = (
            select(AnomalyEvent.classification, func.count(AnomalyEvent.id))
            .where(*base_filter)
            .group_by(AnomalyEvent.classification)
        )
        clf_res = await self.session.execute(clf_stmt)
        by_classification = {row[0]: row[1] for row in clf_res.all()}

        # Faults vs Meteorological Extreme
        faults_stmt = (
            select(AnomalyEvent.is_fault, func.count(AnomalyEvent.id))
            .where(*base_filter)
            .group_by(AnomalyEvent.is_fault)
        )
        faults_res = await self.session.execute(faults_stmt)
        fault_counts = {row[0]: row[1] for row in faults_res.all()}

        return {
            "period_hours": hours,
            "total_anomalies": total_anomalies,
            "by_severity": by_severity,
            "by_classification": by_classification,
            "sensor_faults": fault_counts.get(True, 0),
            "meteorological_extremes": fault_counts.get(False, 0),
        }


# ---------------------------------------------------------------------------
# 4. Health Repository
# ---------------------------------------------------------------------------
class HealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, health_data: Dict[str, Any]) -> SensorHealth:
        data = dict(health_data)
        if "timestamp" in data:
            data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
        record = SensorHealth(**data)
        self.session.add(record)
        await self.session.flush()
        return record

    async def create_batch(self, health_list: List[Dict[str, Any]]) -> List[SensorHealth]:
        records: List[SensorHealth] = []
        for item in health_list:
            data = dict(item)
            if "timestamp" in data:
                data["timestamp"] = parse_datetime(data["timestamp"]) or utcnow()
            records.append(SensorHealth(**data))
        self.session.add_all(records)
        await self.session.flush()
        return records

    async def get_latest(self, station_id: str) -> Optional[SensorHealth]:
        stmt = (
            select(SensorHealth)
            .where(SensorHealth.station_id == station_id)
            .order_by(desc(SensorHealth.timestamp))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_latest(self) -> List[SensorHealth]:
        """Fetches the latest health record for each registered station."""
        subq = (
            select(
                SensorHealth.station_id,
                func.max(SensorHealth.timestamp).label("max_ts"),
            )
            .group_by(SensorHealth.station_id)
            .subquery()
        )
        stmt = select(SensorHealth).join(
            subq,
            (SensorHealth.station_id == subq.c.station_id)
            & (SensorHealth.timestamp == subq.c.max_ts),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_history(
        self,
        station_id: str,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        limit: int = 288,
    ) -> List[SensorHealth]:
        stmt = select(SensorHealth).where(SensorHealth.station_id == station_id)
        dt_start = parse_datetime(start_time)
        dt_end = parse_datetime(end_time)
        if dt_start:
            stmt = stmt.where(SensorHealth.timestamp >= dt_start)
        if dt_end:
            stmt = stmt.where(SensorHealth.timestamp <= dt_end)
        stmt = stmt.order_by(desc(SensorHealth.timestamp)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_fleet_health_summary(self) -> Dict[str, Any]:
        latest_records = await self.get_all_latest()
        if not latest_records:
            return {
                "average_health_score": 100.0,
                "status_distribution": {
                    "EXCELLENT": 0, "GOOD": 0, "DEGRADED": 0, "POOR": 0, "CRITICAL": 0
                },
                "station_count": 0,
            }
        scores = [r.health_score for r in latest_records]
        avg_score = round(sum(scores) / len(scores), 2)
        dist: Dict[str, int] = {
            "EXCELLENT": 0, "GOOD": 0, "DEGRADED": 0, "POOR": 0, "CRITICAL": 0
        }
        for r in latest_records:
            st = r.health_status.upper() if r.health_status else "EXCELLENT"
            dist[st] = dist.get(st, 0) + 1
        return {
            "average_health_score": avg_score,
            "status_distribution": dist,
            "station_count": len(latest_records),
        }


# ---------------------------------------------------------------------------
# 5. Model Run Repository
# ---------------------------------------------------------------------------
class ModelRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, run_data: Dict[str, Any]) -> ModelRun:
        run = ModelRun(**run_data)
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_by_id(self, run_id: int) -> Optional[ModelRun]:
        stmt = select(ModelRun).where(ModelRun.id == run_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest(self, model_name: Optional[str] = None) -> Optional[ModelRun]:
        stmt = select(ModelRun)
        if model_name:
            stmt = stmt.where(ModelRun.model_name == model_name)
        stmt = stmt.order_by(desc(ModelRun.created_at)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all(self, limit: int = 50) -> List[ModelRun]:
        stmt = select(ModelRun).order_by(desc(ModelRun.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_metrics(self, run_id: int, metrics: Dict[str, Any]) -> Optional[ModelRun]:
        stmt = (
            update(ModelRun)
            .where(ModelRun.id == run_id)
            .values(metrics=metrics)
            .returning(ModelRun)
        )
        result = await self.session.execute(stmt)
        updated = result.scalars().first()
        await self.session.flush()
        return updated
