"""Security layer for the datamend MCP server.

Each defence maps to a threat discussed in the MCP security literature:

  Threat (seminar slide 8)              Defence in this file
  ------------------------------------  ---------------------------------------
  Unauthorized access / over-privilege  resolve_in_workspace(), Policy (least privilege)
  Tool poisoning / rug pull             fingerprint_tools(), write_lock(), verify_lock()
  Prompt / retrieval injection          sanitize_text() on every string derived from data
  (no accountability)                   AuditLog (JSON-lines record of every call)
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


class SecurityError(Exception):
    """A request was blocked by the security layer."""


class PolicyDenied(SecurityError):
    """The policy does not allow this tool call."""


class ToolInputError(Exception):
    """The caller supplied invalid input (not a security violation)."""


# --------------------------------------------------------------------------- #
# 1. Text sanitisation (prompt-injection hygiene)
# --------------------------------------------------------------------------- #
# Zero-width / bidi / control characters that can hide instructions from humans.
_HIDDEN_CHARS = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]"
)

# Heuristic patterns typical of injected instructions. This is a *tripwire*, not a
# guarantee: determined attackers can phrase things differently.
_INJECTION = re.compile(
    r"(ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+(instructions|prompts)"
    r"|disregard\s.{0,30}instructions"
    r"|system\s+prompt"
    r"|you\s+(must|should)\s+now"
    r"|do\s+not\s+tell\s+the\s+user"
    r"|<\s*/?\s*(system|assistant|tool|instructions?)\s*>"
    r"|call\s+the\s.{0,30}\btool\b"
    r"|send\s.{0,40}https?://"
    r"|exfiltrate)",
    re.IGNORECASE,
)

REDACTED = "[REDACTED: possible prompt-injection text]"


def contains_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def sanitize_text(value: Any, max_len: int = 120) -> str:
    """Make any data-derived value safe to hand back to an LLM.

    Removes hidden characters, collapses whitespace, redacts instruction-like
    text and truncates. Used for column names, category values, messages, etc.
    """
    text = _HIDDEN_CHARS.sub("", str(value))
    text = " ".join(text.split())
    if contains_injection(text):
        return REDACTED
    if len(text) > max_len:
        text = text[: max_len - 1] + "\u2026"
    return text


# --------------------------------------------------------------------------- #
# 2. Workspace sandbox (least privilege for the file system)
# --------------------------------------------------------------------------- #
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


def safe_name(name: str) -> str:
    """Validate a bare file/contract name (no directories, no traversal)."""
    if not isinstance(name, str) or not _SAFE_NAME.match(name) or ".." in name:
        raise ToolInputError(
            "Invalid name. Use letters, digits, '_', '-', '.' only (max 100 chars, no slashes)."
        )
    return name


def resolve_in_workspace(root: Path, user_path: str, *, must_exist: bool = True) -> Path:
    """Resolve *user_path* and guarantee it stays inside *root*.

    Blocks ``..`` traversal, absolute paths outside the workspace, and symlinks
    that point outside (``Path.resolve`` follows symlinks before the check).
    """
    if not isinstance(user_path, str) or not user_path.strip():
        raise ToolInputError("Path must be a non-empty string.")
    if "\x00" in user_path:
        raise SecurityError("Null byte in path.")
    root_resolved = root.resolve()
    candidate = Path(user_path)
    if not candidate.is_absolute():
        candidate = root_resolved / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise SecurityError("Path escapes the allowed workspace.") from None
    if must_exist and not resolved.is_file():
        raise ToolInputError(f"File not found in workspace: {sanitize_text(user_path)}")
    return resolved


# --------------------------------------------------------------------------- #
# 3. Policy (explicit permissions, deny by default)
# --------------------------------------------------------------------------- #
_DEFAULT_LIMITS = {
    "max_file_mb": 50,
    "max_rows": 1_000_000,
    "max_columns": 500,
    "allowed_extensions": [".csv", ".json", ".parquet", ".xlsx"],
}


@dataclass
class Policy:
    default: str = "deny"
    tools: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    limits: Dict[str, Any] = field(default_factory=lambda: dict(_DEFAULT_LIMITS))

    @classmethod
    def load(cls, path: Path) -> "Policy":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        limits = dict(_DEFAULT_LIMITS)
        limits.update(data.get("limits", {}))
        return cls(default=data.get("default", "deny"), tools=data.get("tools", {}), limits=limits)

    def check(self, tool: str, *, read_only: bool = False) -> None:
        spec = self.tools.get(tool)
        if spec is None:
            if self.default == "deny":
                raise PolicyDenied(f"Tool '{tool}' is not allowed by policy.")
            return
        if not spec.get("allow", False):
            raise PolicyDenied(f"Tool '{tool}' is disabled by policy.")
        if spec.get("mode") == "write" and read_only:
            raise PolicyDenied(f"Tool '{tool}' modifies files and the server is in read-only mode.")

    @property
    def max_file_bytes(self) -> int:
        return int(self.limits["max_file_mb"]) * 1024 * 1024

    @property
    def max_rows(self) -> int:
        return int(self.limits["max_rows"])

    @property
    def max_columns(self) -> int:
        return int(self.limits["max_columns"])

    @property
    def allowed_extensions(self) -> List[str]:
        return [e.lower() for e in self.limits["allowed_extensions"]]

    def check_file(self, path: Path) -> None:
        if path.suffix.lower() not in self.allowed_extensions:
            raise ToolInputError(
                f"File type '{sanitize_text(path.suffix)}' not allowed. "
                f"Allowed: {', '.join(self.allowed_extensions)}"
            )
        if path.exists() and path.stat().st_size > self.max_file_bytes:
            raise ToolInputError(f"File exceeds the {self.limits['max_file_mb']} MB limit.")


# --------------------------------------------------------------------------- #
# 4. Audit log (accountability)
# --------------------------------------------------------------------------- #
class AuditLog:
    """Append-only JSON-lines log. Stores tool name, arguments, status and
    timing - never the contents of the user's data."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(self, **fields: Any) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # Never let logging problems break a tool call.
            pass

    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


