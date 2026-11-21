"""Agent graph tests with a FAKE model, FAKE tools and a FAKE executor. No network, no real key, no real model."""
import json

import pytest

from backend.app.agent import policy
from backend.app.agent.events import JsonlEventLog, redact
from backend.app.agent.state import Candidate
from tests.test_agent_fakes import (HASH, ROW, RUN, STATION, FakeExecutor, FakeModel, FakeToolBox, Lookup, evidence_result, good_candidate, make)


def run(graph, state):
    return graph.invoke(state)


def test_happy_path_to_successful_act():
    graph, state, log, model, tools, ex = make()
    out = run(graph, state)
    assert out["status"] == "completed"
    assert ex.executed == [("propose_reviewer_label", good_candidate().args)]
    assert out["outcome"]["status"] == "success"
    assert out["gate_result"]["ok"] is True
    assert out["explanation"]["generated"] is True
    assert [r["node"] for r in log.read_all()] == ["perceive", "reason", "decide", "explain", "gate", "act"]


def test_one_record_per_step_with_required_fields_and_no_key():
    graph, state, log, *_ = make(model=FakeModel(text="Run 7 row 42 at station ZWL005 shows spike ran. key AIzaSyA1234567890abcdefghijklmnopqrstuv"))
    out = run(graph, state)
    # the explanation mentions a key-like string that is not in the tool results, so it is refused; the log must still hold no key
    assert out["status"] == "explanation_refused"
    recs = log.read_all()
    assert [r["step"] for r in recs] == list(range(1, len(recs) + 1))
    assert len({r["node"] for r in recs}) == len(recs)
    for r in recs:
        for k in ("task_id", "step", "node", "inputs", "model_id", "tool_calls", "decision", "rejected_alternatives", "gate_result", "outcome", "time_utc"):
            assert k in r
    assert "AIza" not in json.dumps(recs)
    assert recs[1]["model_id"] == "fake-model"


def test_log_redacts_keys_and_tokens_but_keeps_evidence_hashes():
    cleaned = redact({"a": "key AIzaSyA1234567890abcdefghijklmnopqrstuv", "b": "Bearer abcdefghijklmnop1234", "api_key": "xyz", "h": HASH,
                      "c": "sk-abcdefghijklmnop12345", "n": [{"token": "t0k3n"}]})
    flat = json.dumps(cleaned)
    assert "AIza" not in flat and "abcdefghijklmnop1234" not in flat and "xyz" not in flat and "sk-abc" not in flat and "t0k3n" not in flat
    assert cleaned["h"] == HASH


def test_jsonl_log_is_append_only_lines_and_redacts(tmp_path):
    path = tmp_path / "events.jsonl"
    log = JsonlEventLog(path, extra_secrets=["my-real-secret-value"])
    graph, state, *_ = make()
    from backend.app.agent.graph import build_agent_graph
    g = build_agent_graph(FakeModel(), FakeToolBox(), FakeExecutor(), Lookup(), log)
    g.invoke(state)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6 and all(json.loads(x)["task_id"] == state["task_id"] for x in lines)
    log.append({"task_id": "t", "note": "leak my-real-secret-value here"})
    assert "my-real-secret-value" not in path.read_text(encoding="utf-8")
    assert len(log.read_all()) == 7


@pytest.mark.parametrize("action,args,word", [
    ("change_verdict", {"run_id": RUN, "verdict": "SUSPECT"}, "verdict"),
    ("edit_score", {"run_id": RUN}, "score"),
    ("modify_evidence", {"run_id": RUN}, "evidence"),
    ("overwrite_raw_data", {"run_id": RUN}, "raw"),
    ("update_settings", {"x": 1}, "settings"),
    ("read_secret", {"name": "GEMINI_API_KEY"}, "secret"),
    ("switch_source", {"source": "esp32"}, "source"),
    ("run_injector", {"fault": "freeze"}, "injector"),
    ("delete_rows", {"run_id": RUN}, "delete"),
])
def test_every_forbidden_action_class_is_rejected_with_a_reason(action, args, word):
    d = policy.check_action(action, args)
    assert not d.ok and d.reason
    assert word in d.reason or "allowlist" in d.reason


