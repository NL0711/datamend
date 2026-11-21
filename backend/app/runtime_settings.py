"""Settings that can be changed from the dashboard without editing .env or restarting the server.

Values saved here OVERRIDE the environment (.env). They live in a JSON file (RUNTIME_SETTINGS_PATH, default data/runtime_settings.json,
git-ignored, written with owner-only permissions where the OS allows). Secrets (the Weather Union key, the narrator token) are stored but
NEVER returned by any endpoint: callers only learn whether one is set and where it came from.

Editing is only possible when ADMIN_TOKEN is set in the environment (see api/settings.py). Nothing here is a user account system.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from backend.app.config import settings
from backend.app.rainfall.providers import provider_info

# The feed settings keep their weather_union_* names (saved files and .env stay valid) but apply to whichever weather provider is chosen:
# weather_union_api_key is THE weather API key, weather_union_city the station cluster, and so on.
FIELDS = ("weather_provider", "weather_union_api_key", "weather_union_city", "weather_union_poll_interval_seconds", "weather_union_accumulation_mode",
          "narrator_url", "narrator_token")
# Telemetry stream settings (slice S3b); their defaults, validation and effective view live in stream_settings.py. They share this file and its rules.
STREAM_FIELDS = ("stream_active_source", "stream_station_mode", "stream_city", "stream_station_cap", "stream_station_ids",
                 "stream_simulator_interval_seconds", "stream_open_meteo_interval_seconds", "stream_weather_union_interval_seconds",
                 "stream_esp32_interval_seconds", "stream_esp32_station_ids", "stream_esp32_latitude", "stream_esp32_longitude",
                 "stream_mqtt_host", "stream_mqtt_port", "stream_mqtt_topic_prefix", "stream_mqtt_username", "stream_mqtt_password", "stream_mqtt_tls",
                 "stream_external_point")
SECRETS = ("weather_union_api_key", "narrator_token", "stream_mqtt_password")
PROVIDERS = ("weather_union", "open_meteo")
KEY_REQUIRED = {"weather_union": True, "open_meteo": False}
ACCUMULATION_MODES = ("cumulative", "per_reading")
MIN_INTERVAL_S, MAX_INTERVAL_S = 60.0, 86400.0
_lock = threading.Lock()


def _path() -> Path:
    return Path(os.environ.get("RUNTIME_SETTINGS_PATH", "data/runtime_settings.json"))


def load_overrides() -> Dict[str, Any]:
    """The saved overrides; an unreadable or corrupt file counts as none (never crashes the app)."""
    try:
        doc = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in doc.items() if k in FIELDS or k in STREAM_FIELDS} if isinstance(doc, dict) else {}


def _write(doc: Dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, p)


@dataclass(frozen=True)
class Effective:
    weather_provider: str
    weather_union_api_key: str
    weather_union_city: str
    weather_union_poll_interval_seconds: float
    weather_union_accumulation_mode: str
    narrator_url: str
    narrator_token: str
    sources: Dict[str, str]          # field -> "runtime" | "environment" | "unset"


def effective() -> Effective:
    """Runtime overrides on top of the environment."""
    ov = load_overrides()
    env = {"weather_provider": settings.WEATHER_PROVIDER if settings.WEATHER_PROVIDER in PROVIDERS else "weather_union",
           "weather_union_api_key": settings.WEATHER_UNION_API_KEY, "weather_union_city": settings.WEATHER_UNION_CITY,
           "weather_union_poll_interval_seconds": settings.WEATHER_UNION_POLL_INTERVAL_SECONDS,
           "weather_union_accumulation_mode": settings.WEATHER_UNION_ACCUMULATION_MODE,
           "narrator_url": settings.NARRATOR_URL, "narrator_token": settings.NARRATOR_TOKEN}
    vals, src = {}, {}
    for f in FIELDS:
        if f in ov and ov[f] not in (None, ""):
            vals[f], src[f] = ov[f], "runtime"
        else:
            vals[f] = env[f]
            src[f] = "environment" if env[f] not in (None, "") else "unset"
    vals["weather_union_poll_interval_seconds"] = float(vals["weather_union_poll_interval_seconds"])
    if vals["weather_provider"] not in PROVIDERS:                 # a hand-edited saved file must not switch the feed to nothing
        vals["weather_provider"], src["weather_provider"] = "weather_union", "unset"
    return Effective(sources=src, **vals)


def feed_enabled(e: Effective) -> bool:
    """Whether the live feed can run: a city, and a key when the provider needs one (Open-Meteo works without)."""
    return bool(e.weather_union_city and (e.weather_union_api_key or not KEY_REQUIRED[e.weather_provider]))


def public_view(eff: Optional[Effective] = None) -> Dict[str, Any]:
    """What the API may show: no secret value, ever."""
    from backend.app import stream_settings
    e = eff or effective()
    return {
        "providers": provider_info(),
        "weather_union": {
            "provider": e.weather_provider, "provider_source": e.sources["weather_provider"], "key_required": KEY_REQUIRED[e.weather_provider],
            "api_key_set": bool(e.weather_union_api_key), "api_key_source": e.sources["weather_union_api_key"],
            "city": e.weather_union_city, "city_source": e.sources["weather_union_city"],
            "poll_interval_seconds": e.weather_union_poll_interval_seconds, "poll_interval_source": e.sources["weather_union_poll_interval_seconds"],
            "accumulation_mode": e.weather_union_accumulation_mode, "accumulation_mode_source": e.sources["weather_union_accumulation_mode"],
            "enabled": feed_enabled(e),
        },
        "narrator": {
            "url": e.narrator_url, "url_source": e.sources["narrator_url"],
            "token_set": bool(e.narrator_token), "token_source": e.sources["narrator_token"],
            "connected": bool(e.narrator_url),
        },
        # the interim LLM layer: environment only, so only whether a key is set and which model, never the key
        "gemini": {"key_set": bool(settings.GEMINI_API_KEY.strip()), "model": settings.GEMINI_MODEL,
                   "active": bool(settings.GEMINI_API_KEY.strip()) and not e.narrator_url.strip()},
        "stream": stream_settings.public_view(),
    }


# ------------------------------------------------------------------------------------------------ validation

class SettingsError(ValueError):
    """A submitted value is not acceptable (the API answers 422 with this message)."""


def cities() -> List[str]:
    from backend.app.rainfall.catalog import load_catalog
    return sorted({s.city for s in load_catalog().values()})


def _check_secret(name: str, v: str) -> str:
    v = v.strip()
    if not (8 <= len(v) <= 300) or any(ord(c) < 33 or ord(c) == 127 for c in v):
        raise SettingsError(f"{name} must be 8 to 300 characters with no spaces or control characters")
    return v


def _blocked_address(host: str, what: str = "narrator") -> Optional[str]:
    """Why the host must not be called from the server (private, loopback, link-local, reserved...), or None when it is public."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise SettingsError(f"the {what} host {host!r} does not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return str(ip)
    return None


