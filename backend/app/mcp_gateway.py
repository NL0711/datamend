"""The platform's own MCP endpoint: other people's agents (Claude and so on) connect over HTTP and read the platform's results.

The MCP server itself is the one in ``mcp-service/`` (read-only tools, pinned tool definitions, injection filtering, an audit log). This module
only hosts it inside the backend so one deployment serves both, and swaps its HTTP client for an in-process one:

  * ``InProcessClient`` reads the platform's own API through the ASGI app (no socket, no second process). It is read-only by construction: ``get``
    is the only method, and only paths under /api/validation/ and /api/places/ are allowed. It presents ``auth.INTERNAL_READ_TOKEN``, a secret made at
    start that only this process knows, so the tools work whether or not the platform requires a sign-in, and a caller outside cannot use it.
  * The tools run in a worker thread (the server core is synchronous) and hand each read back to the running event loop.

If ``mcp-service/`` is missing (a slim image), ``AVAILABLE`` is False and the endpoints answer 503; nothing else is affected.
"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from backend.app.api.auth import INTERNAL_READ_TOKEN
from backend.app.config import settings

MCP_DIR = Path(__file__).resolve().parents[2] / "mcp-service"
LOCK_PATH = MCP_DIR / "tool_manifest.lock.json"
READ_PREFIXES = ("/api/validation/", "/api/places/")
MAX_RESPONSE = 2 * 1024 * 1024
TOKEN_PREFIX = "dmcp_"

if (MCP_DIR / "datamend_mcp").is_dir() and str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))
try:
    from datamend_mcp import config as mcp_config, security as mcp_sec
    from datamend_mcp.client import DataMendError
    from datamend_mcp.protocol import McpServer
    from datamend_mcp.tools import Registry
    AVAILABLE = True
except ImportError:                                           # pragma: no cover - only without mcp-service on disk
    AVAILABLE = False


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def allowed_origins() -> List[str]:
    return [o.strip() for o in settings.MCP_ALLOWED_ORIGINS.split(",") if o.strip()]


def tool_listing() -> List[Dict[str, str]]:
    return [{"name": t["name"], "description": t["description"]} for t in Registry().listing()] if AVAILABLE else []


class InProcessClient:
    """Stands in for ``datamend_mcp.client.DataMendClient``: ``get(path, params)`` against this app, read-only."""

    def __init__(self) -> None:
        self.app: Any = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def _aget(self, path: str, params: Optional[Dict[str, Any]]) -> Any:
        q = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://platform.internal", timeout=20.0) as c:
            r = await c.get(path, params=q, headers={"Authorization": "Bearer " + INTERNAL_READ_TOKEN, "Accept": "application/json"})
        if r.status_code != 200:
            try:
                detail = str(r.json().get("detail", ""))[:200]
            except Exception:
                detail = ""
            raise DataMendError(r.status_code, detail or "request failed")
        if len(r.content) > MAX_RESPONSE:
            raise DataMendError(502, "response larger than 2 MB refused")
        try:
            return r.json()
        except ValueError:
            raise DataMendError(502, "the platform did not return JSON")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Called from the tool's worker thread; the read itself runs on the event loop."""
        if not path.startswith(READ_PREFIXES):
            raise ValueError("only the platform's read-only validation and places paths are reachable")
        if self.loop is None or self.app is None:
            raise DataMendError(0, "the MCP gateway is not attached to a running app")
        return asyncio.run_coroutine_threadsafe(self._aget(path, params), self.loop).result(timeout=25)


_server: Optional["McpServer"] = None


def reset() -> None:
    """Forget the cached server (tests change the audit log path between runs)."""
    global _server, _narrator
    _server = _narrator = None


def get_server(app: Any, loop: asyncio.AbstractEventLoop) -> "McpServer":
    """The one MCP server, built on first use and attached to the app and loop of the current request."""
    global _server
    if not AVAILABLE:
        raise RuntimeError("mcp-service is not installed on this server")
    if _server is None:
        cfg = mcp_config.Settings(datamend_base_url="http://platform.internal", mcp_audit_log=settings.MCP_AUDIT_LOG, mcp_rate_per_minute=settings.MCP_RATE_PER_MINUTE,
                                  mcp_manifest_lock=str(LOCK_PATH), mcp_enforce_manifest=True)
        _server = McpServer(cfg, client=InProcessClient(), registry=Registry(), lock=mcp_sec.load_lock(str(LOCK_PATH)))
    _server.client.app, _server.client.loop = app, loop
    return _server


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------- the platform's own narrator
_app: Any = None
_narrator: Any = None


