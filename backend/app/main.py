"""
backend/app/main.py
DataMend — FastAPI entrypoint of the rainfall time-series validation platform.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.auth import _same as auth_same, require_login, router as auth_router, session_valid_async as auth_session_valid
from backend.app import mcp_gateway
from backend.app.api.mcp_access import endpoint_router as mcp_endpoint_router, router as mcp_access_router
from backend.app.api.pipeline import router as pipeline_router
from backend.app.api.pipeline_explore import router as pipeline_explore_router
from backend.app.api.pipeline_import import router as pipeline_import_router
from backend.app.api.places import router as places_router
from backend.app.api.rainfall import router as rainfall_router
from backend.app.api.settings import router as settings_router
from backend.app.api.validation import router as validation_router
from backend.app.config import settings
from backend.app.db.database import close_db, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown: create the tables, start the live rain-gauge feed if it is configured."""
    logger.info("Initializing %s v%s database...", settings.PROJECT_NAME, settings.VERSION)
    await init_db()
    if os.environ.get("ENVIRONMENT", "").lower() == "production" and settings.ADMIN_PASSWORD == "admin":
        logger.warning("ADMIN_PASSWORD is still the public default 'admin' on a production deployment: anyone can sign in. Set ADMIN_EMAIL and ADMIN_PASSWORD.")
    from backend.app.pipeline.jobs import fail_interrupted_jobs
    try:
        n_cut = await fail_interrupted_jobs()
        if n_cut:
            logger.warning("%d ingest job(s) were interrupted by the restart and marked failed", n_cut)
    except Exception as exc:
        logger.warning("Could not clean up interrupted ingest jobs: %s", exc)

    from backend.app.api.rainfall import start_rainfall_service, stop_rainfall_service
    try:
        await start_rainfall_service()
    except Exception as exc:
        logger.warning("Rainfall feed start skipped: %s", exc)

    yield

    logger.info("Shutting down %s services...", settings.PROJECT_NAME)
    await stop_rainfall_service()
    await close_db()
    logger.info("Cleanup complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="DataMend: rainfall time-series data validation platform (rules, statistics and a neighbour check; no trained model).",
    lifespan=lifespan,
)

app.middleware("http")(require_login)          # added first, so CORS wraps it and a refusal still carries the CORS headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(places_router)
app.include_router(rainfall_router)
app.include_router(validation_router)
app.include_router(auth_router)
app.include_router(pipeline_router)
app.include_router(pipeline_import_router)
app.include_router(pipeline_explore_router)
app.include_router(settings_router)
app.include_router(mcp_access_router)
app.include_router(mcp_endpoint_router)
mcp_gateway.attach(app)                      # the platform's own narrator and MCP endpoint read the platform through this app


@app.get("/", tags=["system"])
async def root(request: Request):
    """Root health check. With REQUIRE_LOGIN on, an unauthenticated caller sees the status only (no project, version or paths)."""
    if settings.REQUIRE_LOGIN:
        tok = request.headers.get("x-admin-token")
        if not (await auth_session_valid(tok) or bool(settings.ADMIN_TOKEN and tok and auth_same(tok, settings.ADMIN_TOKEN))):
            return {"status": "online"}
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "api_prefix": settings.API_PREFIX,
    }
