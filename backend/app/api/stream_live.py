"""Read-only endpoints behind the MCP tools `get_station_stream_v1` and `list_stream_detections_v1` (the current live feed of one station).

They sit under /api/validation/ so the in-process MCP client (GET only, read-only token) can reach them. Routes only parse and delegate to
`backend/app/stream/live_view.py`. Nothing here writes.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.database import get_db
from backend.app.stream import live_view, runtime

router = APIRouter(prefix="/api/validation/stream", tags=["stream-live"])


@router.get("/feed")
async def station_feed(station_id: str = Query(..., min_length=1, max_length=64), window: int = Query(live_view.DEFAULT_WINDOW, ge=1, le=live_view.MAX_WINDOW),
                       up_to_id: Optional[int] = Query(None, ge=1), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await live_view.feed_view(session, runtime.get_manager(), station_id, window, up_to_id)


@router.get("/detections")
async def station_detections(station_id: str = Query(..., min_length=1, max_length=64), limit: int = Query(live_view.DEFAULT_DETECTIONS, ge=1, le=live_view.MAX_DETECTIONS),
                             window: int = Query(live_view.DEFAULT_WINDOW, ge=1, le=live_view.MAX_WINDOW), up_to_id: Optional[int] = Query(None, ge=1),
                             session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await live_view.detections_view(session, runtime.get_manager(), station_id, limit, up_to_id, window)
