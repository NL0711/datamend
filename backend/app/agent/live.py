"""The agent's comment on the CURRENT LIVE FEED of one station (PROTOTYPE of a sandboxed, bounded decision-support agent).

A second graph beside `graph.py`, same parts, no action:

    START -> perceive -> decide --(evidence adequate)--> reason -> explain --(guard accepts)--> gate --(approved)--> END
                            \\--(inadequate)--> abstain -> END           \\--(refused)--> END          \\--(refused)--> END

  * perceive  reads the station's live feed and detections through the read-only MCP tools; each result is an evidence reference. The hash of
              each is the hash of an IMMUTABLE snapshot (readings up to a cutoff id; the tables are append-only), not of the moving feed.
  * decide    deterministic: is the evidence adequate (tools succeeded, readings exist)? Otherwise abstain or ask, never force.
  * reason    the model writes a short comment from the evidence (`model.comment`). It proposes no action: a live comment needs none.
  * explain   the guard: the comment may not name a number, check or station the tools did not return, may not call simulated data real and
              may not call the model score a verdict or leave out that it is not validated.
  * gate      independent of the model: re-reads the SAME window (same cutoff) and compares the hash, and re-reads the source state; a feed
              that went stale or disconnected since perception withholds the comment (the caller asks or abstains).

The comment is stored apart from the evidence and marked generated. `BaselineLiveModel` builds a deterministic rule-based comment from the
same evidence with no language model (used when no provider is connected, and always shown next to a generated one).
"""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Callable, Iterable, Optional, Protocol, runtime_checkable

from langgraph.graph import END, START, StateGraph

from . import events, explain as explain_mod, gate as gate_mod
from .events import EventLog
from .graph import Step, _refs
from .interfaces import GuardedTools, ToolBox, ToolCapExceeded, ToolDenied
from .state import (STATUS_ABSTAINED, STATUS_EXPLANATION_REFUSED, STATUS_GATE_REFUSED, STATUS_NEEDS_CLARIFICATION, STATUS_RUNNING, STATUS_COMPLETED,
                    AgentState)

FEED_TOOL, DETECTIONS_TOOL = gate_mod.LIVE_TOOLS
DEFAULT_WINDOW = 60
MAX_WINDOW = 288
DEFAULT_DETECTIONS = 20


class LiveState(AgentState, total=False):
    source_at_perception: dict
    comment_draft: str
    source_at_gate: dict


@runtime_checkable
class LiveCommentModel(Protocol):
    """A model that can write the live comment. It writes text only; it never executes anything and proposes no action."""
    model_id: str
    def comment(self, state: AgentState) -> str: ...


# (station_id, cutoff_id, window) -> hash of that snapshot NOW; station_id -> {"feed_state": ...} NOW
SnapshotLookup = gate_mod.SnapshotLookup
SourceLookup = gate_mod.SourceLookup


def new_live_state(objective: str, *, station_id: str, window: int = DEFAULT_WINDOW, detections_limit: int = DEFAULT_DETECTIONS, max_tool_calls: int = 6,
                   task_id: Optional[str] = None) -> LiveState:
    return LiveState(
        task_id=task_id or uuid.uuid4().hex, objective=objective,
        constraints={"scope": "live", "station_id": station_id, "window": max(1, min(int(window), MAX_WINDOW)), "detections_limit": int(detections_limit),
                     "max_tool_calls": int(max_tool_calls), "perception_plan": []},
        evidence=[], tool_calls=[], tool_call_count=0, tool_cap_hit=False, candidates=[], selected=None, rejected=[], selection_criteria="",
        abstain_reason="", explanation=None, gate_result=None, outcome=None, status=STATUS_RUNNING, step=0)


def _held(state: AgentState, tool: str) -> Optional[dict]:
    return next((ev for ev in state.get("evidence", []) if ev.get("tool") == tool), None)


def feed_result(state: AgentState) -> dict:
    ev = _held(state, FEED_TOOL)
    return (ev or {}).get("result") or {}


def detections_result(state: AgentState) -> dict:
    ev = _held(state, DETECTIONS_TOOL)
    return (ev or {}).get("result") or {}


# ------------------------------------------------------------------------------------------------ the deterministic baseline
class BaselineLiveModel:
    """No language model: a summary composed by fixed rules from the held evidence only. Numbers and names are copied verbatim."""
    model_id = "baseline-rules"

    def comment(self, state: AgentState) -> str:
        return baseline_text(state)


