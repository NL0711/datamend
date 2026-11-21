"""Injected interfaces of the agent (prototype, slice S6 skeleton). No model, tool or network is created at import time or anywhere in this package:
callers inject them. Fakes live only under tests/; the real ones are the Gemini adapter (gemini_model.py) and an MCP-backed ToolBox (NOT IMPLEMENTED yet)."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

from . import policy
from .state import AgentState, Candidate, EvidenceRef


@runtime_checkable
class ToolBox(Protocol):
    """Read-only tools. `call` returns the tool's result (a dict); it raises on failure."""
    def call(self, name: str, args: Mapping[str, Any]) -> Any: ...


@runtime_checkable
class AgentModel(Protocol):
    """The language model. It PROPOSES and EXPLAINS; it never executes. `tools` is a guarded read-only handle with a call cap."""
    model_id: str
    def propose(self, state: AgentState, tools: ToolBox) -> list[Candidate]: ...
    def explain(self, state: AgentState) -> str: ...


@runtime_checkable
class ActionExecutor(Protocol):
    """The ONLY thing that can change anything. Reached only from the act node, which is reached only through the gate. Real implementation: NOT IMPLEMENTED."""
    def execute(self, action: str, args: Mapping[str, Any]) -> Mapping[str, Any]: ...


# (station_id, run_id, row_ref) -> the CURRENT evidence hash, or None when the evidence no longer exists.
EvidenceLookup = Callable[[Any, Any, Any], Optional[str]]


class ToolDenied(Exception):
    pass


class ToolCapExceeded(Exception):
    pass


def evidence_ref_from_result(tool: str, args: Mapping[str, Any], result: Any, ref_id: str) -> EvidenceRef:
    """Hold a tool result as an evidence reference. Result convention: a dict that may carry run_id, row_ref (or row_id), station_id,
    evidence_hash, source_status ("live" when current) and checks ({name: "ran" | "not run" | ...})."""
    res = result if isinstance(result, dict) else {"value": result}
    row = res.get("row_ref", res.get("row_id", args.get("row_ref", args.get("row_id"))))
    return EvidenceRef(ref_id=ref_id, tool=tool, run_id=res.get("run_id", args.get("run_id")), row_ref=row,
                       station_id=res.get("station_id", args.get("station_id")), evidence_hash=res.get("evidence_hash"),
                       source_status=str(res.get("source_status", "live")), checks=dict(res.get("checks") or {}), result=res)


class GuardedTools:
    """Wraps the injected ToolBox for one stage: read-only allowlist, the per-turn call cap, a record of every call, and evidence capture."""

    def __init__(self, toolbox: ToolBox, state: AgentState) -> None:
        self._box = toolbox
        self.cap = int(state["constraints"]["max_tool_calls"])
        self.count = int(state.get("tool_call_count", 0))
        self.cap_hit = bool(state.get("tool_cap_hit", False))
        self._evidence_n = len(state.get("evidence", []))
        self.calls: list[dict] = []
        self.new_evidence: list[EvidenceRef] = []

    def call(self, name: str, args: Mapping[str, Any]) -> Any:
        args = dict(args)
        verdict = policy.check_tool(name)
        if not verdict.ok:
            self.calls.append({"tool": name, "args": args, "ok": False, "error": verdict.reason})
            raise ToolDenied(verdict.reason)
        if self.count >= self.cap:
            self.cap_hit = True
            self.calls.append({"tool": name, "args": args, "ok": False, "error": "tool-call cap reached"})
            raise ToolCapExceeded(f"tool-call cap of {self.cap} reached")
        self.count += 1
        try:
            result = self._box.call(name, args)
        except Exception as exc:       # the failure is recorded; it is never turned into a made-up result
            self.calls.append({"tool": name, "args": args, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            raise
        self.calls.append({"tool": name, "args": args, "ok": True, "error": ""})
        self._evidence_n += 1
        self.new_evidence.append(evidence_ref_from_result(name, args, result, f"ev{self._evidence_n}"))
        return result
