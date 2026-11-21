"""FAKES for the agent tests. Nothing here is a real model, tool server or executor; they exist only under tests/ and return canned data.
(No tests in this file; it is named test_agent_* so the agent's test helpers sit together.)"""
from __future__ import annotations

from typing import Any, Mapping

from backend.app.agent.events import InMemoryEventLog
from backend.app.agent.graph import build_agent_graph
from backend.app.agent.state import Candidate, new_state

HASH = "a" * 64
STATION, RUN, ROW = "ZWL005", 7, 42


def evidence_result(**over) -> dict:
    """FAKE tool result in the convention of interfaces.evidence_ref_from_result (canned numbers, synthetic)."""
    res = {"run_id": RUN, "row_ref": ROW, "station_id": STATION, "evidence_hash": HASH, "source_status": "live",
           "checks": {"repeated_value": "ran", "spike": "ran"}, "observed_mm": 12.5}
    res.update(over)
    return res


class FakeToolBox:
    """FAKE read-only tool box: answers from a dict of canned results and counts calls."""
    def __init__(self, results: dict | None = None) -> None:
        self.results = results if results is not None else {"get_run_summary": evidence_result(), "get_evidence_v1": evidence_result()}
        self.calls: list = []

    def call(self, name: str, args: Mapping[str, Any]) -> Any:
        self.calls.append((name, dict(args)))
        if name not in self.results:
            raise KeyError(f"fake tool '{name}' has no canned result")
        return self.results[name]


class FakeModel:
    """FAKE model: proposes whatever it was given and explains with a canned text. `model_id` says it is fake."""
    model_id = "fake-model"

    def __init__(self, candidates: list | None = None, text: str = "Run 7 row 42 at station ZWL005 shows checks repeated_value and spike ran; a label is proposed for a reviewer.",
                 tool_calls: list | None = None) -> None:
        self.candidates = candidates if candidates is not None else [good_candidate()]
        self.text = text
        self.tool_calls = tool_calls or []
        self.tool_errors: list = []

    def propose(self, state, tools):
        for name, args in self.tool_calls:
            try:
                tools.call(name, args)
            except Exception as exc:
                self.tool_errors.append(exc)
        return self.candidates

    def explain(self, state) -> str:
        return self.text


class FakeExecutor:
    """FAKE executor: records what it was asked to run; returns a canned outcome."""
    def __init__(self, result: dict | None = None, raises: Exception | None = None) -> None:
        self.executed: list = []
        self.result = result if result is not None else {"status": "success", "detail": "fake executor recorded it"}
        self.raises = raises

    def execute(self, action: str, args: Mapping[str, Any]):
        self.executed.append((action, dict(args)))
        if self.raises:
            raise self.raises
        return self.result


def good_candidate(**over) -> Candidate:
    args = {"run_id": RUN, "row_ref": ROW, "station_id": STATION, "label": "genuine_extreme"}
    args.update(over)
    return Candidate("propose_reviewer_label", args, "evidence shows both checks ran")


class Lookup:
    """FAKE EvidenceLookup: returns HASH, or a different value after `change_after` calls."""
    def __init__(self, change_after: int | None = None, value: str | None = HASH) -> None:
        self.calls = 0
        self.change_after = change_after
        self.value = value

    def __call__(self, station, run, row):
        self.calls += 1
        if self.change_after is not None and self.calls > self.change_after:
            return "b" * 64
        return self.value


def make(model=None, toolbox=None, executor=None, lookup=None, gate_lookup=None, known_checks=(), **state_kw):
    log = InMemoryEventLog()
    model = model or FakeModel()
    toolbox = toolbox or FakeToolBox()
    executor = executor or FakeExecutor()
    graph = build_agent_graph(model, toolbox, executor, lookup or Lookup(), log, gate_lookup=gate_lookup, known_checks=known_checks)
    kw = dict(station_id=STATION, run_id=RUN, row_ref=ROW)
    kw.update(state_kw)
    state = new_state("Is row 42 a genuine extreme or a fault?", **kw)
    return graph, state, log, model, toolbox, executor
