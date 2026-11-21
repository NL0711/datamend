"""Adapters from other sources to the internal Reading record."""
from __future__ import annotations

from typing import Optional

from backend.app.rainfall.weather_union import RainObservation
from backend.app.validation.records import Reading


def reading_from_observation(obs: RainObservation, accumulation_mode: str, seq: int,
                             latitude: Optional[float] = None, longitude: Optional[float] = None, source: str = "weather_union",
                             time_basis: str = "received", units_confirmed: bool = False) -> Reading:
    """A live-feed observation as a Reading. By default a Weather Union poll: the API gives no observation time, so the time is the time of
    receipt (time_basis 'received', which makes gap checks weaker); units and period are unconfirmed, so mm is ASSUMED (units_confirmed False).
    Another provider passes its own source, time basis and units status. A NO_RAIN_FIELDS or API_ERROR poll keeps both values None; nothing
    is invented."""
    return Reading(
        source=source, station_id=obs.station_id, timestamp=obs.observed_at, accumulation=obs.rain_accumulation,
        intensity=obs.rain_intensity, time_basis=time_basis,
        accumulation_mode=accumulation_mode if obs.rain_accumulation is not None else None,
        units_confirmed=units_confirmed, row_ref=seq, latitude=latitude, longitude=longitude, raw=dict(obs.raw))
