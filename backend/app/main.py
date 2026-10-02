"""
backend/app/main.py
SkyGuard AI — Master FastAPI Application Entrypoint & Lifespan Management.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router as api_router
from backend.app.api.websocket import router as ws_router
from backend.app.config import settings
from backend.app.db.database import close_db, init_db
from backend.app.services.simulation_service import simulation_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown events."""
    logger.info("Initializing %s v%s database...", settings.PROJECT_NAME, settings.VERSION)
    await init_db()
    logger.info("Database initialized successfully.")

    # Auto-start configured default data source so telemetry streams immediately upon launch
    from backend.app.sources.manager import data_source_manager
    try:
        await data_source_manager.start()
        logger.info("Telemetry data source manager auto-started.")
    except Exception as exc:
        logger.warning("Data source manager auto-start warning: %s", exc)

    yield

    logger.info("Shutting down %s services...", settings.PROJECT_NAME)
    await data_source_manager.stop()
    await close_db()
    logger.info("Cleanup complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="SkyGuard AI Real-Time Anomaly Detection & Sensor Health System for Automatic Weather Stations",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST and WebSocket routers
app.include_router(api_router)
app.include_router(ws_router)


@app.get("/", tags=["system"])
async def root():
    """Root health check and service metadata endpoint."""
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "api_prefix": settings.API_PREFIX,
    }
