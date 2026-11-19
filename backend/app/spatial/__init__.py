"""
backend/app/spatial package initialization.
"""
from backend.app.spatial.consensus import (
    SpatialConsensusEngine,
    SpatialConsensusResult,
    haversine_distance_km,
    spatial_consensus_engine,
)

__all__ = [
    "SpatialConsensusEngine",
    "SpatialConsensusResult",
    "haversine_distance_km",
    "spatial_consensus_engine",
]