def test_allowed_action_with_forbidden_or_extra_argument_is_rejected():
    assert not policy.check_action("add_review_note", {"run_id": 1, "row_ref": 2, "station_id": "S", "note": "n", "verdict": "FAULT"}).ok
    assert not policy.check_action("ask_user", {"question": "q", "extra": 1}).ok
    assert not policy.check_action("ask_user", {}).ok
    assert not policy.check_action("acknowledge_alert", {"alert_id": 3, "station_id": "S", "note": {"nested": 1}}).ok
    for ok in [("ask_user", {"question": "which run?"}), ("acknowledge_alert", {"alert_id": 3, "station_id": "S"}),
               ("request_checks_rerun", {"run_id": 1, "station_id": "S"})]:
        assert policy.check_action(*ok).ok


def test_model_proposing_forbidden_action_cannot_get_it_executed():
    bad = [Candidate("change_verdict", {"run_id": RUN, "verdict": "FAULT"}, "just do it"),
           Candidate("propose_reviewer_label", {"run_id": RUN, "row_ref": ROW, "station_id": STATION, "label": "fault", "score": 0.99}, "sneaky arg")]
    graph, state, log, model, tools, ex = make(model=FakeModel(candidates=bad))
    out = run(graph, state)
    assert ex.executed == []
    assert out["status"] == "abstained" and out["abstain_reason"] == "no candidate passed policy"
    assert len(out["rejected"]) == 2 and all(r["reason"] for r in out["rejected"])
    assert "act" not in [r["node"] for r in log.read_all()]


def test_forbidden_first_then_allowed_second_runs_only_the_allowed_one():
    cands = [Candidate("change_verdict", {"verdict": "FAULT"}), good_candidate()]
    graph, state, log, model, tools, ex = make(model=FakeModel(candidates=cands))
    out = run(graph, state)
    assert out["status"] == "completed" and [a for a, _ in ex.executed] == ["propose_reviewer_label"]
    assert out["rejected"][0]["action"] == "change_verdict"


def test_evidence_bound_action_for_unread_row_is_rejected():
    graph, state, log, model, tools, ex = make(model=FakeModel(candidates=[good_candidate(row_ref=999)]))
    out = run(graph, state)
    assert ex.executed == [] and out["status"] == "abstained"
    assert "not backed by evidence" in out["rejected"][0]["reason"]


def test_malformed_candidate_object_is_rejected():
    graph, state, log, model, tools, ex = make(model=FakeModel(candidates=["delete everything"]))
    out = run(graph, state)
    assert ex.executed == [] and out["status"] == "abstained" and out["rejected"][0]["reason"] == "malformed action name"


@pytest.mark.parametrize("label,toolres,lookup,expect", [
    ("hash missing", evidence_result(evidence_hash=None), None, "hash missing"),
    ("source stale", evidence_result(source_status="stale since 10:00"), None, "source is not live"),
    ("check not run", evidence_result(checks={"repeated_value": "not run", "spike": "ran"}), None, "checks not run: repeated_value"),
    ("hash changed", evidence_result(), Lookup(value="c" * 64), "hash changed"),
    ("evidence gone", evidence_result(), Lookup(value=None), "hash changed or gone"),
])
def test_abstain_on_inadequate_evidence(label, toolres, lookup, expect):
    tools = FakeToolBox({"get_run_summary": toolres, "get_evidence_v1": toolres})
    graph, state, log, model, _, ex = make(toolbox=tools, lookup=lookup)
    out = run(graph, state)
    assert out["status"] == "needs_clarification", label
    assert expect in out["abstain_reason"]
    assert ex.executed == []
    nodes = [r["node"] for r in log.read_all()]
    assert nodes[-1] == "abstain" and "gate" not in nodes and "act" not in nodes


def test_abstain_when_no_evidence_was_read():
    graph, state, log, model, tools, ex = make(perception_plan=[])
    out = run(graph, state)
    assert out["status"] == "needs_clarification" and "no evidence" in out["abstain_reason"] and ex.executed == []


