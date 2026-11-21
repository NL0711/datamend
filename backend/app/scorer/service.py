"""ModelScorer: the score provider for the pretrained Keras reconstruction model (keras-io/timeseries-anomaly-detection, used as is).

It never produces a verdict. It returns a ``provider`` block per reading: per variable a reconstruction error (when the 288-reading window is
full and the scorer answered), a threshold (only once enough clean scores exist) and a flag. The model is NOT validated on this platform's data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from backend.app.scorer.client import ScorerClient, ScorerUnavailable
from backend.app.scorer.threshold import ThresholdStore
from backend.app.scorer.window import SCALING, VARIABLES, WINDOW, WindowStore

MODEL_ID = "keras-io/timeseries-anomaly-detection"
NOTE = "not validated"
SCORE_KIND = "model reconstruction error, not validated"
VALUE_ATTR = {"temperature": "temperature_c", "pressure": "pressure_hpa", "humidity": "humidity_pct"}


class ModelScorer:
    def __init__(self, client: Optional[ScorerClient] = None, windows: Optional[WindowStore] = None, thresholds: Optional[ThresholdStore] = None) -> None:
        self.client = client
        self.windows = windows or WindowStore()
        self.thresholds = thresholds or ThresholdStore()
        self.revision: Optional[str] = None

    @classmethod
    def from_settings(cls) -> "ModelScorer":
        from backend.app.config import settings
        if not settings.SCORER_URL:
            return cls(None)
        return cls(ScorerClient(settings.SCORER_URL, settings.SCORER_SECRET, settings.SCORER_TIMEOUT_SECONDS),
                   thresholds=ThresholdStore(settings.SCORER_FALSE_ALARM_BUDGET, settings.SCORER_MIN_CLEAN_SCORES))

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def needs_hydration(self, station_id: str) -> bool:
        return self.enabled and station_id not in self.windows

    def hydrate(self, station_id: str, rows: Sequence[Dict[str, Optional[float]]]) -> None:
        self.windows.seed(station_id, rows)

    async def score(self, reading: Any, check_status: str) -> Optional[Dict[str, Any]]:
        """The provider block for one reading (None when no scorer is configured). ``check_status`` is the checks' verdict, used only to decide
        whether the error counts as clean for the threshold; the verdict itself is never changed here."""
        if self.client is None:
            return None
        sid = reading.station_id
        self.windows.mark(sid)
        full: Dict[str, List[float]] = {}
        counts: Dict[str, int] = {}
        for var in VARIABLES:
            value = getattr(reading, VALUE_ATTR[var])
            counts[var] = self.windows.push(sid, var, value)
            w = self.windows.scaled(sid, var)
            if w is not None:
                full[var] = w
        errors: Dict[str, float] = {}
        unavailable: Optional[str] = None
        if full:
            try:
                got, model = await self.client.score(list(full.values()))
                errors = dict(zip(full.keys(), got))
                self.revision = model.get("revision") or self.revision
            except ScorerUnavailable as exc:
                unavailable = f"scorer not available: {exc}"
        out: Dict[str, Dict[str, Any]] = {}
        calibrated = False
        for var in VARIABLES:
            base: Dict[str, Any] = {"window": WINDOW, "scaling": SCALING}
            if var in errors:
                err = errors[var]
                thr = self.thresholds.threshold(sid, var)           # earlier clean errors only
                flagged = thr is not None and err > thr
                calibrated = calibrated or thr is not None
                reason = None if thr is not None else self.thresholds.reason(sid, var)
                out[var] = {"status": "scored", "error": err, "threshold": thr, "flagged": flagged, "reason": reason, **base}
                if check_status == "OK" and not flagged:
                    self.thresholds.add_clean(sid, var, err)
            elif var in full:
                out[var] = {"status": "unavailable", "error": None, "threshold": None, "flagged": False, "reason": unavailable, **base}
            elif getattr(reading, VALUE_ATTR[var]) is None:
                out[var] = {"status": "not_run", "error": None, "threshold": None, "flagged": False,
                            "reason": f"not run: no {var} value in this reading (window reset); have {counts[var]}", **base}
            else:
                out[var] = {"status": "not_run", "error": None, "threshold": None, "flagged": False, "reason": self.windows.warmup_reason(sid, var), **base}
        return {"model_id": MODEL_ID, "revision": self.revision, "calibrated": calibrated, "validated": False, "note": NOTE, "variables": out}


def flagged_variables(provider: Optional[Dict[str, Any]]) -> List[str]:
    if not provider:
        return []
    return [v for v, d in provider["variables"].items() if d.get("flagged")]


def compact(provider: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """What is stored with a reading or event: per-variable status, error, threshold, flag and reason (constants are re-added on read)."""
    if provider is None:
        return None
    keep = ("status", "error", "threshold", "flagged", "reason")
    return {"model_id": provider["model_id"], "revision": provider["revision"], "calibrated": provider["calibrated"],
            "variables": {v: {k: d[k] for k in keep if d.get(k) is not None or k in ("status", "flagged")} for v, d in provider["variables"].items()}}


def expand(stored: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A stored compact block back to the full provider block shape."""
    if not stored:
        return None
    variables = {v: {"error": None, "threshold": None, "reason": None, **d, "window": WINDOW, "scaling": SCALING} for v, d in (stored.get("variables") or {}).items()}
    return {"model_id": stored.get("model_id", MODEL_ID), "revision": stored.get("revision"), "calibrated": bool(stored.get("calibrated")), "validated": False,
            "note": NOTE, "variables": variables}
