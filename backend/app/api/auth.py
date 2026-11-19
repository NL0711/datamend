"""Admin sign-in for the dashboard. One admin account (ADMIN_EMAIL and ADMIN_PASSWORD from the environment, never stored in the database).

A successful sign-in returns a random session token that the dashboard sends as X-Admin-Token, exactly like the older ADMIN_TOKEN, so every
write endpoint keeps one check (api/settings.py, require_admin). Sessions live in memory: a restart signs everyone out. Reading never needs a
sign-in. Wrong attempts are rate limited. There are no other accounts and no password reset.
"""
from __future__ import annotations

import hmac
import secrets
import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_TTL_S = 12 * 3600
MAX_FAILURES, WINDOW_S = 8, 300.0
_sessions: Dict[str, float] = {}
_failures: Deque[float] = deque()


def login_enabled() -> bool:
    return bool(settings.ADMIN_PASSWORD)


def session_valid(token: Optional[str]) -> bool:
    if not token:
        return False
    now = time.time()
    for t in [t for t, exp in _sessions.items() if exp <= now]:
        _sessions.pop(t, None)
    return token in _sessions


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


_OPEN_PATHS = ("/api/auth/login", "/api/auth/me", "/api/auth/logout")


async def require_login(request: Request, call_next):
    """Middleware: with REQUIRE_LOGIN on, every /api request needs a signed-in session (or the ADMIN_TOKEN, for scripts)."""
    path = request.url.path
    if settings.REQUIRE_LOGIN and path.startswith("/api/") and path not in _OPEN_PATHS and request.method != "OPTIONS":
        tok = request.headers.get("x-admin-token")
        ok = session_valid(tok) or bool(settings.ADMIN_TOKEN and tok and _same(tok, settings.ADMIN_TOKEN))
        if not ok:
            return JSONResponse({"detail": "sign in to use the dashboard"}, status_code=status.HTTP_401_UNAUTHORIZED)
    return await call_next(request)


class Credentials(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


@router.post("/login")
async def login(body: Credentials) -> Dict[str, object]:
    if not login_enabled():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin sign-in is switched off: set ADMIN_PASSWORD on the server")
    now = time.monotonic()
    while _failures and now - _failures[0] > WINDOW_S:
        _failures.popleft()
    if len(_failures) >= MAX_FAILURES:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many wrong attempts; wait a few minutes")
    ok_email = _same(body.email.strip().lower(), settings.ADMIN_EMAIL.strip().lower())
    ok_pw = _same(body.password, settings.ADMIN_PASSWORD)          # both compared, so timing does not reveal which was wrong
    if not (ok_email and ok_pw):
        _failures.append(now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the email or password is wrong")
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL_S
    return {"token": token, "email": settings.ADMIN_EMAIL, "expires_in": SESSION_TTL_S}


@router.get("/me")
async def me(x_admin_token: Optional[str] = Header(None)) -> Dict[str, object]:
    ok = session_valid(x_admin_token)
    return {"signed_in": ok, "email": settings.ADMIN_EMAIL if ok else None, "login_enabled": login_enabled()}


@router.post("/logout")
async def logout(x_admin_token: Optional[str] = Header(None)) -> Dict[str, bool]:
    if x_admin_token:
        _sessions.pop(x_admin_token, None)
    return {"signed_in": False}
