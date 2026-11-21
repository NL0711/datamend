"""Independent execution gate (prototype, slice S6 skeleton).

Independent of the model and of the decide node: it imports only `policy`, trusts nothing decide wrote (not the rejected list, not any
"accepted" flag), and re-verifies the chosen action immediately before act against policy and a FRESH evidence hash from an injected lookup.
Any mismatch refuses. It never runs the action; it only answers yes or no with its reasons.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from . import policy
from .interfaces import EvidenceLookup
from .state import STATUS_RUNNING, AgentState


def action_digest(action: Any, args: Any) -> str:
    """Fingerprint of exactly what the gate approved; act refuses to run anything whose fingerprint differs."""
    return hashlib.sha256(json.dumps([action, args], sort_keys=True, default=str).encode("utf-8")).hexdigest()


@dataclass
class GateResult:
    ok: bool
    reason: str = ""
    checks: list = field(default_factory=list)       # [{"check", "ok", "detail"}]
    approved_digest: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _matching_evidence(state: AgentState, args: dict) -> list:
    out = []
    for ev in state.get("evidence", []):
        if ev.get("run_id") != args.get("run_id") or ev.get("station_id") != args.get("station_id"):
            continue
        if "row_ref" in args and ev.get("row_ref") != args.get("row_ref"):
            continue
        out.append(ev)
    return out


def verify(state: AgentState, lookup: EvidenceLookup) -> GateResult:
    checks: list[dict] = []

    def fail(name: str, detail: str) -> GateResult:
        checks.append({"check": name, "ok": False, "detail": detail})
        return GateResult(False, f"{name}: {detail}", checks)

    def passed(name: str, detail: str = "") -> None:
        checks.append({"check": name, "ok": True, "detail": detail})

    sel: Optional[dict] = state.get("selected")
    if not sel:
        return fail("selected", "no action selected")
    action, args = sel.get("action"), sel.get("args")
    if state.get("status") != STATUS_RUNNING:
        return fail("status", f"task status is '{state.get('status')}', not running")
    if not state.get("explanation") or state["explanation"].get("generated") is not True:
        return fail("explanation", "no accepted explanation recorded")
    passed("selected", str(action))
    # the chosen action must be one the model actually proposed (nothing was swapped in after the proposal)
    if not any(c.get("action") == action and c.get("args") == args for c in state.get("candidates", [])):
        return fail("provenance", "selected action is not among the recorded candidates")
    passed("provenance")
    pol = policy.check_action(action, args)
    if not pol.ok:
        return fail("policy", pol.reason)
    passed("policy")
    if policy.ALLOWED_ACTIONS[action].needs_evidence:
        held = _matching_evidence(state, args)
        if not held:
            return fail("evidence", "no held evidence matches the action's run, row and station")
        for ev in held:
            if not ev.get("evidence_hash"):
                return fail("evidence", f"held evidence {ev.get('ref_id')} has no hash")
            try:
                fresh: Any = lookup(ev.get("station_id"), ev.get("run_id"), ev.get("row_ref"))
            except Exception as exc:
                return fail("fresh_hash", f"lookup failed: {type(exc).__name__}: {exc}")
            if fresh is None:
                return fail("fresh_hash", f"evidence {ev.get('ref_id')} no longer exists")
            if fresh != ev["evidence_hash"]:
                return fail("fresh_hash", f"evidence {ev.get('ref_id')} changed since it was read")
        passed("fresh_hash", f"{len(held)} evidence reference(s) unchanged")
    return GateResult(True, "all checks passed", checks, action_digest(action, args))
