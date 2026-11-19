"""SQLAlchemy models for the Locations feature (registered on the shared declarative Base)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_km: Mapped[float] = mapped_column(Float, nullable=False, default=15.0)
    preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    cells: Mapped[List["LocationCell"]] = relationship(
        "LocationCell", back_populates="location", cascade="all, delete-orphan", lazy="selectin",
        order_by="LocationCell.cell_row, LocationCell.cell_col")


class LocationCell(Base):
    __tablename__ = "location_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), index=True, nullable=False)
    cell_row: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_col: Mapped[int] = mapped_column(Integer, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    is_land: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    client: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    held_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    location: Mapped[Location] = relationship("Location", back_populates="cells")

    __table_args__ = (Index("ix_location_cells_rc", "cell_row", "cell_col"),)


class CellNormals(Base):
    """Day-of-year normals of one grid cell, built once from the provider's 1991-2020 daily history."""
    __tablename__ = "cell_normals"

    cell_row: Mapped[int] = mapped_column(Integer, primary_key=True)
    cell_col: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    grid_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    grid_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SeriesCache(Base):
    """The latest fetched hourly series of one location (a short-lived cache)."""
    __tablename__ = "location_series_cache"

    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
