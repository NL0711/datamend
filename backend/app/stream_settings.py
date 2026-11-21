"""Settings of the telemetry stream (slice S3b): the active source, the station set, the cadence of each source, the MQTT connection and the
external point. They are saved in the same file as the other runtime settings (runtime_settings.py) and follow the same rules: saved values
override the environment, and a secret (the MQTT password) is stored but NEVER returned: callers only learn whether it is set.

Every default below is an ``assumed`` configuration value, not a measurement.
"""
from __future__ import annotations

import ipaddress
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.app import runtime_settings as rs
from backend.app.config import settings

SOURCE_IDS = ("simulator", "open_meteo", "weather_union", "esp32")
STATION_MODES = ("city", "all", "ids")
DEFAULT_CITY = "Bengaluru"                    # assumed: one city with 32 catalogue gauges
DEFAULT_CAP = 5                               # assumed: a small subset (one multi-location Open-Meteo request, a few Weather Union calls per round)
MAX_CAP = 50
MAX_IDS = 200
# (min, max, default) seconds. Open-Meteo "current" values are refreshed by the model about every 15 minutes (assumed from its documentation,
# not measured here), so polling faster than 5 minutes only repeats a value. Weather Union is also bounded by the daily call budget.
INTERVALS: Dict[str, tuple] = {
    "stream_simulator_interval_seconds": (0.05, 60.0, 5.0),
    "stream_open_meteo_interval_seconds": (300.0, 86400.0, 900.0),
    "stream_weather_union_interval_seconds": (60.0, 86400.0, 900.0),
    "stream_esp32_interval_seconds": (5.0, 3600.0, 60.0),     # the expected packet cadence; it only sets when the stream counts as stale
}
DEFAULT_ESP32_STATIONS = ("ESP32-001",)
TOPIC_PREFIX = "skyguard/aws"                 # topics: <prefix>/<station_id>/telemetry and <prefix>/<station_id>/heartbeat (as in the original app)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")
_PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+){0,4}$")


@dataclass(frozen=True)
class StreamEffective:
    active_source: str
    station_mode: str
    city: str
    cap: int
    station_ids: List[str]
    simulator_interval_s: float
    open_meteo_interval_s: float
    weather_union_interval_s: float
    esp32_interval_s: float
    esp32_station_ids: List[str]
    esp32_latitude: Optional[float]
    esp32_longitude: Optional[float]
    mqtt_host: str
    mqtt_port: int
    mqtt_topic_prefix: str
    mqtt_username: str
    mqtt_password: str
    mqtt_tls: bool
    external_point: Optional[Dict[str, Any]]
    sources: Dict[str, str]          # field -> "runtime" | "environment" | "default"


def effective() -> StreamEffective:
    ov = rs.load_overrides()
    env = {"stream_mqtt_host": settings.MQTT_HOST, "stream_mqtt_port": settings.MQTT_PORT, "stream_mqtt_username": settings.MQTT_USERNAME,
           "stream_mqtt_password": settings.MQTT_PASSWORD}
    default: Dict[str, Any] = {
        "stream_active_source": "", "stream_station_mode": "city", "stream_city": DEFAULT_CITY, "stream_station_cap": DEFAULT_CAP, "stream_station_ids": [],
        "stream_esp32_station_ids": list(DEFAULT_ESP32_STATIONS), "stream_esp32_latitude": None, "stream_esp32_longitude": None,
        "stream_mqtt_host": "", "stream_mqtt_port": 1883, "stream_mqtt_topic_prefix": TOPIC_PREFIX, "stream_mqtt_username": "", "stream_mqtt_password": "",
        "stream_mqtt_tls": False, "stream_external_point": None, **{k: v[2] for k, v in INTERVALS.items()}}
    vals: Dict[str, Any] = {}
    src: Dict[str, str] = {}
    for f in rs.STREAM_FIELDS:
        if f in ov and ov[f] not in (None, ""):
            vals[f], src[f] = ov[f], "runtime"
        elif env.get(f) not in (None, ""):
            vals[f], src[f] = env[f], "environment"
        else:
            vals[f], src[f] = default[f], "default"
    if vals["stream_active_source"] not in SOURCE_IDS + ("",):          # a hand-edited saved file must not select a source that does not exist
        vals["stream_active_source"], src["stream_active_source"] = "", "default"
    if vals["stream_station_mode"] not in STATION_MODES:
        vals["stream_station_mode"], src["stream_station_mode"] = "city", "default"
    return StreamEffective(
        active_source=vals["stream_active_source"], station_mode=vals["stream_station_mode"], city=vals["stream_city"], cap=int(vals["stream_station_cap"]),
        station_ids=list(vals["stream_station_ids"]), simulator_interval_s=float(vals["stream_simulator_interval_seconds"]),
        open_meteo_interval_s=float(vals["stream_open_meteo_interval_seconds"]), weather_union_interval_s=float(vals["stream_weather_union_interval_seconds"]),
        esp32_interval_s=float(vals["stream_esp32_interval_seconds"]), esp32_station_ids=list(vals["stream_esp32_station_ids"]),
        esp32_latitude=vals["stream_esp32_latitude"], esp32_longitude=vals["stream_esp32_longitude"], mqtt_host=str(vals["stream_mqtt_host"]),
        mqtt_port=int(vals["stream_mqtt_port"]), mqtt_topic_prefix=str(vals["stream_mqtt_topic_prefix"]), mqtt_username=str(vals["stream_mqtt_username"]),
        mqtt_password=str(vals["stream_mqtt_password"]), mqtt_tls=bool(vals["stream_mqtt_tls"]), external_point=vals["stream_external_point"], sources=src)


