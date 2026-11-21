"""Applies the stream settings (stream_settings.py) to the registered sources, and restarts the active source when a setting that concerns it changed."""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Set

from backend.app import runtime_settings as rs
from backend.app import stream_settings as ss
from backend.app.config import settings
from backend.app.rainfall.catalog import load_catalog
from backend.app.stream import stations as station_sets
from backend.app.stream.esp32 import Esp32Source
from backend.app.stream.manager import StreamManager
from backend.app.stream.open_meteo import OpenMeteoSource
from backend.app.stream.simulator import SimulatorSource
from backend.app.stream.types import StationInfo, StreamError
from backend.app.stream.wu_source import WeatherUnionSource

logger = logging.getLogger(__name__)

STATION_SET_FIELDS = {"stream_station_mode", "stream_city", "stream_station_cap", "stream_station_ids"}


def external_point_info(point: dict) -> StationInfo:
    return StationInfo(point["station_id"], point["name"], point["latitude"], point["longitude"], None)


def station_set(eff: ss.StreamEffective) -> List[StationInfo]:
    return station_sets.resolve(eff.station_mode, eff.city, eff.cap, eff.station_ids)


def station_set_view(eff: ss.StreamEffective) -> dict:
    return {"mode": eff.station_mode, "city": eff.city if eff.station_mode == "city" else None, "cap": eff.cap if eff.station_mode == "city" else None}


def configure_sources(manager: StreamManager, eff: Optional[ss.StreamEffective] = None) -> None:
    """Hand each source its part of the effective settings. A source that is running is not touched (stop it first); a station set that cannot be
    resolved is passed on as an error the source reports when asked to start."""
    eff = eff or ss.effective()
    base = rs.effective()
    try:
        chosen, error = station_set(eff), None
    except ValueError as exc:
        chosen, error = [], str(exc)
    for src in manager.sources():
        if src.status().state != "stopped":
            continue
        if isinstance(src, SimulatorSource):
            src.configure(interval_seconds=eff.simulator_interval_s)
        elif isinstance(src, OpenMeteoSource):
            point = eff.external_point
            src.configure([external_point_info(point)] if point else chosen, eff.open_meteo_interval_s, None if point else error)
        elif isinstance(src, WeatherUnionSource):
            cat = load_catalog()
            src.configure([s for s in chosen if s.station_id in cat], eff.weather_union_interval_s, base.weather_union_api_key,
                          base.weather_union_accumulation_mode, error)
        elif isinstance(src, Esp32Source):
            src.configure(eff.esp32_station_ids, eff.esp32_latitude, eff.esp32_longitude, eff.esp32_interval_s, eff.mqtt_host, eff.mqtt_port,
                          eff.mqtt_topic_prefix, eff.mqtt_username, eff.mqtt_password, eff.mqtt_tls)


def affected_sources(changed: Iterable[str]) -> Set[str]:
    ch = set(changed)
    out: Set[str] = set()
    if ch & STATION_SET_FIELDS:
        out |= {"open_meteo", "weather_union"}
    if "stream_external_point" in ch or "stream_open_meteo_interval_seconds" in ch:
        out.add("open_meteo")
    if "stream_simulator_interval_seconds" in ch:
        out.add("simulator")
    if any(c.startswith("weather_union_") for c in ch) or "stream_weather_union_interval_seconds" in ch:
        out.add("weather_union")
    if any(c.startswith(("stream_mqtt_", "stream_esp32_")) for c in ch):
        out.add("esp32")
    return out


async def apply_changes(manager: StreamManager, changed: Iterable[str]) -> Optional[str]:
    """After settings were saved: restart the active source if a setting that concerns it changed, re-configure the others, and select (or
    stop) when the active source setting changed. Returns an error text when the source could not be started, else None."""
    changed = set(changed)
    active = manager.active
    restart = active is not None and active.source_id in affected_sources(changed) and active.status().state != "stopped"
    try:
        if restart:
            await manager.stop()
        configure_sources(manager)
        eff = ss.effective()
        if "stream_active_source" in changed:
            if eff.active_source:
                await manager.select(eff.active_source)
            else:
                await manager.stop()
        elif restart:
            await manager.start()
    except StreamError as exc:
        return str(exc)
    return None


async def autostart(manager: StreamManager) -> Optional[str]:
    """At server start: select the source saved as the active one; with none saved, start the simulator (STREAM_AUTOSTART_SIMULATOR, default on)."""
    eff = ss.effective()
    source = eff.active_source or ("simulator" if settings.STREAM_AUTOSTART_SIMULATOR else None)    # no saved choice: the simulator, unless switched off
    if not source:
        return None
    from backend.app.stream import backfill
    if source == "simulator" and backfill.enabled():
        backfill.start_in_background(manager, source)       # earlier synthetic readings first, as a background task so the server is up at once; the simulator starts after
        return None
    backfill.state.status = "skipped"
    backfill.state.reason = "the simulator is not the starting source" if source != "simulator" else "disabled (STREAM_BACKFILL_READINGS is 0)"
    try:
        await manager.select(source)
    except StreamError as exc:
        logger.warning("[STREAM] the saved active source %s did not start: %s", eff.active_source, exc)
        return str(exc)
    return None
