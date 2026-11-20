"""Security controls, one per threat from the seminar (tool poisoning, rug pull, prompt injection, weak authentication, over-broad access).

* Least privilege .......... ``assert_read_only``: every registered tool must declare readOnlyHint; the server has no write tool at all.
* Rug pull / tool poisoning  ``manifest`` + ``verify_manifest``: each tool definition (name, description, schema, annotations) is hashed and pinned in
                             a lock file; a changed definition is refused by the server and by the narrator's MCP client.
* Poisoned descriptions .... ``scan_definition``: tool descriptions seen by a client are scanned for instruction-like text.
* Prompt / retrieval injection  ``sanitize_value``: every string that came from an uploaded file (station ids, notes, reasons) is stripped of control and
                             bidirectional characters, length-capped, and instruction-like phrases are replaced and reported in ``security_flags``.
* Authentication ........... constant-time bearer check (``check_bearer``) and an Origin allow-list on the HTTP transport.
* Abuse .................... ``RateLimiter`` (sliding window) and ``AuditLog`` (one JSON line per tool call, arguments capped, no secrets).

None of this makes an LLM immune to injection; it removes the cheap routes and records what happened (see docs/mcp, "Limits").
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
import unicodedata
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

MAX_STR = 400                    # longest string a tool result may carry
MAX_RESULT_BYTES = 48 * 1024

# Phrases that try to give an LLM orders. Matched case-insensitively on text that should be plain data.
_INJECTION = [re.compile(p, re.I) for p in (
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts?|rules)",
    r"disregard (all |any |the )?(previous|prior|above|earlier)",
    r"forget (everything|all|your) (instructions|rules|above)",
    r"you are now\b",
    r"\bnew (system )?instructions?\b",
    r"^\s*(system|assistant|developer)\s*:",
    r"<\s*/?\s*(system|instructions?|tool_call|function_call)\b",
    r"\b(reveal|print|show|send|exfiltrate)\b.{0,40}\b(api[ _-]?key|token|password|secret|system prompt)\b",
    r"\bcall (the )?\w+ tool\b",
    r"\bdo not (tell|inform|mention to) the user\b",
    r"\bmark (this|these|all) (row|rows|readings?)\b.{0,30}\b(ok|fine|valid|clean)\b",
)]
_INVISIBLE = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD}
_BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
REMOVED = "[removed: instruction-like text]"


class SecurityError(RuntimeError):
    pass


class ManifestMismatch(SecurityError):
    pass


# --------------------------------------------------------------------------------------------------------- text
def clean_text(s: str, max_len: int = MAX_STR) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if o in _INVISIBLE or o in _BIDI:
            continue
        if unicodedata.category(ch) in ("Cc", "Cf") and ch not in "\n\t":
            continue
        out.append(ch)
    t = "".join(out).strip()
    return t if len(t) <= max_len else t[: max_len - 1] + "…"


def find_injection(s: str) -> List[str]:
    return [p.pattern for p in _INJECTION if p.search(s)]


def sanitize_text(s: str, max_len: int = MAX_STR) -> Tuple[str, List[str]]:
    t = clean_text(s, max_len)
    hits = find_injection(t)
    for p in _INJECTION:
        t = p.sub(REMOVED, t)
    return t, hits


def sanitize_value(v: Any, flags: Optional[List[Dict[str, Any]]] = None, path: str = "", depth: int = 0) -> Any:
    """Recursively sanitise every string in a JSON value. Appends {path, patterns} to ``flags`` for each injection-like string."""
    if flags is None:
        flags = []
    if depth > 12:
        return None
    if isinstance(v, str):
        t, hits = sanitize_text(v)
        if hits:
            flags.append({"path": path or "$", "patterns": len(hits)})
        return t
    if isinstance(v, list):
        return [sanitize_value(x, flags, f"{path}[{i}]", depth + 1) for i, x in enumerate(v[:500])]
    if isinstance(v, dict):
        return {clean_text(str(k), 80): sanitize_value(x, flags, f"{path}.{k}" if path else str(k), depth + 1) for k, x in list(v.items())[:200]}
    return v


# --------------------------------------------------------------------------------------------------------- tool definitions
def definition_of(tool: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a tools/list entry that a client trusts: everything that can steer a model."""
    return {"name": tool.get("name"), "description": tool.get("description"), "inputSchema": tool.get("inputSchema"),
            "annotations": tool.get("annotations") or {}}