def baseline_text(state: AgentState) -> Optional[str]:
    feed = feed_result(state)
    if not feed:
        return None
    dets = detections_result(state)
    sid, fs = feed.get("station_id"), feed.get("feed_state")
    parts = [f"Live feed of station {sid}: the feed is {fs}"]
    if feed.get("source_id"):
        parts[0] += f" (source {feed['source_id']}"
        parts[0] += f", cadence {feed['cadence_seconds']} seconds)" if feed.get("cadence_seconds") is not None else ")"
    if fs == "stale" and feed.get("stale_since"):
        parts.append(f"No reading has arrived since {feed['stale_since']}.")
    if fs == "disconnected":
        parts.append("The source is disconnected; no reading is invented to fill the gap.")
    if fs == "not_streaming":
        parts.append("The active source does not serve this station, so the stored readings are history, not a live feed.")
    n = feed.get("n_readings", 0)
    if n:
        parts.append(f"The window holds {n} stored readings, the last at {feed.get('last_reading_at')}; its verdict is {feed.get('last_verdict')}.")
    counts = feed.get("counts_by_check_status") or {}
    if counts:
        parts.append("Verdicts in the window: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + ".")
    total = feed.get("detections_in_window", 0)
    fired = sorted({c for d in (dets.get("detections") or []) for c in (d.get("checks_fired") or [])})
    parts.append(f"{total} detections in the window" + (f"; checks that fired: {', '.join(fired)}." if fired else "."))
    not_run = [f"{x.get('check')} ({x.get('reason')})" for x in (feed.get("checks_not_run") or [])]
    if not_run:
        parts.append("Checks that did not run (from the stored detections): " + "; ".join(not_run) + ".")
    else:       # readings keep no 'not run' list; it is only known from detections, so an empty list is not 'all checks ran'
        parts.append("Checks that did not run: not available (stored readings do not keep that list, so this feed cannot say).")
    if feed.get("readings_with_no_checks"):
        parts.append(f"{feed['readings_with_no_checks']} readings had no check that could run.")
    ms = feed.get("model_score") or {}
    if ms.get("present"):
        parts.append("A Keras model score is present for this feed; it is not validated and it is never a verdict.")
    sources = sorted({row[6] for row in (feed.get("readings") or []) if len(row) > 6 and row[6]})
    if sources:
        parts.append("Readings come from source " + ", ".join(sources) + ".")
    parts.append("Generated by fixed rules from the stored evidence; the rule scores are uncalibrated and nothing here changes a verdict.")
    return " ".join(parts)


# ------------------------------------------------------------------------------------------------ the guard for a live comment
_REAL = re.compile(r"(?<!not )(?<!no )(?<!never )\breal[- ](?:world )?(?:data|readings?|measurements?|weather|observations?)\b", re.I)
_NO_CHECKS_RAN = re.compile(r"\bno (?:checks?|rules?)\s+(?:ran|were run|was run|have run|were executed)\b|\bchecks?\s+(?:did not|didn't|never)\s+run\b", re.I)
_MODEL_PRESENT = re.compile(r"\b(?:model|keras) scores?\s+(?:is|are)\s+present\b|\ba (?:model|keras) scores?\s+is\s+(?:present|available)\b|\bscore is present\b", re.I)
_MODEL_WORDS = re.compile(r"\b(?:keras|reconstruction|model score|model flag|model error|model's|the model)\b", re.I)
_MODEL_VERDICT = re.compile(r"\b(?:model|keras|score)\b[^.]{0,60}\b(?:verdict|confirm\w*|prove\w*|decid\w*)\b", re.I)
_NEGATED_VERDICT = re.compile(r"\b(?:not|never|no|neither)\s+(?:a\s+|an\s+)?(?:verdicts?|decisions?)\b", re.I)


def validate_live_text(text: Any, state: AgentState, known_checks: Iterable[str] = ()) -> list[str]:
    """Problems of a live comment: the base guard (numbers, ids, check names) plus the live rules. An empty list means it is accepted."""
    problems = explain_mod.validate_text(text, state, known_checks)
    if not isinstance(text, str) or not text.strip():
        return problems
    feed = feed_result(state)
    sources = {row[6] for row in (feed.get("readings") or []) if len(row) > 6}
    # owner decision (2026-11-21): the dashboard adds no warning label for simulated data, so a comment is not forced to say 'simulated';
    # it may still never call simulated data real or measured
    if _REAL.search(text) and "simulated" in sources:
        problems.append("simulated data is called real")
    counts = feed.get("counts_by_check_status") or {}
    if _NO_CHECKS_RAN.search(text) and any(k not in ("NO_CHECKS", "NO_DATA") for k in counts):
        problems.append("the comment says no checks ran, but readings in the window carry check verdicts")
    if _MODEL_PRESENT.search(text) and not (feed.get("model_score") or {}).get("present"):
        problems.append("the comment says a model score is present, but the feed holds none")
    if _MODEL_WORDS.search(text) and "not validated" not in text.lower():
        problems.append("the model score is mentioned without saying it is not validated")
    if _MODEL_VERDICT.search(_NEGATED_VERDICT.sub("", text)):
        problems.append("the model score is presented as a verdict")
    return sorted(set(problems))


# ------------------------------------------------------------------------------------------------ the graph
def build_live_graph(model: LiveCommentModel, toolbox: ToolBox, snapshot_lookup: SnapshotLookup, source_lookup: SourceLookup, log: EventLog, *,
                     known_checks: Iterable[str] = ()):
    model_id = getattr(model, "model_id", None)
    known = tuple(known_checks)

    def perceive(state: LiveState) -> Step:
        guard = GuardedTools(toolbox, state)
        c = state["constraints"]
        update: dict = {}
        try:
            feed = guard.call(FEED_TOOL, {"station_id": c["station_id"], "window": c["window"]})
            cutoff = ((feed or {}).get("snapshot") or {}).get("cutoff_id")
            if cutoff is not None:                              # the detections are read at the SAME cutoff, so both hash the same snapshot
                guard.call(DETECTIONS_TOOL, {"station_id": c["station_id"], "limit": c["detections_limit"], "window": c["window"], "up_to_id": cutoff})
            update["source_at_perception"] = {k: (feed or {}).get(k) for k in ("feed_state", "source_id", "stale_since")}
        except (ToolDenied, ToolCapExceeded, Exception):        # recorded in guard.calls; decide abstains on any failed call
            pass
        update.update({"evidence": list(state.get("evidence", [])) + guard.new_evidence, "tool_calls": list(state.get("tool_calls", [])) + guard.calls,
                       "tool_call_count": guard.count, "tool_cap_hit": guard.cap_hit})
        return Step(update, {"inputs": [c], "tool_calls": guard.calls, "note": "live feed and detections read through read-only MCP tools"})

    def decide(state: LiveState) -> Step:
        reason: Optional[tuple] = None
        feed = feed_result(state)
        failed = [x for x in state.get("tool_calls", []) if not x.get("ok")]
        if state.get("tool_cap_hit"):
            reason = (STATUS_ABSTAINED, f"tool-call cap of {state['constraints']['max_tool_calls']} reached")
        elif failed:
            reason = (STATUS_ABSTAINED, f"a tool call failed ({failed[0]['tool']}: {failed[0]['error']})")
        elif not feed:
            reason = (STATUS_NEEDS_CLARIFICATION, "the live feed was not read")
        elif not feed.get("n_readings"):
            reason = (STATUS_NEEDS_CLARIFICATION, f"no live readings are stored for station {feed.get('station_id')}; start a source that serves it or pick another station")
        elif not _held(state, FEED_TOOL).get("evidence_hash"):
            reason = (STATUS_NEEDS_CLARIFICATION, "the snapshot hash is missing for the live feed")
        if reason:
            return Step({"status": reason[0], "abstain_reason": reason[1]}, {"inputs": _refs(state), "decision": {"abstain": reason[1]}, "note": reason[1]})
        return Step({}, {"inputs": _refs(state), "decision": {"proceed": "evidence adequate; a comment, no action"}})

    def reason_node(state: LiveState) -> Step:
        update: dict = {}
        try:
            draft = model.comment(copy.deepcopy(state))
        except Exception as exc:                                # a failing model never becomes a made-up comment
            update.update({"model_error": f"{type(exc).__name__}: {exc}", "status": STATUS_ABSTAINED, "abstain_reason": f"model unavailable: {type(exc).__name__}: {exc}"})
            draft = None
        update["comment_draft"] = draft if isinstance(draft, str) else ""
        return Step(update, {"inputs": _refs(state), "model_id": model_id, "decision": {"drafted": bool(draft)}, "note": update.get("model_error", "")})

    def explain(state: LiveState) -> Step:
        problems = validate_live_text(state.get("comment_draft"), state, known)
        if problems:
            return Step({"status": STATUS_EXPLANATION_REFUSED, "explanation": None, "abstain_reason": "; ".join(problems)},
                        {"inputs": _refs(state), "model_id": model_id, "note": "comment refused: " + "; ".join(problems)})
        return Step({"explanation": {"text": state["comment_draft"], "generated": True, "basis": explain_mod.build_basis(state)}},
                    {"inputs": _refs(state), "model_id": model_id, "note": "comment accepted (generated)"})

    def gate(state: LiveState) -> Step:
        result = gate_mod.verify_live(state, snapshot_lookup, source_lookup)
        update: dict = {"gate_result": result.to_dict()}
        if result.ok:
            update["status"] = STATUS_COMPLETED
        else:
            failing = next((c["check"] for c in result.checks if not c["ok"]), "")
            update.update({"status": STATUS_NEEDS_CLARIFICATION if failing == "source_state" else STATUS_GATE_REFUSED, "abstain_reason": result.reason, "explanation": None})
        return Step(update, {"inputs": _refs(state), "gate_result": result.to_dict(), "outcome": {"status": update["status"], "detail": result.reason}, "note": result.reason})

    def abstain(state: LiveState) -> Step:
        return Step({}, {"inputs": _refs(state), "decision": {"abstain": state.get("abstain_reason")}, "outcome": {"status": state.get("status"), "detail": state.get("abstain_reason")},
                         "note": "abstain / clarify end"})

    def _wrap(name: str, fn: Callable[[LiveState], Step]):
        def node(state: LiveState) -> dict:
            result = fn(state)
            step = int(state.get("step", 0)) + 1
            fields = {"inputs": [], "model_id": None, "tool_calls": [], "decision": None, "rejected": [], "gate_result": None, "outcome": None, "note": ""}
            fields.update(result.log)
            log.append(events.step_record(task_id=state["task_id"], step=step, node=name, **fields))
            return {**result.update, "step": step}
        node.__name__ = name
        return node

    running = lambda s: s.get("status") == STATUS_RUNNING
    g = StateGraph(LiveState)
    for name, fn in (("perceive", perceive), ("decide", decide), ("reason", reason_node), ("explain", explain), ("gate", gate), ("abstain", abstain)):
        g.add_node(name, _wrap(name, fn))
    g.add_edge(START, "perceive")
    g.add_edge("perceive", "decide")
    g.add_conditional_edges("decide", lambda s: "reason" if running(s) else "abstain", {"reason": "reason", "abstain": "abstain"})
    g.add_conditional_edges("reason", lambda s: "explain" if running(s) else "abstain", {"explain": "explain", "abstain": "abstain"})
    g.add_conditional_edges("explain", lambda s: "gate" if running(s) and s.get("explanation") else "end", {"gate": "gate", "end": END})
    g.add_edge("gate", END)
    g.add_edge("abstain", END)
    return g.compile()


def live_summary(state: AgentState) -> dict:
    """Structured facts for the UI, copied from the held evidence (nothing computed by a model)."""
    feed = feed_result(state)
    if not feed:
        return {}
    snap = feed.get("snapshot") or {}
    ev = _held(state, FEED_TOOL) or {}
    return {"station_id": feed.get("station_id"), "feed_state_at_perception": feed.get("feed_state"), "source_id": feed.get("source_id"), "cadence_seconds": feed.get("cadence_seconds"),
            "last_reading_at": feed.get("last_reading_at"), "last_verdict": feed.get("last_verdict"), "n_readings": feed.get("n_readings"), "window": feed.get("window"),
            "counts_by_check_status": feed.get("counts_by_check_status"), "detections_in_window": feed.get("detections_in_window"),
            "checks_not_run": feed.get("checks_not_run"), "checks_not_run_available": bool(feed.get("checks_not_run")), "model_score_present": bool((feed.get("model_score") or {}).get("present")), "model_score_label": "not validated",
            "snapshot": {"cutoff_id": snap.get("cutoff_id"), "cutoff_timestamp": snap.get("cutoff_timestamp"), "evidence_hash": ev.get("evidence_hash")},
            "feed_state_at_gate": next((c.get("feed_state_now") for c in (state.get("gate_result") or {}).get("checks", []) if c.get("check") == "source_state"), None)}


def result_live_view(state: AgentState) -> dict:
    """What the route may show for a live task; the comment is marked generated and nothing in it is a verdict."""
    ex = state.get("explanation")
    return {"prototype": True, "scope": "live", "task_id": state.get("task_id"), "status": state.get("status"), "abstain_reason": state.get("abstain_reason", ""),
            "explanation": ex, "explanation_generated": bool(ex), "comment": ex["text"] if ex else None, "live": live_summary(state), "selected": None,
            "rejected_alternatives": [], "gate_result": state.get("gate_result"), "outcome": None, "tool_call_count": state.get("tool_call_count", 0)}
