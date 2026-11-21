"""Value types of the telemetry stream: a labelled reading, a source's own status, and the typed errors the stream raises.

A reading carries only the variables its source really has; a variable the source does not report is None, never a filled value.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

SourceState = Literal["stopped", "running", "disconnected"]
StreamState = Literal["stopped", "running", "disconnected", "stale"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class StreamReading:
    """One labelled reading of one station. ``timestamp`` is timezone-aware UTC. ``source`` is the id of the source that produced it and is
    stored with the reading. ``injected`` is the synthetic ground-truth label of a fault the simulator injected on purpose (None otherwise,
    and always None for any other source)."""
    station_id: str
    timestamp: datetime
    source: str
    temperature_c: Optional[float] = None
    pressure_hpa: Optional[float] = None
    humidity_pct: Optional[float] = None
    rain_mm: Optional[float] = None          # rain of this reading interval, mm (per-reading, not a counter)
    injected: Optional[str] = None


@dataclass(frozen=True)
class StationInfo:
    """A station a source produces readings for."""
    station_id: str
    name: str
    latitude: float
    longitude: float
    elevation: Optional[float] = None


@dataclass(frozen=True)
class SourceStatus:
    """What a source itself knows: its state and why it is not running. The manager adds what it observed (last reading, staleness)."""
    state: SourceState
    expected_interval_s: Optional[float] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None


class StreamError(Exception):
    """Base of the errors the stream raises; the API layer maps each subclass to one HTTP status."""


class UnknownSource(StreamError):
    """No source with this id is registered."""


class SourceStartFailed(StreamError):
    """The source could not start (for example its transport refused)."""


class UnknownStation(StreamError):
    """The station is not one the simulator produces."""


class SimulatorNotRunning(StreamError):
    """An injection was asked for while the simulator is not running, so there is no stream to disturb."""


class SimulatorBusy(StreamError):
    """The simulator cannot be reconfigured while it runs."""


class BadSimulatorConfig(StreamError):
    """A start or injection request names something the simulator does not offer."""
