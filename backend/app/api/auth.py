"""Admin sign-in for the dashboard. One admin account (ADMIN_EMAIL and ADMIN_PASSWORD from the environment, never stored in the database).

A successful sign-in returns a random session token that the dashboard sends as X-Admin-Token, exactly like the older ADMIN_TOKEN, so every
write endpoint keeps one check (api/settings.py, require_admin). Sessions live in memory: a restart signs everyone out. With REQUIRE_LOGIN on
(the default) the ``require_login`` middleware below also refuses every other /api route without a session, so nothing is readable signed
out; only login, me and logout are open. Wrong attempts are rate limited. There are no other accounts and no password reset.
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
TOKEN_MAX_FAILURES = 10
_MAX_CLIENTS = 5000
_sessions: Dict[str, float] = {}
_failures: Dict[str, Deque[float]] = {}          # wrong sign-in attempts, per client address
_token_failures: Dict[str, Deque[float]] = {}    # wrong ADMIN_TOKEN guesses (middleware and require_admin share it), per client address


def client_key(request: Request) -> str:
    """The address of the TCP peer. X-Forwarded-For is deliberately NOT read: any caller can set it, which would let an attacker dodge the limit
    or lock out someone else's address. Behind a trusted proxy, run uvicorn with --proxy-headers and --forwarded-allow-ips so the peer address is real."""
    return request.client.host if request.client else "unknown"


def too_many(bucket: Dict[str, Deque[float]], key: str, limit: int) -> bool:
    q = bucket.get(key)
    if q is None:
        return False
    now = time.monotonic()
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if not q:
        bucket.pop(key, None)
    return len(q) >= limit


def record_failure(bucket: Dict[str, Deque[float]], key: str) -> None:
    if len(bucket) >= _MAX_CLIENTS:                  # bounded memory: forget the idle addresses
        now = time.monotonic()
        for k in [k for k, q in bucket.items() if not q or now - q[-1] > WINDOW_S]:
            bucket.pop(k, None)
        if len(bucket) >= _MAX_CLIENTS:
            bucket.pop(next(iter(bucket)), None)
    bucket.setdefault(key, deque()).append(time.monotonic())


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
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")      # the API's description is gated too


def gated(path: str) -> bool:
    return (path.startswith("/api/") and path not in _OPEN_PATHS) or path in _DOC_PATHS


async def require_login(request: Request, call_next):
    """Middleware: with REQUIRE_LOGIN on, every /api request (and /docs, /redoc, /openapi.json) needs a signed-in session (or the ADMIN_TOKEN, for
    scripts). Wrong tokens count against the per-client limiter, so the ADMIN_TOKEN cannot be guessed without limit."""
    path = request.url.path
    if settings.REQUIRE_LOGIN and gated(path) and request.method != "OPTIONS":
        tok = request.headers.get("x-admin-token")
        client = client_key(request)
        if session_valid(tok):
            return await call_next(request)
        if too_many(_token_failures, client, TOKEN_MAX_FAILURES):
            return JSONResponse({"detail": "too many wrong tokens; wait a few minutes"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        if settings.ADMIN_TOKEN and tok and _same(tok, settings.ADMIN_TOKEN):
            return await call_next(request)
        if tok:                                      # a token was offered and it was wrong: that is a guess
            record_failure(_token_failures, client)
        return JSONResponse({"detail": "sign in to use the dashboard"}, status_code=status.HTTP_401_UNAUTHORIZED)
    return await call_next(request)


class Credentials(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


@router.post("/login")
async def login(body: Credentials, request: Request) -> Dict[str, object]:
    if not login_enabled():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin sign-in is switched off: set ADMIN_PASSWORD on the server")
    client = client_key(request)                                    # per client address: one client cannot lock the admin out for everyone
    if too_many(_failures, client, MAX_FAILURES):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many wrong attempts; wait a few minutes")
    ok_email = _same(body.email.strip().lower(), settings.ADMIN_EMAIL.strip().lower())
    ok_pw = _same(body.password, settings.ADMIN_PASSWORD)          # both compared, so timing does not reveal which was wrong
    if not (ok_email and ok_pw):
        record_failure(_failures, client)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the email or password is wrong")
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL_S
    return {"token": token, "email": settings.ADMIN_EMAIL, "expires_in": SESSION_TTL_S}


@router.get("/me")
async def me(x_admin_token: Optional[str] = Header(None)) -> Dict[str, object]:
    # a script holding ADMIN_TOKEN is accepted everywhere else, so it counts as signed in here too
    ok = session_valid(x_admin_token) or bool(settings.ADMIN_TOKEN and x_admin_token and _same(x_admin_token, settings.ADMIN_TOKEN))
    return {"signed_in": ok, "email": settings.ADMIN_EMAIL if ok else None, "login_enabled": login_enabled()}


@router.post("/logout")
async def logout(x_admin_token: Optional[str] = Header(None)) -> Dict[str, bool]:
    if x_admin_token:
        _sessions.pop(x_admin_token, None)
    return {"signed_in": False}