def test_abstain_on_tool_cap():
    # 2 perception calls + 5 model calls = 7 > cap of 6: the 7th is refused and the turn abstains
    model = FakeModel(tool_calls=[("get_overview", {})] * 5)
    tools = FakeToolBox({"get_run_summary": evidence_result(), "get_evidence_v1": evidence_result(), "get_overview": {"runs": 3}})
    graph, state, log, _, _, ex = make(model=model, toolbox=tools)
    out = run(graph, state)
    assert out["tool_cap_hit"] is True and out["tool_call_count"] == 6 and len(tools.calls) == 6
    assert out["status"] == "abstained" and "cap of 6" in out["abstain_reason"]
    assert ex.executed == []


def test_tool_calls_up_to_the_cap_are_allowed():
    model = FakeModel(tool_calls=[("get_overview", {})] * 4)         # 2 + 4 = 6, exactly the cap
    tools = FakeToolBox({"get_run_summary": evidence_result(), "get_evidence_v1": evidence_result(), "get_overview": {"runs": 3}})
    graph, state, *_ , ex = make(model=model, toolbox=tools)
    out = run(graph, state)
    assert out["status"] == "completed" and out["tool_call_count"] == 6


def test_write_tool_is_denied_in_perception_and_to_the_model():
    tools = FakeToolBox({"get_run_summary": evidence_result(), "get_evidence_v1": evidence_result(), "delete_run": {"ok": True}})
    graph, state, log, model, _, ex = make(toolbox=tools, perception_plan=[("get_run_summary", {"run_id": RUN}), ("delete_run", {"run_id": RUN})])
    out = run(graph, state)
    assert ("delete_run", {"run_id": RUN}) not in tools.calls            # the tool was never reached
    assert out["status"] == "abstained" and "read-only" in out["abstain_reason"] and ex.executed == []
    model2 = FakeModel(tool_calls=[("set_threshold", {"v": 1})])
    graph, state, log, _, tools2, ex = make(model=model2)
    out = run(graph, state)
    assert tools2.calls == [("get_run_summary", {"run_id": RUN}), ("get_evidence_v1", {"run_id": RUN, "row_id": ROW})]
    assert out["status"] == "abstained" and ex.executed == []


def test_gate_refuses_when_hash_changed_between_decide_and_act():
    # decide looks up once per evidence ref (2 refs) with the unchanged hash; the gate's later lookups see a changed hash
    graph, state, log, model, tools, ex = make(lookup=Lookup(change_after=2))
    out = run(graph, state)
    assert out["status"] == "gate_refused" and "changed" in out["gate_result"]["reason"]
    assert ex.executed == []
    nodes = [r["node"] for r in log.read_all()]
    assert nodes[-1] == "gate" and "act" not in nodes
    assert log.read_all()[-1]["gate_result"]["ok"] is False


def test_gate_uses_its_own_lookup_independent_of_decide():
    graph, state, log, model, tools, ex = make(lookup=Lookup(), gate_lookup=Lookup(value="d" * 64))
    out = run(graph, state)
    assert out["status"] == "gate_refused" and ex.executed == []


def test_gate_verify_is_independent_of_decide_output():
    """Call the gate directly with a forged state: a forbidden action, a swapped action and a missing explanation are all refused."""
    from backend.app.agent import gate
    graph, state, *_ = make()
    final = {**run(graph, state), "status": "running"}        # the state as the gate saw it, before act set the final status
    assert gate.verify(final, Lookup()).ok
    forged = {**final, "selected": {"action": "change_verdict", "args": {"verdict": "FAULT"}, "rationale": ""}}
    assert "provenance" in gate.verify(forged, Lookup()).reason
    forged["candidates"] = list(final["candidates"]) + [{"action": "change_verdict", "args": {"verdict": "FAULT"}, "rationale": ""}]
    assert "policy" in gate.verify(forged, Lookup()).reason
    no_expl = {**final, "explanation": None}
    assert "explanation" in gate.verify(no_expl, Lookup()).reason
    assert "changed" in gate.verify(final, Lookup(value="e" * 64)).reason


