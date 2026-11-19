"""Orchestration of the Locations feature: create locations, build normals, fetch recent data, score cells."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.locations import anomaly as anom
from backend.app.locations import grid, qc
from backend.app.locations.models import CellNormals, Location, LocationCell, SeriesCache
from backend.app.locations.normals import VARIABLES, NormalsError, build_normals
from backend.app.locations.openmeteo import SOURCE, OpenMeteoClient, OpenMeteoError
from backend.app.locations.scores import ScoreProvider, model_block

logger = logging.getLogger(__name__)
NORMALS_START, NORMALS_END = "1991-01-01", "2020-12-31"
NORMALS_PERIOD = "1991-2020"
FULL_DAY_HOURS = 22                      # a day counts as complete with at least this many hourly values
DEFAULT_RADIUS_KM = 15.0
LIMITATIONS = [
    "Values come from Open-Meteo, which returns model analysis and forecast values at its nearest model grid point (see grid_point), "
    "not station observations and not the mean of the 0.25-degree cell.",
    "Weather anomaly means unusual for this cell and time of year. It does not mean the data is wrong.",
    "The data-QC flag uses rule and statistics checks (qc.method). The trained models of ml-service/qc are not applied yet; see each cell's model block.",
    "A 0.25-degree cell is about 28 km wide: differences inside a city are not resolved.",
]
PRESETS = [{"name": "Mumbai", "latitude": 19.0760, "longitude": 72.8777, "radius_km": 15.0}]


def _safe(v: Any) -> Any:
    """JSON-safe copy: NaN and infinity become None."""
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: _safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in v]
    return v


def _nan_list(xs: List[Any]) -> List[float]:
    return [float("nan") if x is None else float(x) for x in xs]


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class LocationNotFound(LookupError):
    pass


class LocationService:
    def __init__(self, session: AsyncSession, om: Optional[OpenMeteoClient] = None, scores: Optional[ScoreProvider] = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), cache_seconds: float = 600.0) -> None:
        self.db, self.om, self.scores, self.now, self.cache_seconds = session, om or OpenMeteoClient(), scores, now, cache_seconds

    # ------------------------------------------------------------------ locations
    async def create(self, name: str, latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM, preset: bool = False) -> Location:
        cells = grid.cells_for(latitude, longitude, radius_km)            # raises GridError outside the grid or for too large an area
        loc = Location(name=name.strip(), latitude=latitude, longitude=longitude, radius_km=radius_km, preset=preset)
        for r, c in cells:
            d = grid.describe_cell(r, c)
            loc.cells.append(LocationCell(cell_row=r, cell_col=c, lat=d["lat"], lon=d["lon"], is_land=d["is_land"], client=d["client"], held_out=d["held_out"]))
        self.db.add(loc)
        await self.db.flush()
        await self.db.refresh(loc)
        return loc

    async def create_from_name(self, name: str, radius_km: float = DEFAULT_RADIUS_KM) -> Location:
        found = await self.om.geocode(name)
        if not found:
            raise LocationNotFound(f"no place called '{name}' was found")
        first = found[0]
        label = ", ".join(x for x in (first["name"], first.get("admin1"), first.get("country")) if x)
        return await self.create(label, first["latitude"], first["longitude"], radius_km)

    async def list(self) -> List[Location]:
        return list((await self.db.execute(select(Location).order_by(Location.id))).scalars().all())

    async def get(self, location_id: int) -> Location:
        loc = await self.db.get(Location, location_id)
        if loc is None:
            raise LocationNotFound(f"location {location_id} not found")
        return loc

    async def delete(self, location_id: int) -> None:
        loc = await self.get(location_id)
        await self.db.delete(loc)
        await self.db.flush()

    async def ensure_presets(self) -> None:
        """Seed Mumbai when there are no locations at all (needs no network)."""
        n = (await self.db.execute(select(func.count()).select_from(Location))).scalar_one()
        if n == 0:
            for p in PRESETS:
                await self.create(p["name"], p["latitude"], p["longitude"], p["radius_km"], preset=True)

    # ------------------------------------------------------------------ normals
    async def ensure_normals(self, cells: List[LocationCell]) -> Tuple[Dict[Tuple[int, int], Dict[str, Any]], Dict[Tuple[int, int], str]]:
        have: Dict[Tuple[int, int], Dict[str, Any]] = {}
        errors: Dict[Tuple[int, int], str] = {}
        missing: List[LocationCell] = []
        for c in cells:
            row = await self.db.get(CellNormals, (c.cell_row, c.cell_col))
            if row is not None:
                have[(c.cell_row, c.cell_col)] = row.data
            else:
                missing.append(c)
        if missing:
            try:
                hist = await self.om.history([(c.lat, c.lon) for c in missing], NORMALS_START, NORMALS_END)
            except OpenMeteoError as e:
                return have, {(c.cell_row, c.cell_col): f"history could not be fetched: {e}" for c in missing}
            for c, h in zip(missing, hist):
                key = (c.cell_row, c.cell_col)
                try:
                    data = _safe(build_normals(h))
                except NormalsError as e:
                    errors[key] = str(e)
                    continue
                self.db.add(CellNormals(cell_row=c.cell_row, cell_col=c.cell_col, source=SOURCE, period=NORMALS_PERIOD,
                                        grid_lat=h["grid_point"]["lat"], grid_lon=h["grid_point"]["lon"], data=data))
                have[key] = data
            await self.db.flush()
        return have, errors

    # ------------------------------------------------------------------ recent data
    async def _recent(self, loc: Location) -> Tuple[Dict[str, Any], bool]:
        """(payload, stale). payload: {"fetched_at", "cells": {"row_col": {grid_point, time, temperature, ...}}} with None for gaps."""
        row = await self.db.get(SeriesCache, loc.id)
        now = self.now()
        if row is not None and (now - _utc(row.fetched_at)).total_seconds() < self.cache_seconds:
            return row.payload, False
        try:
            got = await self.om.recent([(c.lat, c.lon) for c in loc.cells], past_days=7, now=now)
        except OpenMeteoError:
            if row is not None:
                return row.payload, True                         # keep showing the last good data, marked stale
            raise
        payload = _safe({"fetched_at": now.isoformat(), "cells": {f"{c.cell_row}_{c.cell_col}": g for c, g in zip(loc.cells, got)}})
        if row is None:
            self.db.add(SeriesCache(location_id=loc.id, fetched_at=now, payload=payload))
        else:
            row.fetched_at, row.payload = now, payload
        await self.db.flush()
        return payload, False

    @staticmethod
    def _daily(series: Dict[str, Any]) -> Dict[date, Dict[str, float]]:
        """Daily aggregates (UTC) of the days that have at least FULL_DAY_HOURS hourly values."""
        by: Dict[date, Dict[str, List[float]]] = {}
        for i, t in enumerate(series["time"]):
            d = datetime.fromisoformat(t).date()
            slot = by.setdefault(d, {v: [] for v in (*VARIABLES, "precipitation")})
            for v in slot:
                x = series[v][i]
                if x is not None and math.isfinite(x):
                    slot[v].append(x)
        out: Dict[date, Dict[str, float]] = {}
        for d, slot in by.items():
            day: Dict[str, float] = {}
            for v in VARIABLES:
                if len(slot[v]) >= FULL_DAY_HOURS:
                    day[v] = sum(slot[v]) / len(slot[v])
            if len(slot["precipitation"]) >= FULL_DAY_HOURS:
                day["precipitation"] = sum(slot["precipitation"])
            out[d] = day
        return out

    # ------------------------------------------------------------------ status
    async def status(self, location_id: int) -> Dict[str, Any]:
        loc = await self.get(location_id)
        payload, stale = await self._recent(loc)
        normals, normal_errors = await self.ensure_normals(list(loc.cells))
        today = self.now().date()
        cells_out: List[Dict[str, Any]] = []
        z_by_cell: Dict[str, Dict[str, Optional[float]]] = {}
        parts: Dict[str, Dict[str, Any]] = {}
        for c in loc.cells:
            key = f"{c.cell_row}_{c.cell_col}"
            s = payload["cells"].get(key)
            info = {"id": c.id, "row": c.cell_row, "col": c.cell_col, "lat": c.lat, "lon": c.lon, "is_land": c.is_land,
                    "client": c.client, "held_out": c.held_out}
            if s is None or not s["time"]:
                parts[key] = {"info": info, "error": "no data returned for this cell"}
                continue
            daily = self._daily(s)
            full_days = sorted(d for d in daily if d < today and daily[d])
            a_day = full_days[-1] if full_days else None
            n = normals.get((c.cell_row, c.cell_col))
            weather: Dict[str, Any]
            if a_day is None:
                weather = {"status": "unavailable", "reason": "no complete UTC day in the recent series"}
            elif n is None:
                weather = {"status": "unavailable", "reason": normal_errors.get((c.cell_row, c.cell_col), "normals not built")}
            else:
                weather = {"status": "ok", "date": a_day.isoformat(), "normals_period": NORMALS_PERIOD, **anom.weather_anomaly(daily[a_day], n, a_day)}
            findings = {v: qc.check_series(v, s[v], s["time"]) for v in VARIABLES}
            last = max((i for i in range(len(s["time"])) if all(s[v][i] is not None for v in VARIABLES)), default=None)
            current = None if last is None else {"time": s["time"][last], **{v: s[v][last] for v in VARIABLES},
                                                 "precipitation_1h": s["precipitation"][last]}
            z_by_cell[key] = {v: (weather[v].get("z") if weather.get("status") == "ok" else None) for v in VARIABLES}
            parts[key] = {"info": info, "grid_point": s["grid_point"], "current": current, "weather": weather,
                          "findings": findings, "anomaly_date": a_day}
        buddies = qc.buddy_check(z_by_cell)
        for key, p in parts.items():
            if "error" in p:
                cells_out.append({"cell": p["info"], "status": f"error: {p['error']}"})
                continue
            hard = [dict(f, variable=v) for v, fs in p["findings"].items() for f in fs]
            ok_weather = p["weather"].get("status") == "ok"
            strength = anom.anomaly_strength(p["weather"]) if ok_weather else 0
            others = [q for k, q in parts.items() if k != key and "error" not in q and q["weather"].get("status") == "ok"]
            coherent = sum(1 for q in others if anom.anomaly_strength(q["weather"]) >= 1)
            label = qc.classify(strength, hard, buddies.get(key, []), coherent, len(others))
            cells_out.append({
                "cell": p["info"], "status": "ok", "grid_point": p["grid_point"], "current": p["current"], "weather_anomaly": p["weather"],
                "qc": {"method": qc.METHOD, "findings": hard, "neighbour_findings": buddies.get(key, [])},
                "classification": label, "model": model_block(self.scores, p["info"]["row"], p["info"]["col"], p["anomaly_date"]),
            })
        counts: Dict[str, int] = {}
        for c in cells_out:
            lab = c.get("classification", {}).get("label", "error")
            counts[lab] = counts.get(lab, 0) + 1
        return {"location": {"id": loc.id, "name": loc.name, "latitude": loc.latitude, "longitude": loc.longitude, "radius_km": loc.radius_km,
                             "preset": loc.preset, "n_cells": len(loc.cells)},
                "as_of": payload["fetched_at"], "stale": stale,
                "source": {"provider": SOURCE, "kind": "model analysis and forecast values at the nearest model grid point; not station observations"},
                "summary": counts, "cells": _safe(cells_out), "limitations": LIMITATIONS}

    async def series(self, location_id: int, days: int = 7) -> Dict[str, Any]:
        loc = await self.get(location_id)
        payload, stale = await self._recent(loc)
        cutoff = (self.now() - timedelta(days=days)).replace(tzinfo=None).isoformat(timespec="minutes")
        out = []
        for c in loc.cells:
            s = payload["cells"].get(f"{c.cell_row}_{c.cell_col}")
            if s is None:
                out.append({"cell": {"row": c.cell_row, "col": c.cell_col}, "time": []})
                continue
            keep = [i for i, t in enumerate(s["time"]) if t >= cutoff]
            out.append({"cell": {"row": c.cell_row, "col": c.cell_col, "lat": c.lat, "lon": c.lon}, "grid_point": s["grid_point"],
                        "time": [s["time"][i] for i in keep], **{v: [s[v][i] for i in keep] for v in (*VARIABLES, "precipitation")}})
        normals, _ = await self.ensure_normals(list(loc.cells))
        norm_out = {}
        for c in loc.cells:
            n = normals.get((c.cell_row, c.cell_col))
            if n:
                d = self.now().date()
                i = min(d.timetuple().tm_yday - 1, 365)
                norm_out[f"{c.cell_row}_{c.cell_col}"] = {v: {"mean": n[v]["mean"][i], "sd": n[v]["sd"][i]} for v in VARIABLES}
        return {"location_id": loc.id, "as_of": payload["fetched_at"], "stale": stale, "cells": _safe(out), "normals_today": norm_out}
