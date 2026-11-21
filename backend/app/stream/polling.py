"""Shared loop of the sources that poll an HTTP API (Open-Meteo, Weather Union).

A poll that fails sets the source to ``disconnected`` with the reason and the loop tries again after one interval; a poll that works sets it back
to ``running``. A failed poll emits nothing: no reading is ever invented to cover it (the manager then reports ``disconnected``, or ``stale``
when the source still claims to run but nothing arrives).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.app.stream.source import Emit
from backend.app.stream.types import SourceStartFailed, SourceStatus, utcnow

logger = logging.getLogger(__name__)


class PollingSource:
    source_id = ""
    source_type = ""
    name = ""
    description = ""

    def __init__(self, *, clock: Callable[[], datetime] = utcnow, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep) -> None:
        self._clock, self._sleep = clock, sleep
        self._task: Optional[asyncio.Task] = None
        self._state = "stopped"
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None
        self.polls = 0
        self.failed_polls = 0

    # -- what a subclass provides
    @property
    def interval_s(self) -> float:
        raise NotImplementedError

    async def prepare(self) -> None:
        """Check the configuration and open the transport. Raise SourceStartFailed when the source cannot run."""

    async def release(self) -> None:
        """Close what prepare opened."""

    async def poll_once(self, emit: Emit) -> Optional[str]:
        """One poll: emit the readings it got. Raise when the poll failed as a whole; return a note when it only partly worked."""
        raise NotImplementedError

    def extra_metadata(self) -> Dict[str, Any]:
        return {}

    # -- the TelemetrySource interface
    def status(self) -> SourceStatus:
        if self._task is not None and self._task.done() and self._state in ("running", "disconnected"):
            self._state = "disconnected"
            if self._last_error is None:
                self._last_error, self._last_error_at = "the polling loop stopped", self._clock()
        return SourceStatus(self._state, self.interval_s, self._last_error, self._last_error_at)  # type: ignore[arg-type]

    async def start(self, emit: Emit) -> None:
        if self._task is not None and not self._task.done():
            return
        self._last_error = self._last_error_at = None
        try:
            await self.prepare()
        except SourceStartFailed:
            self._state = "stopped"
            raise
        except Exception as exc:
            self._state = "stopped"
            raise SourceStartFailed(f"{type(exc).__name__}: {exc}") from exc
        self._state = "running"
        self._task = asyncio.create_task(self._loop(emit))

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._state != "stopped":
            await self.release()
        self._state = "stopped"

    async def _loop(self, emit: Emit) -> None:
        try:
            while True:
                try:
                    note = await self.poll_once(emit)
                    self.polls += 1
                    self._state = "running"
                    self._last_error, self._last_error_at = (note, self._clock()) if note else (None, None)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.polls += 1
                    self.failed_polls += 1
                    self._state = "disconnected"
                    self._last_error, self._last_error_at = f"{type(exc).__name__}: {exc}"[:300], self._clock()
                    logger.warning("[STREAM] %s poll failed: %s", self.source_id, self._last_error)
                await self._sleep(self.interval_s)
        except asyncio.CancelledError:
            raise
