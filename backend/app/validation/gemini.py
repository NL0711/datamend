"""Interim LLM layer on Google Gemini: a third ``Explainer`` and the source of the LLM ``Proposer``.

Used while the AI team's MCP narrator is not connected (a set NARRATOR_URL always wins, see narrate.get_narrator). Rules:

* Only the evidence payload (rainfall values, thresholds, station ids, row references) and the user's question are sent. Never the key,
  never reviewer names. The key goes in a request header (not the URL), so it cannot end up in a logged URL, and it is never stored,
  returned or logged here.
* The reply must be JSON of a fixed shape. Any number in the text that is not in what was sent is refused (no invented figures).
* The reply is generated text. It never changes a verdict, score or evidence; the callers store it apart, marked generated.
* A per-minute limit and a per-day call budget protect the quota. Tests use a mocked transport and never the real API.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from datetime import date
from typing import Any, Deque, Dict, List, Optional

import httpx

from backend.app.validation.explain import (MAX_REQUEST_BYTES, MAX_TEXT_CHARS, Explanation, NarratorRateLimited, NarratorUnavailable,
                                            allowed_checks, check_contributions)

GENERATOR = "gemini"
PROPOSAL_LABELS = ("confirmed_fault", "false_alarm", "genuine_extreme", "needs_followup")
HOST = "generativelanguage.googleapis.com"

SYSTEM_EXPLAIN = (
    "You explain rainfall data-quality flags for a reviewer. You are given the evidence of one fired check as JSON. "
    "Use only facts and numbers present in that JSON. Do not invent values, stations, dates or causes you cannot read from it. "
    "Never say a reading is correct or wrong with certainty: a high value alone is not a fault, and the rule score is an uncalibrated "
    "ordering, not a probability. Say what was observed, what the check compared it with, and what the reviewer could check next. "
    "Be brief (at most 120 words). Reply as JSON: {\"text\": string, \"contributions\": [{\"check\": string, \"note\": string}]}."
)
SYSTEM_CHAT = (
    "You answer a reviewer's question about a rainfall validation run. You are given JSON context and optionally the evidence of one flag. "
    "Answer only from that JSON; if it does not contain the answer, say so. Do not invent numbers. You cannot change any verdict, score or "
    "evidence. Be brief (at most 150 words). Reply as JSON: {\"text\": string, \"contributions\": [{\"check\": string, \"note\": string}]}."
)
SYSTEM_PROPOSE = (
    "You propose a reviewer label for one flagged rainfall station-day. You are given the evidence of each fired check as JSON. "
    "Labels: confirmed_fault (the value is very likely an instrument or transmission fault), false_alarm (the checks fired but the "
    "value looks plausible), genuine_extreme (an unusual but real rain event, for example confirmed by neighbouring stations), "
    "needs_followup (the evidence is not enough). Magnitude alone is never a fault. Prefer needs_followup when unsure. Use only numbers in "
    "the JSON. Reply as JSON: {\"label\": one of the four labels, \"reason\": string of at most 60 words}."
)

_EXPLAIN_SCHEMA = {"type": "OBJECT", "properties": {
    "text": {"type": "STRING"},
    "contributions": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"check": {"type": "STRING"}, "note": {"type": "STRING"}}}}},
    "required": ["text"]}
_PROPOSE_SCHEMA = {"type": "OBJECT", "properties": {"label": {"type": "STRING", "enum": list(PROPOSAL_LABELS)}, "reason": {"type": "STRING"}},
                   "required": ["label", "reason"]}

_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def numbers_in(obj: Any) -> List[float]:
    """Every number that appears in a JSON-like object (values and text), for the no-invented-numbers check."""
    return [float(m.group()) for m in _NUM.finditer(json.dumps(obj, default=str))]


def invented_numbers(text: str, sent: Any, free_int_max: int = 24) -> List[str]:
    """Numbers in ``text`` that are not in ``sent`` (within 0.5 percent). Small whole numbers (counts, hours) are allowed."""
    known = numbers_in(sent)
    bad: List[str] = []
    for m in _NUM.finditer(text):
        tok = m.group()
        v = float(tok)
        if v == int(v) and abs(v) <= free_int_max and "." not in tok:
            continue
        if not any(abs(v - k) <= max(0.005 * abs(k), 1e-9) for k in known):
            bad.append(tok)
    return bad


class _DayBudget:
    def __init__(self, limit: int) -> None:
        self.limit, self.day, self.used = limit, date.today(), 0

    def take(self) -> None:
        today = date.today()
        if today != self.day:
            self.day, self.used = today, 0
        if self.used >= self.limit:
            raise NarratorRateLimited(f"the daily Gemini call budget ({self.limit}) is used up; it resets tomorrow or raise GEMINI_DAILY_CALL_BUDGET")
        self.used += 1


class _Minute:
    def __init__(self, per_minute: int) -> None:
        self.per_minute, self.calls = per_minute, deque()   # type: ignore[var-annotated]

    def take(self) -> None:
        now = time.monotonic()
        calls: Deque[float] = self.calls
        while calls and now - calls[0] > 60.0:
            calls.popleft()
        if len(calls) >= self.per_minute:
            raise NarratorRateLimited(f"Gemini calls are limited to {self.per_minute} per minute")
        calls.append(now)


_shared: Dict[str, Any] = {}


def _limits(per_minute: int, per_day: int):
    key = f"{per_minute}/{per_day}"
    if key not in _shared:
        _shared.clear()
        _shared[key] = (_Minute(per_minute), _DayBudget(per_day))
    return _shared[key]


class GeminiExplainer:
    """Same interface as NarratorExplainer (``explain(evidence, question, kind, context)``), plus ``propose_label``."""
    generator = GENERATOR

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash", base_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 timeout: float = 30.0, per_minute: int = 10, per_day: int = 200, transport: Optional[httpx.AsyncBaseTransport] = None,
                 limits: Optional[Any] = None) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("a Gemini API key is required")
        if not re.fullmatch(r"[A-Za-z0-9._\-]{1,80}", model or ""):
            raise ValueError("GEMINI_MODEL must be a plain model id such as gemini-flash-latest")
        if not base_url.startswith("https://"):
            raise ValueError("GEMINI_BASE_URL must be an https URL")
        self._key, self.model, self.base_url, self.timeout, self._transport = api_key.strip(), model, base_url.rstrip("/"), timeout, transport
        self._limits = limits or _limits(per_minute, per_day)
        self.retry_wait = 2.0

    # status helpers (never include the key)
    @property
    def host(self) -> str:
        return HOST if self.base_url.startswith("https://" + HOST) else self.base_url.split("/")[2]

    @property
    def model_id(self) -> str:
        return f"gemini:{self.model}"

    async def _call(self, system: str, payload: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        user = json.dumps(payload, default=str)
        if len(user.encode()) > MAX_REQUEST_BYTES:
            raise NarratorUnavailable("the request is larger than the 64 KB limit")
        for lim in self._limits:
            lim.take()
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0.2, "maxOutputTokens": 1024}}
        url = f"{self.base_url}/models/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport, follow_redirects=False) as client:
                resp = await client.post(url, json=body, headers={"x-goog-api-key": self._key})
                if resp.status_code == 503:                    # "high demand" spikes are usual and short: one retry, then say so
                    await asyncio.sleep(self.retry_wait)
                    resp = await client.post(url, json=body, headers={"x-goog-api-key": self._key})
        except httpx.HTTPError as e:
            raise NarratorUnavailable(f"Gemini did not answer ({type(e).__name__})")
        if resp.status_code == 503:
            raise NarratorUnavailable("Gemini is under high demand (HTTP 503); try again in a moment or set another GEMINI_MODEL")
        if resp.status_code == 404:
            raise NarratorUnavailable(f"Gemini does not offer the model {self.model!r} (HTTP 404); set GEMINI_MODEL")
        if resp.status_code == 429:
            raise NarratorRateLimited("Gemini says the quota is used up (HTTP 429)")
        if resp.status_code in (400, 401, 403):
            raise NarratorUnavailable(f"Gemini refused the request (HTTP {resp.status_code}); check GEMINI_API_KEY and GEMINI_MODEL")
        if resp.status_code != 200:
            raise NarratorUnavailable(f"Gemini answered HTTP {resp.status_code}")
        return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> Dict[str, Any]:
        try:
            d = resp.json()
            cand = d["candidates"][0]
        except (ValueError, KeyError, IndexError, TypeError):
            raise NarratorUnavailable("Gemini's reply has no answer (it may have been blocked)")
        if cand.get("finishReason") not in (None, "STOP"):
            raise NarratorUnavailable(f"Gemini did not finish the answer ({cand.get('finishReason')})")
        try:
            raw = "".join(p.get("text", "") for p in cand["content"]["parts"])
            out = json.loads(raw)
        except (KeyError, TypeError, ValueError):
            raise NarratorUnavailable("Gemini's reply is not the JSON shape asked for")
        if not isinstance(out, dict):
            raise NarratorUnavailable("Gemini's reply is not the JSON shape asked for")
        return out

    async def explain(self, evidence: Optional[Dict[str, Any]], question: Optional[str] = None, kind: str = "explain",
                      context: Optional[Dict[str, Any]] = None) -> Explanation:
        payload: Dict[str, Any] = {}
        if evidence is not None:
            payload["evidence"] = evidence
        if context:
            payload["context"] = context
        if question:
            payload["question"] = question
        if kind == "explain" and evidence is None:
            raise NarratorUnavailable("no evidence to explain")
        out = await self._call(SYSTEM_CHAT if kind == "chat" else SYSTEM_EXPLAIN, payload, _EXPLAIN_SCHEMA)
        text = out.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise NarratorUnavailable(f"Gemini's reply has no usable 'text' (1 to {MAX_TEXT_CHARS} characters)")
        bad = invented_numbers(text, payload)
        if bad:
            raise NarratorUnavailable(f"Gemini's reply cites numbers that are not in the evidence ({', '.join(bad[:5])}); it was discarded")
        contrib = out.get("contributions", [])
        if not isinstance(contrib, list):
            contrib = []
        clean = [{"check": str(c.get("check", ""))[:48], "note": str(c.get("note", ""))[:500]} for c in contrib[:20] if isinstance(c, dict)]
        check_contributions(clean, allowed_checks(evidence, context))
        return Explanation(text.strip(), clean, self.model_id[:96], self.generator, True, None)

    async def propose_label(self, evidences: List[Dict[str, Any]]) -> Dict[str, str]:
        """A proposed reviewer label and reason for one flagged row. The label is one of PROPOSAL_LABELS; the reason has no invented numbers."""
        if not evidences:
            raise NarratorUnavailable("no evidence to propose from")
        payload = {"evidence": evidences}
        out = await self._call(SYSTEM_PROPOSE, payload, _PROPOSE_SCHEMA)
        label, reason = out.get("label"), out.get("reason")
        if label not in PROPOSAL_LABELS:
            raise NarratorUnavailable("Gemini proposed a label that is not one of the four allowed")
        if not isinstance(reason, str) or not reason.strip():
            raise NarratorUnavailable("Gemini gave no reason")
        reason = reason.strip()[:600]
        bad = invented_numbers(reason, payload)
        if bad:
            raise NarratorUnavailable(f"Gemini's reason cites numbers that are not in the evidence ({', '.join(bad[:5])}); it was discarded")
        return {"label": label, "reason": reason}
