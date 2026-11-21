"""A minimal MCP client (stdio child process or Streamable HTTP), used by the narrator to call the DataMend MCP server.

Every tools/list answer is checked before the tools are used: names must be on the allow-list, descriptions are scanned for instruction-like text, and,
when a lock file is given, each definition must match its pinned hash (a changed or extra tool is refused: the rug-pull and tool-squatting guard).
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import security as sec

PROTOCOL = "2025-06-18"


class McpClientError(RuntimeError):
    pass


class _Base:
    def __init__(self, timeout: float) -> None:
        self.timeout, self._id, self._lock = timeout, 0, threading.RLock()
        self._ready = False

    def _request(self, method: str, params: Optional[Dict[str, Any]], timeout: float) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def _notify(self, method: str) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def connect(self) -> Dict[str, Any]:
        with self._lock:
            r = self._request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "datamend-narrator", "version": "0.1.0"}}, self.timeout)
            self._notify("notifications/initialized")
            self._ready = True
            return r

    def list_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            if not self._ready:
                self.connect()
            return self._request("tools/list", {}, self.timeout).get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        with self._lock:
            if not self._ready:
                self.connect()
            r = self._request("tools/call", {"name": name, "arguments": arguments}, timeout or self.timeout)
        text = "".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        return {"is_error": bool(r.get("isError")), "text": text, "structured": r.get("structuredContent")}

    def read_resource(self, uri: str) -> str:
        with self._lock:
            if not self._ready:
                self.connect()
            r = self._request("resources/read", {"uri": uri}, self.timeout)
        return "".join(c.get("text", "") for c in r.get("contents", []))

    def close(self) -> None:
        pass


class StdioMcpClient(_Base):
    def __init__(self, cmd: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None, timeout: float = 15.0) -> None:
        super().__init__(timeout)
        self.cmd, self.env, self.cwd = cmd, env, cwd
        self._proc: Optional[subprocess.Popen] = None
        self._q: "queue.Queue[Optional[str]]" = queue.Queue()

    def _start(self) -> None:
        self.close()
        self._q = queue.Queue()
        self._proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1,
                                      env=self.env, cwd=self.cwd)
        proc, q = self._proc, self._q

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                q.put(line)
            q.put(None)
        threading.Thread(target=pump, daemon=True).start()
        self._ready = False

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _send(self, obj: Dict[str, Any]) -> None:
        if not self._alive():
            self._start()
            self._ready = False if obj.get("method") == "initialize" else self._ready
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise McpClientError("the MCP server process is not running")

    def _request(self, method: str, params: Optional[Dict[str, Any]], timeout: float) -> Any:
        if not self._alive() and method != "initialize":
            self._ready = False
            self.connect()
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        while True:
            try:
                line = self._q.get(timeout=timeout)
            except queue.Empty:
                raise McpClientError(f"the MCP server did not answer {method} in {timeout:g} s")
            if line is None:
                raise McpClientError("the MCP server process ended")
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("id") == rid:
                if "error" in m:
                    raise McpClientError(f"MCP error {m['error'].get('code')}: {m['error'].get('message')}")
                return m.get("result", {})

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def close(self) -> None:
        p, self._proc = self._proc, None
        if p is not None and p.poll() is None:
            try:
                if p.stdin:
                    p.stdin.close()
                p.wait(timeout=3)
            except Exception:
                p.kill()


class HttpMcpClient(_Base):
    def __init__(self, url: str, token: str = "", timeout: float = 15.0) -> None:
        super().__init__(timeout)
        if not url.startswith(("http://", "https://")):
            raise McpClientError("NARRATOR_MCP_URL must be an http or https URL")
        self.url, self.token = url, token

    def _post(self, obj: Dict[str, Any], timeout: float) -> Optional[Dict[str, Any]]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.url, data=json.dumps(obj).encode(), headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(2 * 1024 * 1024)
                return json.loads(raw) if r.status == 200 and raw else None
        except urllib.error.HTTPError as e:
            raise McpClientError(f"the MCP server answered HTTP {e.code}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise McpClientError(f"cannot reach the MCP server ({type(e).__name__})")

    def _request(self, method: str, params: Optional[Dict[str, Any]], timeout: float) -> Any:
        rid = self._next_id()
        m = self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}, timeout)
        if not m or m.get("id") != rid:
            raise McpClientError(f"no answer to {method}")
        if "error" in m:
            raise McpClientError(f"MCP error {m['error'].get('code')}: {m['error'].get('message')}")
        return m.get("result", {})

    def _notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method}, self.timeout)


def vet_tools(tools: List[Dict[str, Any]], lock: Optional[Dict[str, str]] = None, allow: Optional[set] = None) -> List[Dict[str, Any]]:
    """Return only tools that are safe to hand to a model; raise on a pin mismatch."""
    if lock is not None:
        sec.verify_manifest(tools, lock)
    safe = []
    for t in tools:
        if allow is not None and t.get("name") not in allow:
            continue
        if sec.scan_definition(t):
            continue
        a = t.get("annotations") or {}
        if a.get("readOnlyHint") is not True:
            continue
        safe.append(t)
    return safe


def default_stdio_client(env_extra: Optional[Dict[str, str]] = None, timeout: float = 15.0) -> StdioMcpClient:
    root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    env.update(env_extra or {})
    return StdioMcpClient([sys.executable, "-m", "datamend_mcp", "serve", "--transport", "stdio"], env=env, cwd=root, timeout=timeout)
