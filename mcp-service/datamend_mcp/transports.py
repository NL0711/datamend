"""Transports of the MCP server: stdio (a local client starts the server as a child process) and Streamable HTTP (POST /mcp, JSON replies).

Streamable HTTP here is the request/response subset: every POST is answered with application/json (or 202 for a notification); GET /mcp answers 405
(no server-initiated stream is offered). The HTTP transport refuses to start without a bearer token, checks the Origin header, and caps the body.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from . import security as sec
from .protocol import INVALID_REQUEST, PARSE_ERROR, McpServer, _err

MAX_BODY = 1024 * 1024


def serve_stdio(server: McpServer, stdin=None, stdout=None) -> None:
    """Newline-delimited JSON-RPC on stdin/stdout. Logs go to stderr only: anything else on stdout would corrupt the protocol."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out: Any = _err(None, PARSE_ERROR, "parse error")
        else:
            if isinstance(msg, list):
                out = [r for r in (server.handle(m) for m in msg) if r is not None] or None
            else:
                out = server.handle(msg)
        if out is not None:
            stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()


def make_http_server(server: McpServer, host: str, port: int) -> ThreadingHTTPServer:
    cfg = server.cfg
    if not cfg.mcp_bearer_token:
        raise sec.SecurityError("MCP_BEARER_TOKEN must be set to use the HTTP transport (it carries read access to the platform's data)")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "datamend-mcp"

        def log_message(self, fmt: str, *args: Any) -> None:          # keep the console quiet; the audit log is the record
            pass

        def _send(self, code: int, body: Optional[bytes] = None, ctype: str = "application/json", headers: Optional[dict] = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body or b"")))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _gate(self) -> bool:
            if not sec.origin_allowed(self.headers.get("Origin"), cfg.mcp_allowed_origins):
                self._send(403, b'{"error":"origin not allowed"}')
                return False
            if not sec.check_bearer(self.headers.get("Authorization"), cfg.mcp_bearer_token):
                self._send(401, b'{"error":"bearer token required"}', headers={"WWW-Authenticate": "Bearer"})
                return False
            return True

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, b'{"status":"ok"}')
            elif self.path.split("?")[0] == "/mcp":
                if self._gate():
                    self._send(405, b'{"error":"this server does not offer a GET stream"}', headers={"Allow": "POST"})
            else:
                self._send(404, b'{"error":"not found"}')

        def do_POST(self) -> None:
            if self.path.split("?")[0] != "/mcp":
                return self._send(404, b'{"error":"not found"}')
            if not self._gate():
                return
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if n <= 0 or n > MAX_BODY:
                return self._send(413 if n > MAX_BODY else 400, b'{"error":"body must be 1 byte to 1 MB"}')
            try:
                msg = json.loads(self.rfile.read(n))
            except ValueError:
                return self._send(400, json.dumps(_err(None, PARSE_ERROR, "parse error")).encode())
            if isinstance(msg, list):
                out: Any = [r for r in (server.handle(m) for m in msg) if r is not None] or None
            else:
                out = server.handle(msg)
            if out is None:
                return self._send(202)
            self._send(200, json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode())

        def do_DELETE(self) -> None:
            self._send(405, b'{"error":"no sessions to terminate"}', headers={"Allow": "POST"})

    return ThreadingHTTPServer((host, port), Handler)


def serve_http(server: McpServer, host: str, port: int) -> None:
    httpd = make_http_server(server, host, port)
    print(f"datamend-mcp: Streamable HTTP on http://{host}:{httpd.server_address[1]}/mcp (bearer token required)", file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
