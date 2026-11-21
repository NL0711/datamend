"""HTTP client of the separate Keras scorer service (ml-service/scorer). The web process never imports TensorFlow.

One call per reading carries every full window (at most 8 per request). Any failure raises ``ScorerUnavailable`` and starts a back-off during
which no call is made, so a slow or dead scorer never stalls the stream; a score is never invented. The secret is never logged.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

import httpx

logger = logging.getLogger(__name__)

BACKOFF_SECONDS = 30.0
MAX_WINDOWS = 8


class ScorerUnavailable(Exception):
    """The scorer could not answer; the message is the reason shown ('scorer not available: <reason>')."""


class ScorerClient:
    def __init__(self, url: str, secret: str = "", timeout: float = 2.0, transport: Optional[httpx.AsyncBaseTransport] = None,
                 clock: Callable[[], float] = time.monotonic, backoff_s: float = BACKOFF_SECONDS) -> None:
        self.url = url.rstrip("/")
        self._secret = secret
        self.timeout = timeout
        self._transport = transport
        self._clock = clock
        self.backoff_s = backoff_s
        self._down_until = 0.0
        self.last_error: Optional[str] = None
        self.calls = 0
        self._shared: Optional[httpx.AsyncClient] = None

    @asynccontextmanager
    async def bulk(self, timeout: Optional[float] = None, backoff_s: Optional[float] = None) -> AsyncIterator[None]:
        """For a long run of calls: one shared connection, a longer timeout and a shorter back-off while it lasts; the settings are restored after."""
        old_timeout, old_backoff = self.timeout, self.backoff_s
        self.timeout = timeout if timeout is not None else old_timeout
        self.backoff_s = backoff_s if backoff_s is not None else old_backoff
        self._down_until = 0.0
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as http:
            self._shared = http
            try:
                yield
            finally:
                self._shared = None
                self.timeout, self.backoff_s = old_timeout, old_backoff

    async def wake(self, max_wait_s: float = 60.0, pause_s: float = 3.0, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep) -> bool:
        """GET /health until it answers 200 (a sleeping free-tier service takes many seconds), for about ``max_wait_s``. Never blocks forever."""
        waited = 0.0
        while True:
            try:
                async with httpx.AsyncClient(timeout=min(15.0, max(1.0, max_wait_s)), transport=self._transport) as http:
                    if (await http.get(f"{self.url}/health")).status_code == 200:
                        return True
            except (httpx.HTTPError, ValueError):
                pass
            waited += pause_s            # counted, not read from a clock: pauses (plus bounded request time) add up to about max_wait_s
            if waited >= max_wait_s:
                return False
            await sleep(pause_s)

    async def _post_chunks(self, http: httpx.AsyncClient, windows: Sequence[Sequence[float]], errors: List[float], model: Dict[str, Any]) -> Tuple[List[float], Dict[str, Any]]:
        for i in range(0, len(windows), MAX_WINDOWS):
            chunk = [list(w) for w in windows[i:i + MAX_WINDOWS]]
            self.calls += 1
            resp = await http.post(f"{self.url}/score", json={"windows": chunk}, headers={"X-Scorer-Secret": self._secret})
            if resp.status_code != 200:
                raise self._fail(f"HTTP {resp.status_code}")
            body = resp.json()
            errs = body.get("errors")
            if not isinstance(errs, list) or len(errs) != len(chunk) or not all(isinstance(e, (int, float)) and e == e and abs(e) != float("inf") for e in errs):
                raise self._fail("malformed answer")
            errors.extend(float(e) for e in errs)
            model = body.get("model") or model
        return errors, model

    def _fail(self, reason: str) -> "ScorerUnavailable":
        self._down_until = self._clock() + self.backoff_s
        self.last_error = reason
        logger.warning("scorer not available: %s (backing off %.0f s)", reason, self.backoff_s)
        return ScorerUnavailable(reason)

    async def score(self, windows: Sequence[Sequence[float]]) -> Tuple[List[float], Dict[str, Any]]:
        """Reconstruction error per window, plus the model block the service reports. Raises ScorerUnavailable."""
        if not windows:
            return [], {}
        if self._clock() < self._down_until:
            raise ScorerUnavailable(f"backing off after: {self.last_error}")
        errors: List[float] = []
        model: Dict[str, Any] = {}
        try:
            if self._shared is not None:         # a bulk run (the startup backfill) keeps one connection open instead of a handshake per call
                errors, model = await self._post_chunks(self._shared, windows, errors, model)
            else:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as http:
                    errors, model = await self._post_chunks(http, windows, errors, model)
        except ScorerUnavailable:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise self._fail(type(exc).__name__ + (f": {exc}" if str(exc) else "")) from exc
        self.last_error = None
        return errors, model
