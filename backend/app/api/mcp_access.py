"""MCP access for other people's agents: tokens made in Settings, and the MCP endpoint they connect to.

  * ``/api/settings/mcp``: list the tokens (never the token itself), make one (shown once, stored as a hash), revoke one. Making and revoking
    need the admin sign-in; the list needs a signed-in session like every other read.
  * ``POST /api/mcp``: Streamable HTTP, request/response only (JSON replies, 202 for a notification, 405 for GET and DELETE: no server-initiated
    stream, no sessions). Authenticated by an MCP token only; a session or the admin token does not open it. The tools are read-only
    (mcp-service/README.md): they list runs, flagged rows and evidence, and cannot change anything.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import mcp_gateway as gw
from backend.app.api import auth as auth_api
from backend.app.api.settings import require_admin
from backend.app.config import settings
from backend.app.db.database import get_db
from backend.app.validation.models import McpToken

router = APIRouter(prefix="/api/settings/mcp", tags=["mcp"])
endpoint_router = APIRouter(tags=["mcp"])
MAX_BODY = 1024 * 1024
LAST_USED_EVERY_S = 60


def _row(t: McpToken) -> Dict[str, Any]:
    return {"id": t.id, "label": t.label, "prefix": t.prefix, "created_at": t.created_at.isoformat() if t.created_at else None,
            "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None, "revoked_at": t.revoked_at.isoformat() if t.revoked_at else None}


def _need_service() -> None:
    if not gw.AVAILABLE:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "the MCP service files (mcp-service/) are not installed on this server")


async def _active_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(McpToken).where(McpToken.revoked_at.is_(None)))).scalar_one())


@router.get("")
async def mcp_state(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    tokens = list((await session.execute(select(McpToken).order_by(McpToken.id.desc()))).scalars())
    return {"available": gw.AVAILABLE, "endpoint_path": "/api/mcp", "read_only": True, "transport": "Streamable HTTP (JSON replies)",
            "tokens": [_row(t) for t in tokens], "active": sum(1 for t in tokens if t.revoked_at is None), "max_tokens": settings.MCP_MAX_TOKENS,
            "rate_per_minute": settings.MCP_RATE_PER_MINUTE, "tools": gw.tool_listing()}


class NewToken(BaseModel):
    label: str = Field(min_length=1, max_length=80)

    @field_validator("label")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = v.strip()
        if not v or any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("the label must be 1 to 80 characters with no control characters")
        return v


@router.post("/tokens", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_token(body: NewToken, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    _need_service()
    if await _active_count(session) >= settings.MCP_MAX_TOKENS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{settings.MCP_MAX_TOKENS} active tokens already exist; revoke one first")
    token = gw.new_token()
    row = McpToken(label=body.label, prefix=token[:12], token_hash=gw.hash_token(token))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {**_row(row), "token": token, "note": "this is the only time the token is shown"}


@router.delete("/tokens/{token_id}", dependencies=[Depends(require_admin)])
async def revoke_token(token_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await session.get(McpToken, token_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"token {token_id} not found")
    if row.revoked_at is None:
        row.revoked_at = gw.utcnow()
        await session.commit()
    return {"revoked": True, **_row(row)}


# ---------------------------------------------------------------------------------------------- the endpoint
def _rpc_error(code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}}


@endpoint_router.post("/api/mcp")
async def mcp_endpoint(request: Request, session: AsyncSession = Depends(get_db)) -> Response:
    _need_service()
    if request.headers.get("origin") is not None and request.headers["origin"] not in gw.allowed_origins():
        return JSONResponse({"error": "origin not allowed"}, status_code=status.HTTP_403_FORBIDDEN)
    client = auth_api.client_key(request)
    header = request.headers.get("authorization") or ""
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""
    if token and auth_api.too_many(auth_api._token_failures, client, auth_api.TOKEN_MAX_FAILURES):
        return JSONResponse({"error": "too many wrong tokens; wait a few minutes"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
    row = None
    if token:
        row = (await session.execute(select(McpToken).where(McpToken.token_hash == gw.hash_token(token), McpToken.revoked_at.is_(None)))).scalar_one_or_none()
    if row is None:
        if token:
            auth_api.record_failure(auth_api._token_failures, client)
        return JSONResponse({"error": "a valid MCP access token is required (Settings, MCP access)"}, status_code=status.HTTP_401_UNAUTHORIZED,
                            headers={"WWW-Authenticate": "Bearer"})
    now = gw.utcnow()
    if row.last_used_at is None or (now - row.last_used_at.replace(tzinfo=row.last_used_at.tzinfo or now.tzinfo)).total_seconds() > LAST_USED_EVERY_S:
        row.last_used_at = now
        await session.commit()

    raw = await request.body()
    if len(raw) > MAX_BODY:
        return JSONResponse(_rpc_error(-32600, "body larger than 1 MB"), status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    try:
        msg = json.loads(raw)
    except ValueError:
        return JSONResponse(_rpc_error(-32700, "parse error"), status_code=status.HTTP_400_BAD_REQUEST)

    server = gw.get_server(request.app, asyncio.get_running_loop())

    def run() -> Any:
        if isinstance(msg, list):
            return [r for r in (server.handle(m) for m in msg) if r is not None] or None
        return server.handle(msg)

    out = await run_in_threadpool(run)
    if out is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return JSONResponse(out)


@endpoint_router.get("/api/mcp")
@endpoint_router.delete("/api/mcp")
async def mcp_not_offered() -> Response:
    """No server-initiated stream and no sessions: GET and DELETE are not offered (the spec allows this)."""
    return JSONResponse({"error": "this endpoint answers POST only"}, status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "POST"})
