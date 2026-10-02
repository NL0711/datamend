"""
backend/app/sources/__init__.py
SkyGuard AI — Data Source Abstraction Layer Package.
"""

from backend.app.sources.base import BaseDataSource
from backend.app.sources.external_source import ExternalWeatherDataSource
from backend.app.sources.manager import DataSourceManager, data_source_manager
from backend.app.sources.physical_source import PhysicalAWSDataSource
from backend.app.sources.simulated_source import SimulatedDataSource

__all__ = [
    "BaseDataSource",
    "SimulatedDataSource",
    "ExternalWeatherDataSource",
    "PhysicalAWSDataSource",
    "DataSourceManager",
    "data_source_manager",
]
