"""The seam every telemetry source implements. The manager owns the active source and gives it one callback; the source pushes readings into it.

A source never invents a reading to cover a gap: if its transport is silent it simply emits nothing, and the manager reports the silence
as ``stale`` (or the source reports ``disconnected``).
"""
from __future__ import annotations

from typing import Awaitable, Callable, Protocol, Sequence, runtime_checkable

from backend.app.stream.types import SourceStatus, StationInfo, StreamReading

Emit = Callable[[StreamReading], Awaitable[None]]


@runtime_checkable
class TelemetrySource(Protocol):
    source_id: str          # stable id, stored on every reading ("simulator")
    source_type: str        # the dashboard's DataSourceType ("SIMULATED")
    name: str
    description: str

    async def start(self, emit: Emit) -> None:
        """Begin producing readings, pushing each into ``emit``. Returns once started (the production loop runs as a background task)."""

    async def stop(self) -> None:
        """Stop producing readings and release the transport. Safe to call when already stopped."""

    def status(self) -> SourceStatus:
        """The source's own state: stopped, running or disconnected."""

    def stations(self) -> Sequence[StationInfo]:
        """The stations this source produces readings for."""
