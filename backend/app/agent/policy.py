"""Deterministic policy for the agent (prototype, slice S6 skeleton).

Two things live here, both independent of any model:
  * the ALLOWLIST of actions the agent may ever execute, with the arguments each one takes;
  * the READ-ONLY tool allowlist: the only tools perception (and the model's `tools` handle) may call.

Anything not on an allowlist is rejected with a reason. Nothing here calls a model or the network.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Read-only MCP tools of the DataMend server (mcp-service/datamend_mcp/tools.py, all read-only). A tool outside this set cannot be called by the agent.
READ_ONLY_TOOLS = frozenset({
    "list_runs", "get_run_summary", "list_flagged_rows", "get_row_evidence", "get_evidence_v1", "get_row_context",
    "summarize_flag_patterns", "get_overview", "get_station_cycle", "get_review_summary", "get_row_reviews", "locate_place",
})


# The reviewer decisions of the platform's review loop (validation/review.py DECISIONS); a verdict word such as SUSPECT is not a label.
REVIEWER_LABELS = ("confirmed_fault", "false_alarm", "genuine_extreme", "needs_followup")


@dataclass(frozen=True)
class ActionSpec:
    required: frozenset
    optional: frozenset
    needs_evidence: bool          # the action targets a run / row, so it must be backed by evidence the agent holds and a fresh hash


ALLOWED_ACTIONS: dict[str, ActionSpec] = {
    "propose_reviewer_label": ActionSpec(frozenset({"run_id", "row_ref", "station_id", "label"}), frozenset({"note"}), True),
    "add_review_note": ActionSpec(frozenset({"run_id", "row_ref", "station_id", "note"}), frozenset(), True),
    # a flag on the alert only; it never touches a verdict
    "acknowledge_alert": ActionSpec(frozenset({"alert_id", "station_id"}), frozenset({"note"}), False),
    "request_checks_rerun": ActionSpec(frozenset({"run_id", "station_id"}), frozenset({"reason"}), True),
    "ask_user": ActionSpec(frozenset({"question"}), frozenset({"station_id"}), False),
}

# Words that mark something the agent must never change. Used only to give a precise rejection reason; the allowlist is what protects.
_FORBIDDEN_WORDS = {
    "verdict": "changes a verdict", "score": "changes a score", "evidence": "changes evidence", "raw": "changes raw data",
    "setting": "changes settings", "config": "changes settings", "secret": "touches a secret", "token": "touches a secret",
    "key": "touches a secret", "password": "touches a secret", "source": "changes a source", "inject": "touches the injector",
    "delete": "deletes data", "overwrite": "overwrites data", "threshold": "changes settings",
}
_FORBIDDEN_ARG_KEYS = ("verdict", "score", "raw", "setting", "secret", "token", "api_key", "password", "source", "inject", "threshold")


@dataclass(frozen=True)
class PolicyDecision:
    ok: bool
    reason: str = ""


def _why_forbidden(name: str) -> str:
    low = str(name).lower()
    for word, why in _FORBIDDEN_WORDS.items():
        if word in low:
            return why
    return "is not on the action allowlist"


def check_action(action: Any, args: Any) -> PolicyDecision:
    """Is this action, with these arguments, on the allowlist and well formed? Pure and deterministic."""
    if not isinstance(action, str) or not action:
        return PolicyDecision(False, "malformed action name")
    spec = ALLOWED_ACTIONS.get(action)
    if spec is None:
        return PolicyDecision(False, f"action '{action}' {_why_forbidden(action)}")
    if not isinstance(args, Mapping):
        return PolicyDecision(False, "malformed arguments (not a mapping)")
    for key in args:
        low = str(key).lower()
        if any(bad in low for bad in _FORBIDDEN_ARG_KEYS):
            return PolicyDecision(False, f"argument '{key}' {_why_forbidden(key)}")
    missing = sorted(spec.required - set(args))
    if missing:
        return PolicyDecision(False, f"missing required arguments: {', '.join(missing)}")
    extra = sorted(set(args) - spec.required - spec.optional)
    if extra:
        return PolicyDecision(False, f"unexpected arguments: {', '.join(extra)}")
    for key, value in args.items():
        if isinstance(value, (dict, list, tuple, set)) or value is None or (isinstance(value, str) and not value.strip()):
            return PolicyDecision(False, f"argument '{key}' must be a non-empty scalar")
    if action == "propose_reviewer_label" and args["label"] not in REVIEWER_LABELS:
        return PolicyDecision(False, f"label must be one of {', '.join(REVIEWER_LABELS)}")
    return PolicyDecision(True)


def check_tool(name: Any) -> PolicyDecision:
    """Tool-permission check: perception and the model's tool handle may call read-only tools only."""
    if name in READ_ONLY_TOOLS:
        return PolicyDecision(True)
    return PolicyDecision(False, f"tool '{name}' is not on the read-only tool allowlist")
