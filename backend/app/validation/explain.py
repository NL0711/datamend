"""The Explainer seam (spec section 6): one interface, two implementations.

* BaselineExplainer ships with the platform: it fills a template from the evidence. It can explain a fired check; it cannot answer a
  free-text question (no canned chat answers) and it computes no confidence.
* NarratorExplainer calls the AI team's service at NARRATOR_URL. NOT IMPLEMENTED on the narrator side until they deliver; the request
  and response shape (docs/contracts/narrator-request-v1.md) is a proposal awaiting their confirmation.

An explanation is generated text, stored separately and always marked generated. It never changes a verdict, score or evidence.
"""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Protocol
from urllib.parse import urlparse

import httpx

MAX_REQUEST_BYTES = 64 * 1024
MAX_TEXT_CHARS = 4000
NARRATOR_CALLS_PER_MINUTE = 30


class NarratorUnavailable(RuntimeError):
    """No narrator is configured, or it did not give a usable answer."""


class NarratorRateLimited(NarratorUnavailable):
    pass


@dataclass
class Explanation:
    text: str
    contributions: List[Dict[str, Any]]
    model_id: str
    generator: str
    generated: bool = True
    confidence: Optional[float] = None    # only ever the narrator's own number


class Explainer(Protocol):
    generator: str

    async def explain(self, evidence: Optional[Dict[str, Any]], question: Optional[str] = None, kind: str = "explain",
                      context: Optional[Dict[str, Any]] = None) -> Explanation: ...


# ------------------------------------------------------------------------------------------------ baseline

class BaselineExplainer:
    generator = "baseline-rules"
    model_id = "baseline-rules-v1"

    async def explain(self, evidence: Optional[Dict[str, Any]], question: Optional[str] = None, kind: str = "explain",
                      context: Optional[Dict[str, Any]] = None) -> Explanation:
        if question or kind == "chat":
            raise NarratorUnavailable("the rule-based baseline can only explain a fired check; it cannot answer questions")
        if not evidence:
            raise NarratorUnavailable("no evidence to explain")
        return Explanation(self.text(evidence), [{"check": evidence["check"], "weight": evidence.get("weight"), "note": evidence["reason"]}],
                           self.model_id, self.generator)

    @staticmethod
    def text(ev: Dict[str, Any]) -> str:
        row, parts = ev["row"], []
        parts.append(f"Check '{ev['check']}' fired on row {row['row_ref']} of station {row['station_id']}: {ev['reason']}.")
        obs = ev.get("observed")
        if obs:
            parts.append(f"Observed {obs['value']:g} {obs['unit']} ({obs['basis']}).")
        thr = ev.get("threshold")
        if thr:
            parts.append(f"Threshold {thr['value']} ({thr['why']}; {thr['basis']}).")
        nb = ev.get("neighbours")
        if nb:
            wet = sum(1 for n in nb if n["wet"])
            parts.append(f"{len(nb)} neighbouring station(s) within range were compared: {wet} wet, {len(nb) - wet} dry.")
        if ev.get("history"):
            parts.append(f"The gauge's own history had {ev['history']['n_wet_days']} earlier wet days near this day of the year (derived).")
        effect = {"fault": "a fault-kind check, so the row is SUSPECT", "uncertain": "an uncertainty-kind check, so the row is UNCERTAIN, not called a fault",
                  "info": "informational only; it does not change the verdict"}[ev["kind"]]
        parts.append(f"This is {effect}. Rule score {row['rule_score']:g} (an uncalibrated ordering of suspicion, not a probability).")
        assumed = [k for k in ("observed", "threshold") if ev.get(k, {}).get("basis") == "assumed"]
        if ev.get("time_basis") == "received":
            parts.append("Times are when this platform received the reading, so gap and neighbour comparisons are weaker.")
        if "observed" in assumed:
            parts.append("The unit of the observed value is assumed, not confirmed.")
        parts.append("This text is generated from the evidence by fixed rules.")
        return " ".join(parts)


# ------------------------------------------------------------------------------------------------ narrator

class _Limiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute, self.calls = per_minute, deque()   # type: ignore[var-annotated]

    def take(self) -> None:
        now = time.monotonic()
        calls: Deque[float] = self.calls
        while calls and now - calls[0] > 60.0:
            calls.popleft()
        if len(calls) >= self.per_minute:
            raise NarratorRateLimited(f"narrator calls are limited to {self.per_minute} per minute")
        calls.append(now)


_limiter = _Limiter(NARRATOR_CALLS_PER_MINUTE)


class NarratorExplainer:
    generator = "mcp-narrator"

    def __init__(self, url: str, token: str = "", timeout: float = 20.0, transport: Optional[httpx.AsyncBaseTransport] = None,
                 limiter: Optional[_Limiter] = None) -> None:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError("NARRATOR_URL must be an http or https URL")
        self.url, self.token, self.timeout, self._transport = url, token, timeout, transport
        self._limiter = limiter or _limiter

    @property
    def host(self) -> str:
        return urlparse(self.url).netloc

    async def explain(self, evidence: Optional[Dict[str, Any]], question: Optional[str] = None, kind: str = "explain",
                      context: Optional[Dict[str, Any]] = None) -> Explanation:
        body: Dict[str, Any] = {"schema": "narrator-request-v1", "kind": kind}
        if evidence is not None:
            body["evidence"] = evidence
        if question:
            body["question"] = question
        if context:
            body["context"] = context
        raw = json.dumps(body, default=str).encode()
        if len(raw) > MAX_REQUEST_BYTES:
            raise NarratorUnavailable("the request is larger than the 64 KB limit")
        self._limiter.take()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport, follow_redirects=False) as client:
                resp = await client.post(self.url, content=raw, headers=headers)
        except httpx.HTTPError as e:
            raise NarratorUnavailable(f"the narrator did not answer ({type(e).__name__})")
        if resp.status_code != 200:
            raise NarratorUnavailable(f"the narrator answered HTTP {resp.status_code}")
        return self._parse(resp)

    def _parse(self, resp: httpx.Response) -> Explanation:
        try:
            d = resp.json()
        except ValueError:
            raise NarratorUnavailable("the narrator's reply is not JSON")
        text, model_id = d.get("text") if isinstance(d, dict) else None, d.get("model_id") if isinstance(d, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise NarratorUnavailable(f"the narrator's reply has no usable 'text' (1 to {MAX_TEXT_CHARS} characters)")
        if not isinstance(model_id, str) or not model_id.strip():
            raise NarratorUnavailable("the narrator's reply has no 'model_id'")
        contrib = d.get("contributions", [])
        if not isinstance(contrib, list) or not all(isinstance(c, dict) for c in contrib):
            raise NarratorUnavailable("the narrator's 'contributions' must be a list of objects")
        conf = d.get("confidence")
        if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float))):
            raise NarratorUnavailable("the narrator's 'confidence' must be a number or null")
        clean = [{"check": str(c.get("check", ""))[:48], "note": str(c.get("note", ""))[:500]} for c in contrib[:20]]
        return Explanation(text.strip(), clean, model_id.strip()[:96], self.generator, True, float(conf) if conf is not None else None)