def public_view(eff: Optional[StreamEffective] = None) -> Dict[str, Any]:
    """What the API may show: no secret value, ever (only whether the MQTT password is set)."""
    e = eff or effective()
    s = e.sources
    return {
        "source_ids": list(SOURCE_IDS), "station_modes": list(STATION_MODES), "cities": rs.cities(), "max_station_cap": MAX_CAP,
        "interval_limits_seconds": {k.replace("stream_", "").replace("_interval_seconds", ""): [v[0], v[1]] for k, v in INTERVALS.items()},
        "active_source": e.active_source, "active_source_origin": s["stream_active_source"],
        "station_set": {"mode": e.station_mode, "city": e.city, "cap": e.cap, "station_ids": e.station_ids, "mode_origin": s["stream_station_mode"]},
        "intervals_seconds": {"simulator": e.simulator_interval_s, "open_meteo": e.open_meteo_interval_s, "weather_union": e.weather_union_interval_s,
                              "esp32": e.esp32_interval_s},
        "esp32": {"station_ids": e.esp32_station_ids, "latitude": e.esp32_latitude, "longitude": e.esp32_longitude},
        "mqtt": {"host": e.mqtt_host, "host_origin": s["stream_mqtt_host"], "port": e.mqtt_port, "topic_prefix": e.mqtt_topic_prefix,
                 "username": e.mqtt_username, "password_set": bool(e.mqtt_password), "password_origin": s["stream_mqtt_password"], "tls": e.mqtt_tls},
        "external_point": e.external_point,
    }


# ------------------------------------------------------------------------------------------------ validation
def _number(name: str, v: Any, lo: float, hi: float) -> float:
    if isinstance(v, bool):
        raise rs.SettingsError(f"{name} must be a number")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise rs.SettingsError(f"{name} must be a number")
    if math.isnan(x) or not lo <= x <= hi:
        raise rs.SettingsError(f"{name} must be between {lo:g} and {hi:g}")
    return x


def _id_list(name: str, v: Any, limit: int) -> List[str]:
    items = [p.strip() for p in v.split(",")] if isinstance(v, str) else v
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise rs.SettingsError(f"{name} must be a list of station ids")
    items = [i.strip() for i in items if i.strip()]
    if not 1 <= len(items) <= limit:
        raise rs.SettingsError(f"{name} must hold 1 to {limit} station ids")
    return list(dict.fromkeys(items))


def check_mqtt_host(host: str, allow_private: Optional[bool] = None) -> str:
    """A bare host name or address (no scheme, port or path); by default not a private or loopback address, so the form cannot make the server
    connect to internal services. MQTT_ALLOW_PRIVATE=true in the server environment allows a broker on localhost or a private network."""
    h = host.strip()
    if not h:
        return ""
    if not _HOST_RE.match(h) or ".." in h:
        raise rs.SettingsError("the MQTT host must be a host name or address only (no scheme, port or path)")
    allow = allow_private if allow_private is not None else os.environ.get("MQTT_ALLOW_PRIVATE", "").lower() in ("1", "true", "yes")
    if not allow:
        bad = rs._blocked_address(h, "MQTT")
        if bad:
            raise rs.SettingsError(f"the MQTT host resolves to a private or reserved address ({bad}); set MQTT_ALLOW_PRIVATE=true in the server "
                                   f"environment if that is intended")
    return h


