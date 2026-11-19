"""Orchestrate explanations without giving a narrator any mutable decision state."""
import asyncio
import time

from .evidence import DecisionEvidence
from .explanations import baseline_explanation, narrate
from .explanation_store import save_explanation


class ExplanationService:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._last_call = {}

    async def explain(self, session, evidence: DecisionEvidence, use_narrator: bool, url: str, token: str):
        baseline = baseline_explanation(evidence)
        narrator, status = None, "AI explanation not requested"
        if use_narrator:
            if not url:
                status = "AI narrator not connected"
            else:
                # One outbound call per station per minute; no quota spent by GET requests.
                async with self._lock:
                    now = time.monotonic()
                    self._last_call = {k: t for k, t in self._last_call.items() if now - t < 60}
                    allowed = evidence.station_id not in self._last_call
                    if allowed:
                        self._last_call[evidence.station_id] = now
                if allowed:
                    narrator, status = await narrate(evidence, url, token)
                else:
                    status = "AI narrator rate limit reached; baseline shown"
        return await save_explanation(session, evidence, baseline, narrator, status)
