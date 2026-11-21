"""TEST FAKES for the telemetry stream. Nothing in this file is production code or a real source: a hand-driven source and a hand-driven clock."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.app.stream.source import Emit
from backend.app.stream.types import SourceStatus, StationInfo, StreamReading

T0 = datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    """TEST FAKE: a clock that moves only when the test advances it."""

    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


class FakeSource:
    """TEST FAKE: a TelemetrySource the test drives by hand (push a reading, drop the connection, refuse to start)."""

    source_type = "FAKE"
    name = "Fake source (test)"
    description = "TEST FAKE"

    def __init__(self, source_id: str = "fake", interval: Optional[float] = 1.0, fail_start: bool = False) -> None:
        self.source_id = source_id
        self.interval = interval
        self.fail_start = fail_start
        self.state = "stopped"
        self.error: Optional[str] = None
        self.emit: Optional[Emit] = None
        self.starts = 0
        self.stops = 0

    async def start(self, emit: Emit) -> None:
        if self.fail_start:
            raise ConnectionError("transport refused")
        self.emit, self.state, self.error = emit, "running", None
        self.starts += 1

    async def stop(self) -> None:
        self.state = "stopped"
        self.stops += 1

    def status(self) -> SourceStatus:
        return SourceStatus(self.state, self.interval, self.error)  # type: ignore[arg-type]

    def stations(self):
        return [StationInfo(f"{self.source_id}-1", "Fake station", 10.0, 20.0)]

    async def push(self, reading: StreamReading) -> None:
        assert self.emit is not None
        await self.emit(reading)

    def drop_connection(self, why: str = "broker went away") -> None:
        self.state, self.error = "disconnected", why


def reading(station: str = "S1", at: datetime = T0, source: str = "fake", **values) -> StreamReading:
    return StreamReading(station, at, source, **values)