def digest(tool: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(definition_of(tool), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def manifest(tools: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    return {t["name"]: digest(t) for t in sorted(tools, key=lambda t: t["name"])}


def load_lock(path: str) -> Dict[str, str]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    tools = d.get("tools")
    if not isinstance(tools, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in tools.items()):
        raise SecurityError(f"{path}: not a tool manifest lock")
    return tools


def write_lock(path: str, tools: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    m = manifest(tools)
    Path(path).write_text(json.dumps({"schema": "datamend-mcp-manifest-v1", "algorithm": "sha256 of canonical JSON of name+description+inputSchema+annotations",
                                      "tools": m}, indent=2) + "\n", encoding="utf-8")
    return m


def verify_manifest(tools: Iterable[Dict[str, Any]], lock: Dict[str, str]) -> None:
    """Raise ManifestMismatch if a tool is new, missing or changed against the pinned lock (rug-pull / squatting guard)."""
    now = manifest(tools)
    changed = sorted(n for n in now if n in lock and now[n] != lock[n])
    added = sorted(n for n in now if n not in lock)
    missing = sorted(n for n in lock if n not in now)
    if changed or added or missing:
        raise ManifestMismatch(f"tool definitions differ from the pinned lock: changed={changed} unexpected={added} missing={missing}")


def scan_definition(tool: Dict[str, Any]) -> List[str]:
    """Instruction-like text inside a tool's name, description or parameter descriptions (tool poisoning)."""
    texts = [str(tool.get("name", "")), str(tool.get("description", ""))]

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "description" and isinstance(v, str):
                    texts.append(v)
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)
    walk(tool.get("inputSchema"))
    return [p for t in texts for p in find_injection(t)]


def assert_read_only(tools: Iterable[Dict[str, Any]]) -> None:
    for t in tools:
        a = t.get("annotations") or {}
        if a.get("readOnlyHint") is not True or a.get("destructiveHint") is True:
            raise SecurityError(f"tool {t.get('name')!r} is not declared read-only; this server never registers a write tool")


# --------------------------------------------------------------------------------------------------------- authentication
def check_bearer(header: Optional[str], expected: str) -> bool:
    if not expected or not header or not header.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(header[7:].strip().encode(), expected.encode())


def origin_allowed(origin: Optional[str], allowed: Iterable[str]) -> bool:
    """No Origin header = not a browser (fine). A browser Origin must be on the allow-list (guards against DNS rebinding, per the MCP transport spec)."""
    return origin is None or origin in set(allowed)


# --------------------------------------------------------------------------------------------------------- abuse control
class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute, self._calls, self._lock = per_minute, deque(), threading.Lock()   # type: Deque[float]

    def take(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] > 60.0:
                self._calls.popleft()
            if len(self._calls) >= self.per_minute:
                return False
            self._calls.append(now)
            return True


_SECRET_KEYS = re.compile(r"(token|password|secret|api[_-]?key|authorization)", re.I)


def redact(v: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "…"
    if isinstance(v, dict):
        return {k: ("[redacted]" if _SECRET_KEYS.search(str(k)) else redact(x, depth + 1)) for k, x in v.items()}
    if isinstance(v, list):
        return [redact(x, depth + 1) for x in v[:20]]
    if isinstance(v, str):
        return v if len(v) <= 120 else v[:119] + "…"
    return v


class AuditLog:
    """One JSON line per tool call. Arguments are redacted and capped; results are recorded by size only."""

    def __init__(self, path: str) -> None:
        self.path, self._lock = path, threading.Lock()

    def record(self, **fields: Any) -> None:
        if not self.path:
            return
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), **{k: redact(v) for k, v in fields.items()}}, default=str)
        try:
            with self._lock:
                p = Path(self.path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except OSError:
            pass            # auditing must never break a tool call
