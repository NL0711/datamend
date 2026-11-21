"""Gemini adapter for the agent's model interface, through `langchain-google-genai` (slice S6 skeleton).

NOT VERIFIED LIVE: no call to Gemini has been made from this code. Imports and object construction were checked offline only.
The key comes from the environment (GEMINI_API_KEY) or the caller; the model name from AGENT_MODEL or the caller. Nothing is hardcoded and
nothing is created at import time: `langchain_google_genai` is imported inside the constructor.

The adapter does not bind tools to Gemini yet (`propose` ignores its `tools` handle): perception is the graph's own read-only plan. Letting
the model call tools itself (through `langchain-mcp-adapters`) is a LATER step, and would still go through the GuardedTools handle.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import policy
from .state import AgentState, Candidate


class AgentNotConnected(RuntimeError):
    """No provider key or package: the agent reports 'agent not connected' and the rule-based baseline keeps explaining."""


_SYSTEM = (
    "You are a bounded decision-support assistant for rainfall and weather data validation (a prototype). You only PROPOSE actions; you never "
    "execute anything and you never change a verdict, score, evidence, raw data, setting, secret or source. Use ONLY the facts in the "
    "evidence JSON provided: do not state any number, check name or station id that is not in it. If the evidence is not enough, propose "
    "ask_user. For propose_reviewer_label, label must be exactly one of " + ", ".join(policy.REVIEWER_LABELS) + " (a verdict such as SUSPECT is not a label); "
    "row_ref is the row id from the evidence. Allowed actions and arguments: " + json.dumps({k: sorted(v.required | v.optional) for k, v in policy.ALLOWED_ACTIONS.items()})
)


class TokenBudgetExceeded(RuntimeError):
    """The evidence is larger than the per-call token budget; the graph abstains instead of cutting it."""


class GeminiAgentModel:
    def __init__(self, *, api_key: Optional[str] = None, model: Optional[str] = None, temperature: float = 0.0, timeout: float = 30.0,
                 token_budget: Optional[int] = None) -> None:
        self.token_budget = token_budget          # assumed: input estimated as characters / 4; also the cap on output tokens
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        name = model or os.environ.get("AGENT_MODEL", "")
        if not key:
            raise AgentNotConnected("GEMINI_API_KEY is not set")
        if not name:
            raise AgentNotConnected("AGENT_MODEL is not set")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from pydantic import BaseModel, Field
        except ImportError as exc:
            raise AgentNotConnected(f"langchain-google-genai is not installed: {exc}") from exc

        class _Proposal(BaseModel):
            action: str = Field(description="one of the allowed action names")
            args_json: str = Field(description="the action's arguments as a JSON object string")
            rationale: str = Field(description="why, using only facts from the evidence")

        class _Proposals(BaseModel):
            candidates: list[_Proposal]

        self.model_id = name
        extra = {"max_output_tokens": int(token_budget)} if token_budget else {}
        self._llm = ChatGoogleGenerativeAI(model=name, google_api_key=key, temperature=temperature, timeout=timeout, **extra)
        self._structured = self._llm.with_structured_output(_Proposals)

    def _evidence_json(self, state: AgentState) -> str:
        text = self._evidence_json_raw(state)
        if self.token_budget and len(text) / 4 > self.token_budget:
            raise TokenBudgetExceeded(f"the evidence is about {len(text) // 4} tokens (estimated), over the budget of {self.token_budget}")
        return text

    @staticmethod
    def _evidence_json_raw(state: AgentState) -> str:
        return json.dumps({"objective": state.get("objective"), "constraints": {k: v for k, v in state.get("constraints", {}).items() if k != "perception_plan"},
                           "evidence": [{k: ev.get(k) for k in ("ref_id", "tool", "run_id", "row_ref", "station_id", "source_status", "checks", "result")}
                                        for ev in state.get("evidence", [])]}, default=str)

    def propose(self, state: AgentState, tools: Any) -> list[Candidate]:           # `tools` is unused for now (see module docstring)
        out = self._structured.invoke([("system", _SYSTEM), ("human", self._evidence_json(state))])
        cands: list[Candidate] = []
        for p in out.candidates:
            try:
                args = json.loads(p.args_json)
            except ValueError:
                args = {"_malformed": p.args_json}          # policy rejects it; never repaired silently
            if isinstance(args, dict):
                for k in ("run_id", "row_ref"):          # the model sometimes writes ids as strings; the evidence holds integers (same value, not a repair of content)
                    if isinstance(args.get(k), str) and args[k].strip().isdigit():
                        args[k] = int(args[k])
            cands.append(Candidate(p.action, args if isinstance(args, dict) else {"_malformed": p.args_json}, p.rationale))
        return cands

    def explain(self, state: AgentState) -> str:
        sel = json.dumps({"selected": state.get("selected"), "criteria": state.get("selection_criteria"), "rejected": state.get("rejected")}, default=str)
        msg = self._llm.invoke([("system", _SYSTEM + " Now write a short plain-text account of why the selected action was chosen and the others rejected."),
                                ("human", self._evidence_json(state) + "\n" + sel)])
        text = msg.content
        return text if isinstance(text, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
