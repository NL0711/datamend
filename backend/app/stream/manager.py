"""The stream manager: owns the registered sources and the one active source, switches between them, and fans readings out to subscribers.

States of the stream: ``stopped`` (nothing running), ``running`` (the source runs and a reading arrived recently), ``stale`` (the source claims
to run but no reading arrived for longer than ``stale_after``; ``stale_since`` says when that began) and ``disconnected`` (the source says its
transport is down). The manager NEVER fabricates a reading to fill a gap: silence is reported as silence.

Every reading goes through ``processor`` (in production: score it and store it, see service.py) and the resulting frame is pushed to each
subscriber's bounded queue. A slow subscriber loses its oldest frames (counted in ``dropped``); it never blocks the stream or the others.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.app.stream import frames
from backend.app.stream.source import TelemetrySource
from backend.app.stream.types import SourceStartFailed, StreamReading, StreamState, UnknownSource, utcnow

logger = logging.getLogger(__name__)

Processor = Callable[[StreamReading], Awaitable[Dict[str, Any]]]


async def plain_processor(reading: StreamReading) -> Dict[str, Any]:
    """No storage and no checks: the frame data of the reading as it is. Used when the manager is built without a store."""
    return frames.observation_data(reading, stored=False)


@dataclass
class StreamStatus:
    source_id: Optional[str]
    source_type: Optional[str]
    state: StreamState
    last_reading_at: Optional[datetime]
    stale_since: Optional[datetime]
    stale_after_s: Optional[float]
    packet_count: int
    last_error: Optional[str]
    last_error_at: Optional[datetime]
    expected_interval_s: Optional[float]
    subscribers: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id, "source_type": self.source_type, "state": self.state,
            "last_reading_at": frames.iso(self.last_reading_at), "stale_since": frames.iso(self.stale_since), "stale_after_seconds": self.stale_after_s,
            "packet_count": self.packet_count, "last_error": self.last_error, "last_error_at": frames.iso(self.last_error_at),
            "expected_interval_seconds": self.expected_interval_s, "subscribers": self.subscribers,
        }


class Subscription:
    """One subscriber's bounded queue of frames."""

    def __init__(self, size: int) -> None:
        self.queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=size)
        self.dropped = 0

    def push(self, frame: Dict[str, Any]) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
        self.queue.put_nowait(frame)

    async def get(self) -> Dict[str, Any]:
        return await self.queue.get()


