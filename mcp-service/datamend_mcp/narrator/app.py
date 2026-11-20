"""HTTP front of the narrator: ``POST /narrate`` (also ``POST /``) with the narrator-request-v1 body, ``GET /health``.

Set the platform's NARRATOR_URL to ``http://<host>:<port>/narrate`` and NARRATOR_TOKEN to this service's NARRATOR_BEARER_TOKEN. Non-200 answers make the
platform store nothing and tell the user the narrator did not answer, which is the contract's behaviour.
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .. import security as sec
from ..config import Settings
from .agent import BadRequest, CannotAnswer, Narrator, Unavailable

MAX_BODY = 64 * 1024                       # the contract's request cap


def make_server(cfg: Settings, narrator: Narrator, host: Optional[str] = None, port: Optional[int] = None) -> ThreadingHTTPServer:
    limiter, audit = sec.RateLimiter(60), sec.AuditLog(cfg.mcp_audit_log)

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "datamend-narrator"

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

        def _json(self, code: int, obj: Any) -> None:
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self) -> None:
            if self.path == "/health":
                return self._json(200, {"status": "ok", "mode": narrator.mode})
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path.split("?")[0] not in ("/narrate", "/"):
                return self._json(404, {"error": "not found"})
            if cfg.narrator_bearer_token and not sec.check_bearer(self.headers.get("Authorization"), cfg.narrator_bearer_token):
                audit.record(event="narrator_request", ok=False, reason="unauthorised")
                return self._json(401, {"error": "bearer token required"})
            if not limiter.take():
                return self._json(429, {"error": "too many requests"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if n <= 0 or n > MAX_BODY:
                return self._json(413 if n > MAX_BODY else 400, {"error": "body must be 1 byte to 64 KB"})
            try:
                body = json.loads(self.rfile.read(n))
            except ValueError:
                return self._json(400, {"error": "body is not JSON"})
            try:
                out = narrator.respond(body)
            except BadRequest as e:
                return self._json(400, {"error": str(e)})
            except CannotAnswer as e:
                audit.record(event="narrator_request", ok=False, reason="cannot_answer", mode=narrator.mode)
                return self._json(501, {"error": str(e)})
            except Unavailable as e:
                audit.record(event="narrator_request", ok=False, reason="unavailable", detail=str(e)[:120], mode=narrator.mode)
                return self._json(502, {"error": str(e)})
            except Exception as e:                                         # never leak internals
                audit.record(event="narrator_request", ok=False, reason="internal", error=type(e).__name__)
                return self._json(500, {"error": "internal error"})
            audit.record(event="narrator_request", ok=True, kind=body.get("kind"), mode=narrator.mode, chars=len(out["text"]))
            self._json(200, out)

    return ThreadingHTTPServer((host or cfg.narrator_host, cfg.narrator_port if port is None else port), H)


def serve(cfg: Settings, narrator: Narrator) -> None:
    httpd = make_server(cfg, narrator)
    print(f"datamend-narrator: http://{httpd.server_address[0]}:{httpd.server_address[1]}/narrate  mode={narrator.mode}"
          + ("" if cfg.narrator_bearer_token else "  WARNING: NARRATOR_BEARER_TOKEN is empty, anyone who can reach this port can call it"), file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
