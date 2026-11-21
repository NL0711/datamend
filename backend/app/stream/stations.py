"""The station set of the stream sources: which stations a source polls, from the stream settings (stream_settings.py).

Modes: ``city`` (the ``cap`` catalogue gauges closest to the city's median point, so they are each other's neighbours), ``all`` (every catalogue
gauge) and ``ids`` (explicit ids, each a catalogue gauge or a simulator station). A station that exists nowhere is refused, never invented.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from backend.app.rainfall.catalog import Station, load_catalog
from backend.app.rainfall.service import pick_cluster
from backend.app.stream.sim_physics import SIM_STATIONS
from backend.app.stream.types import StationInfo


def catalogue_info(s: Station) -> StationInfo:
    return StationInfo(s.locality_id, f"{s.place}, {s.city}", s.latitude, s.longitude, None)


def simulator_info() -> Dict[str, StationInfo]:
    return {s.station_id: StationInfo(s.station_id, s.name, s.latitude, s.longitude, s.elevation) for s in SIM_STATIONS}


def known_ids() -> set:
    """Every station id a station set may name: the 580 catalogue gauges and the simulator's stations."""
    return set(load_catalog()) | {s.station_id for s in SIM_STATIONS}


def resolve(mode: str, city: str, cap: int, ids: Sequence[str]) -> List[StationInfo]:
    """The stations of a station set. Raises ValueError for an unknown city or id (settings validation catches this earlier)."""
    cat = load_catalog()
    if mode == "all":
        return [catalogue_info(s) for s in cat.values()]
    if mode == "city":
        return [catalogue_info(s) for s in pick_cluster(city, max(1, cap), cat)]
    if mode == "ids":
        sims = simulator_info()
        out: List[StationInfo] = []
        for sid in dict.fromkeys(ids):
            if sid in cat:
                out.append(catalogue_info(cat[sid]))
            elif sid in sims:
                out.append(sims[sid])
            else:
                raise ValueError(f"unknown station {sid!r}: it is neither a catalogue gauge nor a simulator station")
        return out
    raise ValueError(f"unknown station set mode {mode!r}")
