"""Explanation stage helpers (prototype, slice S6 skeleton).

The account is built from the recorded evidence, the selection criteria and the rejected alternatives (`build_basis`). The model's text
is only accepted when `validate_text` finds nothing in it that the tool results held in the state did not return: no number, no
check name, no station id. All accepted output is marked generated and stored apart from the evidence.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from . import policy
from .state import AgentState

_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_ID_LIKE = re.compile(r"\b(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{3,}\b")        # letters and digits: a station id, a ref id
_SNAKE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")                                       # check-name style


def _norm_number(text: str) -> str:
    try:
        return repr(float(text))
    except ValueError:
        return text


def _walk(obj: Any, numbers: set, words: set) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        numbers.add(_norm_number(str(obj)))
    elif isinstance(obj, str):
        numbers.update(_norm_number(m) for m in _NUMBER.findall(obj))
        words.update(t.lower() for t in _ID_LIKE.findall(obj))
        words.update(t.lower() for t in _SNAKE.findall(obj))
        words.add(obj.lower())
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk(k, numbers, words)
            _walk(v, numbers, words)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _walk(v, numbers, words)


def allowed_vocabulary(state: AgentState) -> tuple[set, set]:
    """Numbers and identifier-like words present in the tool results (and the references that point at them) held in the state."""
    numbers: set = set()
    words: set = set()
    for ev in state.get("evidence", []):
        _walk(ev.get("result"), numbers, words)
        _walk([ev.get("ref_id"), ev.get("run_id"), ev.get("row_ref"), ev.get("station_id"), ev.get("evidence_hash")], numbers, words)
        _walk(ev.get("checks"), numbers, words)
    words.update(policy.ALLOWED_ACTIONS)         # naming an allowlisted action is not a claim about the data
    words.update(policy.REVIEWER_LABELS)         # nor is naming a reviewer label, or a tool the agent itself called
    words.update(str(c.get("tool", "")).lower() for c in state.get("tool_calls", []))
    return numbers, words


def validate_text(text: Any, state: AgentState, known_checks: Iterable[str] = ()) -> list[str]:
    """Problems found in a generated explanation; an empty list means it names nothing the tools did not return."""
    if not isinstance(text, str) or not text.strip():
        return ["empty or non-text explanation"]
    numbers, words = allowed_vocabulary(state)
    problems: list[str] = []
    for m in _NUMBER.findall(text):
        if _norm_number(m) not in numbers:
            problems.append(f"number {m} is not in the tool results")
    for tok in set(_ID_LIKE.findall(text)) | set(_SNAKE.findall(text)):
        if tok.lower() not in words:
            problems.append(f"name '{tok}' is not in the tool results")
    held_checks = {str(k).lower() for ev in state.get("evidence", []) for k in (ev.get("checks") or {})}
    low = text.lower().replace("_", " ")
    for name in known_checks:
        if str(name).lower() not in held_checks and str(name).lower().replace("_", " ") in low:
            problems.append(f"check '{name}' was not returned by the tools")
    return sorted(set(problems))


def build_basis(state: AgentState) -> dict:
    """The deterministic account: what was read, what was chosen and by which criteria, what was rejected and why."""
    return {
        "evidence": [{k: ev.get(k) for k in ("ref_id", "tool", "run_id", "row_ref", "station_id", "evidence_hash", "source_status")}
                     for ev in state.get("evidence", [])],
        "selected": state.get("selected"),
        "selection_criteria": state.get("selection_criteria", ""),
        "rejected_alternatives": list(state.get("rejected", [])),
    }