def validate_point(v: Any) -> Dict[str, Any]:
    """The external (Open-Meteo) point the dashboard's city presets configure: coordinates, an id and a name."""
    if not isinstance(v, dict):
        raise rs.SettingsError("the external point must be an object with latitude and longitude")
    from backend.app.stream import stations
    lat, lon = _number("latitude", v.get("latitude"), -90.0, 90.0), _number("longitude", v.get("longitude"), -180.0, 180.0)
    sid = str(v.get("station_id") or f"EXT-{lat:.3f}_{lon:.3f}").strip()
    if not _ID_RE.match(sid):
        raise rs.SettingsError("the station id must be 1 to 64 letters, digits, '.', '_' or '-'")
    if sid in stations.known_ids():
        raise rs.SettingsError(f"the station id {sid!r} is already a catalogue or simulator station; use another id")
    name = str(v.get("station_name") or v.get("name") or sid).strip()[:80]
    return {"station_id": sid, "name": name, "latitude": round(lat, 4), "longitude": round(lon, 4)}


def validate_field(f: str, v: Any) -> Any:
    """One stream setting -> the value to save (None removes the override). Raises SettingsError."""
    from backend.app.stream import stations
    if f == "stream_active_source":
        if v == "":
            return None
        if v not in SOURCE_IDS:
            raise rs.SettingsError(f"the active source must be one of: {', '.join(SOURCE_IDS)} (empty for none)")
        return v
    if f == "stream_station_mode":
        if v not in STATION_MODES:
            raise rs.SettingsError(f"the station set mode must be one of: {', '.join(STATION_MODES)}")
        return v
    if f == "stream_city":
        match = {c.lower(): c for c in rs.cities()}.get(str(v).strip().lower())
        if match is None:
            raise rs.SettingsError(f"unknown city {v!r}; choose one of: {', '.join(rs.cities())}")
        return match
    if f == "stream_station_cap":
        return int(_number("the station cap", v, 1, MAX_CAP))
    if f == "stream_station_ids":
        ids = _id_list("the station ids", v, MAX_IDS)
        unknown = [i for i in ids if i not in stations.known_ids()]
        if unknown:
            raise rs.SettingsError(f"unknown stations (neither a catalogue gauge nor a simulator station): {', '.join(unknown[:5])}"
                                   + (" ..." if len(unknown) > 5 else ""))
        return ids
    if f in INTERVALS:
        lo, hi, _ = INTERVALS[f]
        return _number("the cadence", v, lo, hi)
    if f == "stream_esp32_station_ids":
        ids = _id_list("the ESP32 station ids", v, 20)
        bad = [i for i in ids if not _ID_RE.match(i)]
        if bad:
            raise rs.SettingsError(f"an ESP32 station id must be 1 to 64 letters, digits, '.', '_' or '-': {bad[0]!r}")
        taken = [i for i in ids if i in stations.known_ids()]
        if taken:
            raise rs.SettingsError(f"{taken[0]!r} is already a catalogue or simulator station; use another id")
        return ids
    if f == "stream_esp32_latitude":
        return _number("latitude", v, -90.0, 90.0)
    if f == "stream_esp32_longitude":
        return _number("longitude", v, -180.0, 180.0)
    if f == "stream_mqtt_host":
        return check_mqtt_host(str(v)) or None
    if f == "stream_mqtt_port":
        return int(_number("the MQTT port", v, 1, 65535))
    if f == "stream_mqtt_topic_prefix":
        p = str(v).strip().strip("/")
        if not _PREFIX_RE.match(p):
            raise rs.SettingsError("the MQTT topic prefix must be 1 to 5 levels of letters, digits, '_' or '-' (no wildcards)")
        return p
    if f == "stream_mqtt_username":
        u = str(v).strip()
        if len(u) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in u):
            raise rs.SettingsError("the MQTT user name must be at most 128 characters with no control characters")
        return u or None
    if f == "stream_mqtt_password":
        pw = str(v)
        if not 1 <= len(pw) <= 300 or any(ord(c) < 32 or ord(c) == 127 for c in pw):
            raise rs.SettingsError("the MQTT password must be 1 to 300 characters with no control characters")
        return pw
    if f == "stream_mqtt_tls":
        if not isinstance(v, bool):
            raise rs.SettingsError("the MQTT TLS setting must be true or false")
        return v
    if f == "stream_external_point":
        return validate_point(v)
    raise rs.SettingsError(f"unknown setting {f!r}")
