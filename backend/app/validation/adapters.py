"""Adapters from other sources to the internal Reading record. The ISD replay adapter is NOT IMPLEMENTED in this slice."""
from __future__ import annotations

from typing import Optional

from backend.app.rainfall.weather_union import RainObservation
from backend.app.validation.records import Reading


def reading_from_observation(obs: RainObservation, accumulation_mode: str, seq: int,
                             latitude: Optional[float] = None, longitude: Optional[float] = None) -> Reading:
    """A Weather Union poll as a Reading. The API gives no observation time, so the time is the time of receipt (time_basis
    'received', which makes gap checks weaker); units and period are unconfirmed, so mm is ASSUMED (units_confirmed False).
    A NO_RAIN_FIELDS or API_ERROR poll keeps both values None; nothing is invented."""
    return Reading(
        source="weather_union", station_id=obs.station_id, timestamp=obs.observed_at, accumulation=obs.rain_accumulation,
        intensity=obs.rain_intensity, time_basis="received",
        accumulation_mode=accumulation_mode if obs.rain_accumulation is not None else None,
        units_confirmed=False, row_ref=seq, latitude=latitude, longitude=longitude, raw=dict(obs.raw))
