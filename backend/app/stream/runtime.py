"""The process-wide stream manager and the one place sources are registered.

Registered: the simulator (S3a) and the Open-Meteo, Weather Union and ESP32 sources (S3b). Their settings come from stream_settings.py through
control.py. Nothing starts on its own unless an active source was saved in the settings (``autostart``).
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.app.stream import control
from backend.app.stream.esp32 import Esp32Source
from backend.app.stream.manager import StreamManager
from backend.app.stream.open_meteo import OpenMeteoSource
from backend.app.stream.service import ReadingProcessor
from backend.app.stream.simulator import SimulatorSource
from backend.app.stream.wu_source import WeatherUnionSource

logger = logging.getLogger(__name__)
_manager: Optional[StreamManager] = None


def build_manager() -> StreamManager:
    manager = StreamManager(processor=ReadingProcessor())
    manager.register(SimulatorSource())
    manager.register(OpenMeteoSource())
    manager.register(WeatherUnionSource())
    manager.register(Esp32Source())
    try:
        control.configure_sources(manager)
    except Exception:
        logger.exception("the stream settings could not be applied to the sources")
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


async def autostart() -> None:
    await control.autostart(get_manager())


async def shutdown() -> None:
    global _manager
    if _manager is not None:
        await _manager.shutdown()
        _manager = None