def check_narrator_url(url: str, allow_private: Optional[bool] = None) -> str:
    """http(s) only, and by default not a private or loopback address (so the form cannot make the server call internal services).
    Set NARRATOR_ALLOW_PRIVATE=true in the environment to use a narrator on localhost or a private network."""
    u = url.strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise SettingsError("the narrator URL must start with http:// or https:// and name a host")
    if p.username or p.password:
        raise SettingsError("put no credentials in the narrator URL; use the token field")
    allow = allow_private if allow_private is not None else os.environ.get("NARRATOR_ALLOW_PRIVATE", "").lower() in ("1", "true", "yes")
    if not allow:
        bad = _blocked_address(p.hostname)
        if bad:
            raise SettingsError(f"the narrator host resolves to a private or reserved address ({bad}); set NARRATOR_ALLOW_PRIVATE=true in the "
                                f"server environment if that is intended")
    return u


def validate_update(raw: Dict[str, Any], clear: List[str]) -> Dict[str, Any]:
    """-> the overrides to merge. `raw` holds only the fields the caller sent (None means not sent); `clear` removes overrides."""
    out: Dict[str, Any] = {}
    for f in clear:
        if f not in FIELDS and f not in STREAM_FIELDS:
            raise SettingsError(f"unknown setting {f!r}")
        out[f] = None
    for f, v in raw.items():
        if v is None:
            continue
        if f in STREAM_FIELDS:
            from backend.app import stream_settings
            out[f] = stream_settings.validate_field(f, v)
        elif f == "weather_provider":
            if v not in PROVIDERS:
                raise SettingsError(f"the weather provider must be one of: {', '.join(PROVIDERS)}")
            out[f] = v
        elif f == "weather_union_api_key":
            out[f] = _check_secret("the weather API key", v)
        elif f == "narrator_token":
            out[f] = _check_secret("the narrator token", v)
        elif f == "weather_union_city":
            match = {c.lower(): c for c in cities()}.get(str(v).strip().lower())
            if match is None:
                raise SettingsError(f"unknown city {v!r}; choose one of: {', '.join(cities())}")
            out[f] = match
        elif f == "weather_union_poll_interval_seconds":
            x = float(v)
            if not (MIN_INTERVAL_S <= x <= MAX_INTERVAL_S) or x != x:
                raise SettingsError(f"the poll interval must be between {MIN_INTERVAL_S:g} and {MAX_INTERVAL_S:g} seconds")
            out[f] = x
        elif f == "weather_union_accumulation_mode":
            if v not in ACCUMULATION_MODES:
                raise SettingsError(f"accumulation mode must be one of {ACCUMULATION_MODES}")
            out[f] = v
        elif f == "narrator_url":
            out[f] = check_narrator_url(v)
        else:
            raise SettingsError(f"unknown setting {f!r}")
    return out


def save_update(changes: Dict[str, Any]) -> None:
    """Merge validated changes into the saved overrides (None removes an override)."""
    with _lock:
        doc = load_overrides()
        for k, v in changes.items():
            if v is None:
                doc.pop(k, None)
            else:
                doc[k] = v
        _write(doc)
