"""Task state of the agent graph (prototype, slice S6 skeleton). The graph state IS the task state.

Everything in the state is plain JSON-friendly data (dicts, lists, strings, numbers) so it can be logged by reference and stored later.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

DEFAULT_MAX_TOOL_CALLS = 6        # assumed: a config value (DECISIONS.md, "Defaults set without the owner")

# Task statuses. Only "completed" means an action ran and its real outcome was a success.
STATUS_RUNNING = "running"
STATUS_ABSTAINED = "abstained"                          # inadequate evidence or no admissible candidate; reason is in `abstain_reason`
STATUS_NEEDS_CLARIFICATION = "needs_clarification"      # same, and a question for the user is the only sensible next step
STATUS_EXPLANATION_REFUSED = "explanation_refused"
STATUS_GATE_REFUSED = "gate_refused"
STATUS_COMPLETED = "completed"
STATUS_ACT_REFUSED = "act_refused"                      # the executor itself refused
STATUS_ACT_ERROR = "act_error"


@dataclass(frozen=True)
class Candidate:
    """An action the model PROPOSES. It is only a proposal: nothing runs from it until decide, explain and the gate have passed."""
    action: str
    args: dict = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {"action": self.action, "args": dict(self.args), "rationale": self.rationale}


class EvidenceRef(TypedDict, total=False):
    """One tool result held as evidence. `result` is the tool's answer verbatim; the explanation may only name what is in it."""
    ref_id: str
    tool: str
    run_id: Any
    row_ref: Any
    station_id: Any
    evidence_hash: Optional[str]
    source_status: str              # "live" or anything else (stale, disconnected, ...)
    checks: dict                    # check name -> "ran" | "not run" | ...
    result: dict


class AgentState(TypedDict, total=False):
    task_id: str
    objective: str
    constraints: dict               # station_id, run_id, row_ref, max_tool_calls, perception plan
    evidence: list                  # list[EvidenceRef]
    tool_calls: list                # [{"tool","args","ok","error"}] in call order
    tool_call_count: int
    tool_cap_hit: bool
    model_error: str
    candidates: list                # list[dict] from Candidate.to_dict()
    selected: Optional[dict]
    rejected: list                  # [{"action","args","reason"}]
    selection_criteria: str
    abstain_reason: str
    explanation: Optional[dict]     # {"text","generated":True,"basis":{...}}
    gate_result: Optional[dict]
    outcome: Optional[dict]         # the REAL outcome of act: {"status": success|refused|error, "detail": ...}
    status: str
    step: int


def new_state(objective: str, *, station_id: str, run_id: Any = None, row_ref: Any = None, max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
              perception_plan: Optional[list] = None, task_id: Optional[str] = None) -> AgentState:
    """Input stage: the objective and the constraints of one turn. `perception_plan` is a list of (tool, args) read-only calls."""
    plan = perception_plan
    if plan is None:
        plan = [("get_run_summary", {"run_id": run_id})] if run_id is not None else []
        if run_id is not None and row_ref is not None:
            plan.append(("get_evidence_v1", {"run_id": run_id, "row_id": row_ref}))
    return AgentState(
        task_id=task_id or uuid.uuid4().hex, objective=objective,
        constraints={"station_id": station_id, "run_id": run_id, "row_ref": row_ref, "max_tool_calls": int(max_tool_calls),
                     "perception_plan": [[t, dict(a)] for t, a in plan]},
        evidence=[], tool_calls=[], tool_call_count=0, tool_cap_hit=False, candidates=[], selected=None, rejected=[],
        selection_criteria="", abstain_reason="", explanation=None, gate_result=None, outcome=None, status=STATUS_RUNNING, step=0)
