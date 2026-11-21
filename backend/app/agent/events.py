"""Structured, append-only event log of the agent (prototype, slice S6 skeleton): one record per graph step.

In-memory and JSONL implementations only. The SQL `agent_events` table is a LATER step (needs an Alembic migration): NOT IMPLEMENTED here.
Every record passes through `redact` first, which removes anything that looks like an API key or token.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol, runtime_checkable

REDACTED = "[REDACTED]"
_SECRET_KEY_NAME = re.compile(r"(api[_-]?key|token|secret|password|passwd|authorization|bearer|credential)", re.I)
_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                     # Google API key
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),                    # OpenAI / Anthropic style
    re.compile(r"\b(?:ghp|gho|ghs|github_pat|xox[abprs]|glpat)[-_][A-Za-z0-9_\-]{16,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),   # JWT
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[=:]\s*\S{6,}"),
]
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_PURE_HEX = re.compile(r"^[0-9a-fA-F]+$")


def _redact_str(text: str, extra: Iterable[str]) -> str:
    for secret in extra:
        if secret:
            text = text.replace(secret, REDACTED)
    for pat in _PATTERNS:
        text = pat.sub(REDACTED, text)

    def _long(m: re.Match) -> str:          # evidence hashes are pure hex and must stay readable; other long mixed tokens look like keys
        tok = m.group(0)
        if _PURE_HEX.match(tok) or not (re.search(r"[A-Za-z]", tok) and re.search(r"\d", tok)):
            return tok
        return REDACTED
    return _LONG_TOKEN.sub(_long, text)


def redact(obj: Any, extra_secrets: Iterable[str] = ()) -> Any:
    """Return a copy of `obj` with key-like and token-like strings removed, and the values of secret-named keys blanked."""
    extra = tuple(s for s in extra_secrets if s)
    if isinstance(obj, dict):
        return {k: (REDACTED if _SECRET_KEY_NAME.search(str(k)) and obj[k] not in (None, "") else redact(v, extra)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact(v, extra) for v in obj]
    if isinstance(obj, str):
        return _redact_str(obj, extra)
    return obj


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@runtime_checkable
class EventLog(Protocol):
    def append(self, record: dict) -> None: ...
    def read_all(self) -> list[dict]: ...


class InMemoryEventLog:
    """Append-only list. Exposes no way to change or remove a record."""
    def __init__(self, extra_secrets: Iterable[str] = ()) -> None:
        self._records: list[dict] = []
        self._extra = tuple(extra_secrets)
        self._lock = threading.Lock()

    def append(self, record: dict) -> None:
        clean = redact(json.loads(json.dumps(record, default=str)), self._extra)
        with self._lock:
            self._records.append(clean)

    def read_all(self) -> list[dict]:
        with self._lock:
            return json.loads(json.dumps(self._records))


class JsonlEventLog:
    """One JSON object per line, opened in append mode for every write."""
    def __init__(self, path: str | Path, extra_secrets: Iterable[str] = ()) -> None:
        self.path = Path(path)
        self._extra = tuple(extra_secrets)
        self._lock = threading.Lock()

    def append(self, record: dict) -> None:
        clean = redact(json.loads(json.dumps(record, default=str)), self._extra)
        line = json.dumps(clean, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


def step_record(*, task_id: str, step: int, node: str, inputs: list, model_id: Optional[str], tool_calls: list, decision: Any,
                rejected: list, gate_result: Any, outcome: Any, note: str = "") -> dict:
    """The one structured record of a step. `inputs` are references (evidence ref ids, hashes), never the content."""
    return {"task_id": task_id, "step": step, "node": node, "inputs": inputs, "model_id": model_id, "tool_calls": tool_calls,
            "decision": decision, "rejected_alternatives": rejected, "gate_result": gate_result, "outcome": outcome,
            "note": note, "time_utc": now_utc()}
