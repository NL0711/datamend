"""The process-wide stream manager and the one place sources are registered.

S3b registers the Open-Meteo, Weather Union and ESP32 sources here next to the simulator; none of them exists yet.
"""
from __future__ import annotations

from typing import Optional

from backend.app.stream.manager import StreamManager
from backend.app.stream.service import ReadingProcessor
from backend.app.stream.simulator import SimulatorSource

_manager: Optional[StreamManager] = None


def build_manager() -> StreamManager:
    manager = StreamManager(processor=ReadingProcessor())
    manager.register(SimulatorSource())
    return manager


def get_manager() -> StreamManager:
    global _manager
    if _manager is None:
        _manager = build_manager()
    return _manager


def set_manager(manager: Optional[StreamManager]) -> None:
    """Replace the manager (tests use this to run the API against a manager with a fast, seeded simulator)."""
    global _manager
    _manager = manager


async def shutdown() -> None:
    global _manager
    if _manager is not None:
        await _manager.shutdown()
        _manager = None