class StreamManager:
    def __init__(self, processor: Processor = plain_processor, *, clock: Callable[[], datetime] = utcnow, stale_factor: float = 3.0,
                 min_stale_s: float = 5.0, watch_interval_s: float = 1.0, queue_size: int = 256) -> None:
        self._processor = processor
        self._clock = clock
        self.stale_factor = stale_factor
        self.min_stale_s = min_stale_s
        self.watch_interval_s = watch_interval_s
        self._queue_size = queue_size
        self._sources: Dict[str, TelemetrySource] = {}
        self._active: Optional[TelemetrySource] = None
        self._subs: List[Subscription] = []
        self._lock: Optional[asyncio.Lock] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._started_at: Optional[datetime] = None
        self._last_reading_at: Optional[datetime] = None
        self._packets = 0
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None
        self._published_state: Optional[str] = None

    # ------------------------------------------------------------------ registry
    def register(self, source: TelemetrySource) -> None:
        """Add a source. The registry is open: later slices register their own sources the same way."""
        self._sources[source.source_id] = source

    def sources(self) -> List[TelemetrySource]:
        return list(self._sources.values())

    def source(self, source_id: str) -> TelemetrySource:
        try:
            return self._sources[source_id]
        except KeyError:
            raise UnknownSource(f"no data source '{source_id}' is registered") from None

    @property
    def active(self) -> Optional[TelemetrySource]:
        return self._active

    def _guard(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ------------------------------------------------------------------ control
    async def select(self, source_id: str) -> StreamStatus:
        """Make ``source_id`` the active source and start it. The previous active source is stopped first."""
        new = self.source(source_id)
        async with self._guard():
            if self._active is not None and self._active is not new:
                await self._stop_active()
            self._active = new
            await self._start_active()
        return self.status()

    async def start(self) -> StreamStatus:
        """Start the active source again after a stop. Does nothing when no source is selected."""
        async with self._guard():
            if self._active is not None and self._active.status().state == "stopped":
                await self._start_active()
        return self.status()

    async def stop(self) -> StreamStatus:
        async with self._guard():
            await self._stop_active()
        return self.status()

    async def shutdown(self) -> None:
        await self.stop()

    async def _start_active(self) -> None:
        assert self._active is not None
        self._started_at = self._clock()
        self._last_reading_at = None
        self._packets = 0
        self._last_error = self._last_error_at = None
        try:
            await self._active.start(self._emit)
        except Exception as exc:
            self._last_error, self._last_error_at = f"{type(exc).__name__}: {exc}", self._clock()
            self._publish_state_if_changed()
            raise SourceStartFailed(f"the source '{self._active.source_id}' could not start: {exc}") from exc
        if self._watch_task is None or self._watch_task.done():
            self._watch_task = asyncio.create_task(self._watch())
        self._publish_state_if_changed()

    async def _stop_active(self) -> None:
        if self._active is not None:
            await self._active.stop()
        if self._watch_task is not None:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except (asyncio.CancelledError, Exception):
                pass
            self._watch_task = None
        self._publish_state_if_changed()

    # ------------------------------------------------------------------ readings and subscribers
    async def _emit(self, reading: StreamReading) -> None:
        """The callback a source calls with each reading."""
        now = self._clock()
        self._last_reading_at = now
        self._packets += 1
        try:
            data = await self._processor(reading)
        except Exception:
            logger.exception("processing a %s reading of %s failed; it is passed on unstored and unchecked", reading.source, reading.station_id)
            data = frames.observation_data(reading, stored=False)
        self.publish(frames.observation_frame(data))
        self._publish_state_if_changed()

    def publish(self, frame: Dict[str, Any]) -> None:
        for sub in list(self._subs):
            sub.push(frame)

    def subscribe(self) -> Subscription:
        sub = Subscription(self._queue_size)
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    # ------------------------------------------------------------------ state
    def stale_after_s(self) -> Optional[float]:
        if self._active is None:
            return None
        interval = self._active.status().expected_interval_s or 0.0
        return max(self.min_stale_s, self.stale_factor * interval)

    def status(self) -> StreamStatus:
        src = self._active
        if src is None:
            return StreamStatus(None, None, "stopped", None, None, None, 0, None, None, None, len(self._subs))
        own = src.status()
        stale_after = self.stale_after_s()
        state: StreamState
        stale_since: Optional[datetime] = None
        if own.state == "stopped":
            state = "stopped"
        elif own.state == "disconnected":
            state = "disconnected"
        else:
            ref = self._last_reading_at or self._started_at
            if ref is not None and stale_after is not None and (self._clock() - ref).total_seconds() > stale_after:
                state, stale_since = "stale", ref + timedelta(seconds=stale_after)
            else:
                state = "running"
        return StreamStatus(src.source_id, src.source_type, state, self._last_reading_at, stale_since, stale_after, self._packets,
                            own.last_error or self._last_error, own.last_error_at or self._last_error_at, own.expected_interval_s, len(self._subs))

    def refresh_state(self) -> StreamStatus:
        """Re-evaluate the state and tell the subscribers if it changed (the watchdog calls this on a timer; tests call it directly)."""
        self._publish_state_if_changed()
        return self.status()

    def _publish_state_if_changed(self) -> None:
        st = self.status()
        marker = f"{st.source_id}:{st.state}"
        if marker != self._published_state:
            self._published_state = marker
            self.publish(frames.status_frame(st.as_dict()))

    async def _watch(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.watch_interval_s)
                self._publish_state_if_changed()
        except asyncio.CancelledError:
            raise
