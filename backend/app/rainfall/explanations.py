"""Explainable reasoning over immutable evidence; AI has no decision write path."""
from __future__ import annotations

import asyncio
import json
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import Field, ValidationError

from .evidence import Contract, DecisionEvidence

MAX_BYTES = 64 * 1024


class Contribution(Contract):
    factor: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)


class Explanation(Contract):
    text: str = Field(min_length=1, max_length=16000)
    contributions: list[Contribution] = Field(max_length=32)
    model_id: str = Field(min_length=1, max_length=200)
    generated: Literal[True] = True
    confidence: None = None


def baseline_explanation(evidence: DecisionEvidence) -> Explanation:
    parts = [f"Decision: {evidence.verdict}. Rule score {evidence.rule_score:g} (computed, uncalibrated; not a probability).",
             "The score combines the fixed weights of fired checks as one minus the product of one minus each weight."]
    contributions = []
    for check in evidence.checks:
        observed = check.observed
        value = "unavailable" if observed.value is None else f"{observed.value:g} {observed.unit} ({observed.basis})"
        params = ", ".join(f"{k}: {v.value:g} {v.unit} ({v.basis})" for k, v in check.threshold.parameters.items() if v.value is not None)
        note = (f"{check.reason}. Observed: {value}. {check.threshold.description} {params}. "
                f"Check weight {check.weight.value:g} (assumed design choice). {check.threshold.why}")
        contributions.append(Contribution(factor=check.check, note=note))
        parts.append(note)
    if not evidence.checks:
        parts.append("No available check fired; this does not prove the reading is correct.")
    if evidence.verdict == "UNCERTAIN":
        parts.append("The evidence is inconclusive; local rainfall can differ between gauges. This is not a proven fault.")
    elif evidence.verdict == "SUSPECT":
        parts.append("A rule or internal consistency check fired. SUSPECT is not a diagnosis of sensor failure.")
    parts.extend(evidence.limitations)
    parts.append("Checks not run: " + "; ".join(evidence.not_run))
    return Explanation(text=" ".join(parts), contributions=contributions, model_id="baseline-rules-v1")


async def narrate(evidence: DecisionEvidence, url: str, token: str = "", transport=None) -> tuple[Explanation | None, str]:
    if not url:
        return None, "AI narrator not connected"
    if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
        return None, "AI narrator URL is invalid; baseline shown"
    payload = {"schema_version": "evidence-v1", "run_id": evidence.run_id,
               "row_ref": evidence.row_ref, "evidence": evidence.model_dump()}
    if len(json.dumps(payload).encode()) > MAX_BYTES:
        return None, "AI narrator payload exceeds limit; baseline shown"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async def fetch():
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, transport=transport) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("Response exceeds limit")
                return bytes(data)

    try:
        data = await asyncio.wait_for(fetch(), timeout=20)
        result = Explanation.model_validate_json(data)
        if not result.text.strip() or not result.model_id.strip():
            raise ValueError("Empty explanation")
        checks = {c.check for c in evidence.checks}
        if any(c.factor not in checks for c in result.contributions):
            raise ValueError("Unknown evidence contribution")
        return result, "AI-generated; verify against the evidence"
    except (httpx.HTTPError, asyncio.TimeoutError, ValidationError, ValueError):
        # Never return server bodies/URLs: they may contain secrets.
        return None, "AI narrator failed or returned an invalid explanation; baseline shown"
