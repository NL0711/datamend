"""Admin sign-in for the dashboard. One admin account (ADMIN_EMAIL and ADMIN_PASSWORD from the environment, never stored in the database).

A successful sign-in returns a random session token that the dashboard sends as X-Admin-Token, exactly like the older ADMIN_TOKEN, so every
write endpoint keeps one check (api/settings.py, require_admin). Sessions are stored (token hash only) in the ``admin_sessions`` table behind an in-memory cache, so a restart does not sign the admin out. With REQUIRE_LOGIN on
(the default) the ``require_login`` middleware below also refuses every other /api route without a session, so nothing is readable signed
out; only login, me and logout are open. Wrong attempts are rate limited. There are no other accounts and no password reset.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete

from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.validation.models import AdminSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

def session_ttl_s() -> int:
    return max(600, int(settings.SESSION_TTL_HOURS * 3600))


SESSION_COOKIE = "datamend_session"
_SIGNED_PREFIX = "v1."
_revoked: Dict[str, float] = {}                  # digests of signed tokens that were signed out, until they would have expired (this process only)
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


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _signing_key() -> bytes:
    """SESSION_SECRET when set; otherwise derived from the admin credentials, so changing the admin password signs every session out."""
    if settings.SESSION_SECRET:
        return settings.SESSION_SECRET.encode()
    return hashlib.sha256(f"datamend-session-v1|{settings.ADMIN_EMAIL}|{settings.ADMIN_PASSWORD}|{settings.ADMIN_TOKEN}".encode()).digest()


def _mac(body: str) -> str:
    return hmac.new(_signing_key(), body.encode(), hashlib.sha256).hexdigest()


def new_signed_token(expires_at: float) -> str:
    """A self-contained session token: ``v1.<expiry>.<random>.<hmac>``. It needs no database row, so a restart, redeploy or sleep on a host with an
    ephemeral disk does not sign the admin out; it only stops working at its expiry, when the secret changes, or when it is signed out here."""
    body = f"{_SIGNED_PREFIX}{int(expires_at)}.{secrets.token_urlsafe(9)}"
    return f"{body}.{_mac(body)}"


def signed_token_valid(token: Optional[str]) -> bool:
    if not token or not token.startswith(_SIGNED_PREFIX) or token.count(".") != 3 or not login_enabled():
        return False
    body, _, mac = token.rpartition(".")
    if not _same(mac, _mac(body)):
        return False
    try:
        exp = int(body.split(".")[1])
    except (ValueError, IndexError):
        return False
    return exp > time.time() and _digest(token) not in _revoked


async def _store_session(token: str, expires_at: float) -> None:
    try:
        async with async_session_factory() as s:
            await s.execute(delete(AdminSession).where(AdminSession.expires_at <= time.time()))
            s.add(AdminSession(token_hash=_digest(token), expires_at=expires_at))
            await s.commit()
    except Exception:                                    # the database is down: the session still works from memory until a restart
        logger.warning("could not store the admin session; it lasts until this server restarts", exc_info=True)


async def _forget_session(token: str) -> None:
    _sessions.pop(token, None)
    if token.startswith(_SIGNED_PREFIX):                 # a signed token cannot be deleted; remember it as signed out (until a restart of this process)
        now = time.time()
        for k in [k for k, exp in _revoked.items() if exp <= now]:
            _revoked.pop(k, None)
        try:
            _revoked[_digest(token)] = float(int(token.split(".")[1]))
        except (ValueError, IndexError):
            pass
    try:
        async with async_session_factory() as s:
            await s.execute(delete(AdminSession).where(AdminSession.token_hash == _digest(token)))
            await s.commit()
    except Exception:
        logger.warning("could not delete the stored admin session", exc_info=True)


def session_valid(token: Optional[str]) -> bool:
    """Memory-only check (the cache). Use ``session_valid_async`` where the database may know a session this process does not."""
    if not token:
        return False
    if signed_token_valid(token):
        return True
    now = time.time()
    for t in [t for t, exp in _sessions.items() if exp <= now]:
        _sessions.pop(t, None)
    return token in _sessions


async def session_valid_async(token: Optional[str]) -> bool:
    """The cache first, then the stored sessions (a session made before a restart, or by another instance)."""
    if session_valid(token):
        return True
    if not token:
        return False
    try:
        async with async_session_factory() as s:
            row = await s.get(AdminSession, _digest(token))
    except Exception:
        return False
    if row is None or row.expires_at <= time.time():
        return False
    _sessions[token] = row.expires_at
    return True


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# "/api/mcp" authenticates itself with an MCP access token (api/mcp_access.py), so it is not behind the session gate.
_OPEN_PATHS = ("/api/auth/login", "/api/auth/me", "/api/auth/logout", "/api/mcp")
# A random secret made at start, known only to this process: the in-process MCP tools present it to read the platform (GET under READ_ONLY_PREFIXES).
INTERNAL_READ_TOKEN = secrets.token_urlsafe(32)
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")      # the API's description is gated too


READ_ONLY_PREFIXES = ("/api/validation/", "/api/places/")


def _bearer(request: Request) -> Optional[str]:
    """The token of an `Authorization: Bearer ...` header, or None when there is no such header."""
    h = request.headers.get("authorization") or ""
    return h[7:].strip() if h[:7].lower() == "bearer " else None


def gated(path: str) -> bool:
    return (path.startswith("/api/") and path not in _OPEN_PATHS) or path in _DOC_PATHS


async def require_login(request: Request, call_next):
    """Middleware: with REQUIRE_LOGIN on, every /api request (and /docs, /redoc, /openapi.json) needs a signed-in session (or the ADMIN_TOKEN, for
    scripts). Wrong tokens count against the per-client limiter, so the ADMIN_TOKEN cannot be guessed without limit."""
    path = request.url.path
    if settings.REQUIRE_LOGIN and gated(path) and request.method != "OPTIONS":
        tok = request.headers.get("x-admin-token")
        client = client_key(request)
        if await session_valid_async(tok):
            return await call_next(request)
        internal = _bearer(request)                     # the in-process MCP tools: a secret only this process knows, so it is never a guess
        if internal is not None and request.method == "GET" and path.startswith(READ_ONLY_PREFIXES) and _same(internal, INTERNAL_READ_TOKEN):
            return await call_next(request)
        if too_many(_token_failures, client, TOKEN_MAX_FAILURES):
            return JSONResponse({"detail": "too many wrong tokens; wait a few minutes"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        if settings.ADMIN_TOKEN and tok and _same(tok, settings.ADMIN_TOKEN):
            return await call_next(request)
        bearer = _bearer(request)
        if bearer is not None and request.method == "GET" and path.startswith(READ_ONLY_PREFIXES):
            if settings.EVIDENCE_API_TOKEN and _same(bearer, settings.EVIDENCE_API_TOKEN):
                return await call_next(request)   # read-only: GET under /api/validation/ and /api/places/ only, never a write
        if tok or bearer is not None:                # a token was offered and it was wrong (or not allowed here): that is a guess
            record_failure(_token_failures, client)
        return JSONResponse({"detail": "sign in to use the dashboard"}, status_code=status.HTTP_401_UNAUTHORIZED)
    return await call_next(request)


class Credentials(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response) -> Dict[str, object]:
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
    ttl = session_ttl_s()
    token = new_signed_token(time.time() + ttl)             # signed, so it survives a restart with no database (the ephemeral disk of a free host)
    # the same token as an HttpOnly cookie, read ONLY by the telemetry WebSocket (a browser cannot set X-Admin-Token on one); HTTP routes ignore it
    response.set_cookie(SESSION_COOKIE, token, max_age=ttl, httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/")
    return {"token": token, "email": settings.ADMIN_EMAIL, "expires_in": ttl}


@router.get("/me")
async def me(x_admin_token: Optional[str] = Header(None)) -> Dict[str, object]:
    # a script holding ADMIN_TOKEN is accepted everywhere else, so it counts as signed in here too
    ok = await session_valid_async(x_admin_token) or bool(settings.ADMIN_TOKEN and x_admin_token and _same(x_admin_token, settings.ADMIN_TOKEN))
    return {"signed_in": ok, "email": settings.ADMIN_EMAIL if ok else None, "login_enabled": login_enabled()}


@router.post("/logout")
async def logout(request: Request, response: Response, x_admin_token: Optional[str] = Header(None)) -> Dict[str, bool]:
    for tok in {x_admin_token, request.cookies.get(SESSION_COOKIE)}:
        if tok:
            await _forget_session(tok)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"signed_in": False}