def attach(app: Any) -> None:
    """Remember the FastAPI app (called once from main.py) so the embedded narrator can read the platform without a request in hand."""
    global _app
    _app = app


if AVAILABLE:
    from datamend_mcp.mcp_client import McpClientError, _Base as _McpClientBase
    from datamend_mcp.narrator.agent import BadRequest, CannotAnswer, Narrator, Unavailable

    from backend.app.validation.explain import Explanation, NarratorExplainer, NarratorUnavailable, allowed_checks

    class InProcessMcpClient(_McpClientBase):
        """The narrator's MCP client without a transport: each message goes straight to the in-process MCP server."""

        def __init__(self, server: "McpServer", timeout: float = 15.0) -> None:
            super().__init__(timeout)
            self.server = server

        def _request(self, method: str, params: Optional[Dict[str, Any]], timeout: float) -> Any:
            reply = self.server.handle({"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params or {}})
            if reply is None or "error" in reply:
                raise McpClientError(str((reply or {}).get("error", {}).get("message", "no reply from the MCP server")))
            return reply["result"]

        def _notify(self, method: str) -> None:
            self.server.handle({"jsonrpc": "2.0", "method": method})

    class EmbeddedNarrator(NarratorExplainer):
        """The platform's own narrator: the one in mcp-service run in this process, so the AI chat and "Explain (AI)" need no second service.
        Without ANTHROPIC_API_KEY it is GROUNDED (text composed from the evidence and platform data by fixed rules, no language model) and answers
        only the questions its rules cover; with the key a language model answers (the evidence then leaves this server for Anthropic).
        Same request and reply contract as a remote narrator, so everything downstream is unchanged."""

        def __init__(self) -> None:                                  # no URL: nothing is called over the network except Anthropic in LLM mode
            self.url, self.token, self.timeout, self._transport = "embedded", "", float(settings.NARRATOR_TIMEOUT_SECONDS), None

        @property
        def host(self) -> str:
            return "this server (embedded)"

        @property
        def mode(self) -> str:
            return "llm" if settings.ANTHROPIC_API_KEY.strip() else "grounded"

        def _build(self, loop: asyncio.AbstractEventLoop) -> Any:
            global _narrator
            server = get_server(_app, loop)
            if _narrator is None:
                cfg = mcp_config.Settings(datamend_base_url="http://platform.internal", mcp_audit_log=settings.MCP_AUDIT_LOG, narrator_timeout_s=min(18.0, self.timeout),
                                          anthropic_api_key=settings.ANTHROPIC_API_KEY.strip(), narrator_llm_model=settings.NARRATOR_LLM_MODEL)
                _narrator = Narrator(cfg, InProcessMcpClient(server), lock=mcp_sec.load_lock(str(LOCK_PATH)))
            return _narrator

        async def explain(self, evidence: Optional[Dict[str, Any]], question: Optional[str] = None, kind: str = "explain",
                          context: Optional[Dict[str, Any]] = None) -> Explanation:
            import json

            from fastapi.concurrency import run_in_threadpool
            if _app is None:
                raise NarratorUnavailable("the embedded narrator is not attached to the app")
            body: Dict[str, Any] = {"schema": "narrator-request-v1", "kind": kind}
            if evidence is not None:
                body["evidence"] = evidence
            if question:
                body["question"] = question
            if context:
                body["context"] = context
            narrator = self._build(asyncio.get_running_loop())
            try:
                out = await run_in_threadpool(narrator.respond, body)
            except (BadRequest, CannotAnswer, Unavailable) as e:
                raise NarratorUnavailable(str(e))
            return self._parse(json.dumps(out).encode(), allowed_checks(evidence, context))


def embedded_narrator() -> Optional[Any]:
    """The platform's own narrator, or None when it is switched off (NARRATOR_EMBEDDED=false) or mcp-service is not installed."""
    if not (AVAILABLE and settings.NARRATOR_EMBEDDED and _app is not None):
        return None
    return EmbeddedNarrator()