# --------------------------------------------------------------------------- #
# 5. Tool-definition pinning (tool poisoning / rug-pull defence)
# --------------------------------------------------------------------------- #
def _tool_fields(tool: Any) -> Dict[str, Any]:
    if isinstance(tool, dict):
        name = tool.get("name")
        desc = tool.get("description")
        schema = tool.get("inputSchema", tool.get("input_schema"))
    else:
        name = getattr(tool, "name", None)
        desc = getattr(tool, "description", None)
        schema = getattr(tool, "inputSchema", None)
    return {"name": name, "description": desc or "", "inputSchema": schema or {}}


def fingerprint_tools(tools: Iterable[Any]) -> Dict[str, Any]:
    """SHA-256 fingerprint of every tool's name + description + input schema."""
    entries: Dict[str, str] = {}
    for tool in tools:
        fields = _tool_fields(tool)
        canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        entries[str(fields["name"])] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    overall = hashlib.sha256(json.dumps(entries, sort_keys=True).encode("utf-8")).hexdigest()
    return {"version": 1, "algorithm": "sha256", "tools": entries, "manifest_hash": overall}


def write_lock(tools: Iterable[Any], path: Path) -> Dict[str, Any]:
    manifest = fingerprint_tools(tools)
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_lock(tools: Iterable[Any], path: Path) -> List[str]:
    """Return a list of problems (empty list == definitions match the lock)."""
    locked = json.loads(Path(path).read_text(encoding="utf-8"))["tools"]
    current = fingerprint_tools(tools)["tools"]
    problems: List[str] = []
    for name in sorted(set(current) - set(locked)):
        problems.append(f"NEW tool not in lock file: {name}")
    for name in sorted(set(locked) - set(current)):
        problems.append(f"MISSING tool that is in lock file: {name}")
    for name in sorted(set(locked) & set(current)):
        if locked[name] != current[name]:
            problems.append(f"CHANGED definition (description or schema): {name}")
    return problems
