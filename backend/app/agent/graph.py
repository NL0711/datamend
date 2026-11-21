"""The agent pipeline as a LangGraph graph (PROTOTYPE of a sandboxed, bounded decision-support agent; slice S6 skeleton).

    START -> perceive -> reason -> decide --(admissible action)--> explain --(accepted)--> gate --(approved)--> act -> END
                                     \\--(inadequate evidence / nothing admissible)--> abstain -> END
                                                                      \\--(explanation refused)--> END     \\--(refused)--> END

`act` has exactly one incoming edge, from `gate`. The model, tools, executor, evidence lookup and log are injected into `build_agent_graph`;
nothing here creates a model or makes a network call. The executor and a real MCP-backed ToolBox are NOT IMPLEMENTED yet.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Iterable, NamedTuple, Optional

from langgraph.graph import END, START, StateGraph

from . import events, explain as explain_mod, gate as gate_mod, policy
from .events import EventLog
from .interfaces import ActionExecutor, AgentModel, EvidenceLookup, GuardedTools, ToolBox, ToolCapExceeded, ToolDenied
from .state import (STATUS_ABSTAINED, STATUS_ACT_ERROR, STATUS_ACT_REFUSED, STATUS_COMPLETED, STATUS_EXPLANATION_REFUSED,
                    STATUS_GATE_REFUSED, STATUS_NEEDS_CLARIFICATION, STATUS_RUNNING, AgentState, Candidate)

NODES = ("perceive", "reason", "decide", "explain", "gate", "act", "abstain")


class Step(NamedTuple):
    update: dict
    log: dict


def _refs(state: AgentState) -> list:
    return [{k: ev.get(k) for k in ("ref_id", "tool", "run_id", "row_ref", "station_id", "evidence_hash")} for ev in state.get("evidence", [])]


def build_agent_graph(model: AgentModel, toolbox: ToolBox, executor: ActionExecutor, evidence_lookup: EvidenceLookup, log: EventLog,
                      *, gate_lookup: Optional[EvidenceLookup] = None, known_checks: Iterable[str] = ()):
    """Compile the pipeline. `gate_lookup` lets the gate use its own source of fresh hashes (default: the same callable as decide's)."""
    model_id = getattr(model, "model_id", None)
    gate_fresh = gate_lookup or evidence_lookup
    known = tuple(known_checks)

    # ---- nodes: each returns a Step(update, log fields); `_wrap` writes exactly one event record per executed node -----------------
    def perceive(state: AgentState) -> Step:
        guard = GuardedTools(toolbox, state)
        for tool, args in state["constraints"].get("perception_plan", []):
            try:
                guard.call(tool, args)
            except (ToolDenied, ToolCapExceeded, Exception):      # recorded in guard.calls; decide abstains on any failed call
                pass
        return Step({"evidence": list(state.get("evidence", [])) + guard.new_evidence, "tool_calls": list(state.get("tool_calls", [])) + guard.calls,
                     "tool_call_count": guard.count, "tool_cap_hit": guard.cap_hit},
                    {"inputs": [state["constraints"]], "tool_calls": guard.calls})

    def reason(state: AgentState) -> Step:
        guard = GuardedTools(toolbox, state)
        update: dict = {}
        cands: list = []
        try:
            for c in model.propose(copy.deepcopy(state), guard):
                cands.append(c.to_dict() if isinstance(c, Candidate) else {"action": None, "args": {}, "rationale": "", "malformed": repr(c)[:200]})
        except ToolCapExceeded:
            pass                                                   # guard.cap_hit is set; decide abstains
        except Exception as exc:                                   # a failing model never becomes a made-up proposal
            update["model_error"] = f"{type(exc).__name__}: {exc}"
        update.update({"candidates": cands, "evidence": list(state.get("evidence", [])) + guard.new_evidence,
                       "tool_calls": list(state.get("tool_calls", [])) + guard.calls, "tool_call_count": guard.count, "tool_cap_hit": guard.cap_hit})
        return Step(update, {"inputs": _refs(state), "model_id": model_id, "tool_calls": guard.calls, "decision": {"proposed": cands},
                             "note": update.get("model_error", "")})

    def _abstain_reason(state: AgentState) -> Optional[tuple]:
        """(status, reason) when the evidence is inadequate, else None. Never forces a decision."""
        if state.get("model_error"):
            return STATUS_ABSTAINED, f"model unavailable: {state['model_error']}"
        if state.get("tool_cap_hit"):
            return STATUS_ABSTAINED, f"tool-call cap of {state['constraints']['max_tool_calls']} reached"
        failed = [c for c in state.get("tool_calls", []) if not c.get("ok")]
        if failed:
            return STATUS_ABSTAINED, f"a tool call failed ({failed[0]['tool']}: {failed[0]['error']})"
        bound = [ev for ev in state.get("evidence", []) if ev.get("run_id") is not None or "evidence_hash" in (ev.get("result") or {})]
        if not bound:
            return STATUS_NEEDS_CLARIFICATION, "no evidence was read for this task"
        for ev in bound:
            if not ev.get("evidence_hash"):
                return STATUS_NEEDS_CLARIFICATION, f"evidence hash missing for {ev['ref_id']} ({ev['tool']})"
        for ev in bound:
            if ev.get("source_status") != "live":
                return STATUS_NEEDS_CLARIFICATION, f"source is not live ({ev['source_status']}) for {ev['ref_id']}"
        for ev in bound:
            not_run = sorted(n for n, s in (ev.get("checks") or {}).items() if str(s).lower() == "not run")
            if not_run:
                return STATUS_NEEDS_CLARIFICATION, f"checks not run: {', '.join(not_run)}"
        for ev in bound:
            try:
                fresh = evidence_lookup(ev.get("station_id"), ev.get("run_id"), ev.get("row_ref"))
            except Exception as exc:
                return STATUS_ABSTAINED, f"evidence lookup failed: {type(exc).__name__}: {exc}"
            if fresh != ev["evidence_hash"]:
                return STATUS_NEEDS_CLARIFICATION, f"evidence hash changed or gone for {ev['ref_id']}"
        return None

    def decide(state: AgentState) -> Step:
        inadequate = _abstain_reason(state)
        if inadequate:
            status, reason = inadequate
            return Step({"status": status, "abstain_reason": reason, "selected": None},
                        {"inputs": _refs(state), "decision": {"abstain": reason}, "note": reason})
        rejected: list = []
        admissible: list = []
        for c in state.get("candidates", []):
            pol = policy.check_action(c.get("action"), c.get("args"))
            if not pol.ok:
                rejected.append({"action": c.get("action"), "args": c.get("args"), "reason": pol.reason})
            elif policy.ALLOWED_ACTIONS[c["action"]].needs_evidence and not gate_mod._matching_evidence(state, c["args"]):
                rejected.append({"action": c["action"], "args": c["args"], "reason": "not backed by evidence the agent read (run, row or station differ)"})
            else:
                admissible.append(c)
        criteria = "first policy-admissible candidate in the model's order; evidence-bound actions must match evidence read this turn"
        if not admissible:
            reason = "no candidate passed policy" if state.get("candidates") else "the model proposed no candidate"
            return Step({"status": STATUS_ABSTAINED, "abstain_reason": reason, "selected": None, "rejected": rejected, "selection_criteria": criteria},
                        {"inputs": _refs(state), "decision": {"abstain": reason}, "rejected": rejected, "note": reason})
        chosen = admissible[0]
        rejected += [{"action": c["action"], "args": c["args"], "reason": "admissible but not selected: an earlier candidate was chosen"} for c in admissible[1:]]
        sel = {"action": chosen["action"], "args": chosen["args"], "rationale": chosen.get("rationale", "")}
        return Step({"selected": sel, "rejected": rejected, "selection_criteria": criteria, "abstain_reason": ""},
                    {"inputs": _refs(state), "decision": {"selected": sel, "criteria": criteria}, "rejected": rejected})

    def explain(state: AgentState) -> Step:
        basis = explain_mod.build_basis(state)
        try:
            text = model.explain(copy.deepcopy(state))
        except Exception as exc:
            problems = [f"model failed to explain: {type(exc).__name__}: {exc}"]
            text = None
        else:
            problems = explain_mod.validate_text(text, state, known)
        if problems:
            return Step({"status": STATUS_EXPLANATION_REFUSED, "explanation": None, "abstain_reason": "; ".join(problems)},
                        {"inputs": _refs(state), "model_id": model_id, "decision": {"selected": state.get("selected")},
                         "rejected": state.get("rejected", []), "note": "explanation refused: " + "; ".join(problems)})
        return Step({"explanation": {"text": text, "generated": True, "basis": basis}},
                    {"inputs": _refs(state), "model_id": model_id, "decision": {"selected": state.get("selected")}, "rejected": state.get("rejected", []),
                     "note": "explanation accepted (generated)"})

    def gate(state: AgentState) -> Step:
        result = gate_mod.verify(state, gate_fresh)
        update: dict = {"gate_result": result.to_dict()}
        if not result.ok:
            update["status"] = STATUS_GATE_REFUSED
        return Step(update, {"inputs": _refs(state), "decision": {"selected": state.get("selected")}, "gate_result": result.to_dict(), "note": result.reason})

    def act(state: AgentState) -> Step:
        sel, gr = state.get("selected"), state.get("gate_result") or {}
        if not (gr.get("ok") is True and sel and gr.get("approved_digest") == gate_mod.action_digest(sel.get("action"), sel.get("args"))):
            raise RuntimeError("act reached without a matching gate approval")     # unreachable through the graph; defence in depth
        try:
            raw = executor.execute(sel["action"], dict(sel["args"]))
            status = raw.get("status") if isinstance(raw, dict) else None
            if status in ("success", "refused"):
                outcome = {"status": status, "detail": raw.get("detail", "")}
            else:
                outcome = {"status": "error", "detail": f"executor returned an unrecognised result: {str(raw)[:200]}"}      # never assumed to be a success
        except Exception as exc:
            outcome = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}
        final = {"success": STATUS_COMPLETED, "refused": STATUS_ACT_REFUSED}.get(outcome["status"], STATUS_ACT_ERROR)
        return Step({"outcome": outcome, "status": final},
                    {"inputs": _refs(state), "decision": {"selected": sel}, "gate_result": gr, "outcome": outcome})

    def abstain(state: AgentState) -> Step:
        return Step({}, {"inputs": _refs(state), "decision": {"abstain": state.get("abstain_reason")}, "rejected": state.get("rejected", []),
                         "outcome": {"status": state.get("status"), "detail": state.get("abstain_reason")}, "note": "abstain / clarify end"})

    def _wrap(name: str, fn: Callable[[AgentState], Step]):
        def node(state: AgentState) -> dict:
            result = fn(state)
            step = int(state.get("step", 0)) + 1
            fields = {"inputs": [], "model_id": None, "tool_calls": [], "decision": None, "rejected": [], "gate_result": None, "outcome": None, "note": ""}
            fields.update(result.log)
            log.append(events.step_record(task_id=state["task_id"], step=step, node=name, **fields))
            return {**result.update, "step": step}
        node.__name__ = name
        return node

    # ---- routing ---------------------------------------------------------------------------------------------------------------
    def after_decide(state: AgentState) -> str:
        return "explain" if state.get("selected") and state.get("status") == STATUS_RUNNING else "abstain"

    def after_explain(state: AgentState) -> str:
        return "gate" if state.get("explanation") and state.get("status") == STATUS_RUNNING else "end"

    def after_gate(state: AgentState) -> str:
        return "act" if (state.get("gate_result") or {}).get("ok") is True and state.get("status") == STATUS_RUNNING else "end"

    g = StateGraph(AgentState)
    for name, fn in (("perceive", perceive), ("reason", reason), ("decide", decide), ("explain", explain), ("gate", gate), ("act", act), ("abstain", abstain)):
        g.add_node(name, _wrap(name, fn))
    g.add_edge(START, "perceive")
    g.add_edge("perceive", "reason")
    g.add_edge("reason", "decide")
    g.add_conditional_edges("decide", after_decide, {"explain": "explain", "abstain": "abstain"})
    g.add_conditional_edges("explain", after_explain, {"gate": "gate", "end": END})
    g.add_conditional_edges("gate", after_gate, {"act": "act", "end": END})       # the ONLY edge into act
    g.add_edge("act", END)
    g.add_edge("abstain", END)
    return g.compile()


def result_view(state: AgentState) -> dict:
    """What a caller (route, UI) may show. Everything model-written is marked generated; the prototype status is stated."""
    return {"prototype": True, "task_id": state.get("task_id"), "status": state.get("status"), "abstain_reason": state.get("abstain_reason", ""),
            "explanation": state.get("explanation"), "explanation_generated": bool(state.get("explanation")), "selected": state.get("selected"),
            "rejected_alternatives": state.get("rejected", []), "gate_result": state.get("gate_result"), "outcome": state.get("outcome"),
            "tool_call_count": state.get("tool_call_count", 0)}