def test_act_outcome_is_the_real_one_never_assumed():
    for result, raises, status, outcome in [({"status": "refused", "detail": "no"}, None, "act_refused", "refused"),
                                            ({"weird": 1}, None, "act_error", "error"),
                                            (None, RuntimeError("db down"), "act_error", "error")]:
        graph, state, log, model, tools, ex = make(executor=FakeExecutor(result=result, raises=raises))
        out = run(graph, state)
        assert out["status"] == status and out["outcome"]["status"] == outcome
        assert log.read_all()[-1]["node"] == "act" and log.read_all()[-1]["outcome"]["status"] == outcome


def test_act_has_exactly_one_incoming_edge_from_gate():
    graph, *_ = make()
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    assert [s for s, t in edges if t == "act"] == ["gate"]
    assert [t for s, t in edges if s == "gate"] and set(t for s, t in edges if s == "gate") == {"act", "__end__"}
    # nothing else (start, perceive, reason, decide, explain, abstain) leads into act
    for node in ("__start__", "perceive", "reason", "decide", "explain", "abstain"):
        assert ("%s" % node, "act") not in edges
    # every path from START to act passes through gate
    adj = {}
    for s, t in edges:
        adj.setdefault(s, set()).add(t)

    def reach(start, blocked):
        seen, stack = set(), [start]
        while stack:
            n = stack.pop()
            if n in seen or n == blocked:
                continue
            seen.add(n)
            stack.extend(adj.get(n, ()))
        return seen
    assert "act" not in reach("__start__", blocked="gate")
    assert "act" in reach("__start__", blocked=None)


def test_explanation_refused_on_invented_number_check_or_station():
    for text in ["Row 42 at ZWL005 had 99.9 mm of rain.",                       # invented number
                 "Station ZWL999 shows the spike check ran.",                    # invented station
                 "Run 7 row 42 ZWL005: the flatline_check fired."]:              # invented check name (snake case)
        graph, state, log, model, tools, ex = make(model=FakeModel(text=text))
        out = run(graph, state)
        assert out["status"] == "explanation_refused", text
        assert out["explanation"] is None and ex.executed == []
        assert "gate" not in [r["node"] for r in log.read_all()]


def test_explanation_refused_on_known_catalogue_check_not_returned():
    graph, state, log, *_, ex = make(model=FakeModel(text="Run 7 at ZWL005: the buddy check agrees."), known_checks=["buddy check", "spike"])
    out = run(graph, state)
    assert out["status"] == "explanation_refused" and "buddy check" in out["abstain_reason"] and ex.executed == []


def test_explanation_accepts_numbers_from_tool_results_and_is_marked_generated():
    graph, state, log, model, tools, ex = make(model=FakeModel(text="Row 42 of run 7 at ZWL005 recorded 12.5 mm; checks repeated_value and spike ran."))
    out = run(graph, state)
    assert out["status"] == "completed"
    exp = out["explanation"]
    assert exp["generated"] is True and exp["basis"]["selected"]["action"] == "propose_reviewer_label" and exp["basis"]["selection_criteria"]
    from backend.app.agent.graph import result_view
    view = result_view(out)
    assert view["prototype"] is True and view["explanation_generated"] is True


def test_rejected_alternatives_are_recorded_with_reasons_in_log():
    cands = [good_candidate(), Candidate("ask_user", {"question": "ok?"}), Candidate("edit_score", {})]
    graph, state, log, *_ = make(model=FakeModel(candidates=cands))
    out = run(graph, state)
    assert len(out["rejected"]) == 2 and all(r["reason"] for r in out["rejected"])
    decide = [r for r in log.read_all() if r["node"] == "decide"][0]
    assert len(decide["rejected_alternatives"]) == 2


def test_model_error_abstains_and_nothing_runs():
    class Boom(FakeModel):
        def propose(self, state, tools):
            raise RuntimeError("quota")
    graph, state, log, model, tools, ex = make(model=Boom())
    out = run(graph, state)
    assert out["status"] == "abstained" and "quota" in out["abstain_reason"] and ex.executed == []
