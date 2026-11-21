"""Keras scorer backend side: windowing, z-score, threshold, client back-off and the provider block. A httpx.MockTransport stub (labelled fake)
returns KNOWN errors; no network, no TensorFlow."""
import json
import math
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.app.scorer.client import ScorerClient, ScorerUnavailable
from backend.app.scorer.service import MODEL_ID, ModelScorer, compact, expand
from backend.app.scorer.threshold import ThresholdStore
from backend.app.scorer.window import WINDOW, WindowStore, zscore
from backend.app.stream.types import StreamReading

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


class Stub:
    """Fake scorer service: every window gets the error in ``self.error`` (or the per-call list); records requests."""
    def __init__(self, error=0.1, status=200):
        self.error, self.status, self.requests = error, status, []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        self.requests.append((req.headers.get("X-Scorer-Secret"), body))
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "x"})
        n = len(body["windows"])
        errs = self.error if isinstance(self.error, list) else [self.error] * n
        return httpx.Response(200, json={"errors": errs[:n], "model": {"id": MODEL_ID, "revision": "abc123", "format": "savedmodel"}})


def rd(i, t=20.0, p=1000.0, rh=50.0):
    return StreamReading("S1", T0 + timedelta(minutes=i), "fake", temperature_c=t, pressure_hpa=p, humidity_pct=rh)


def scorer(stub, min_clean=3, budget=0.2):
    return ModelScorer(ScorerClient("http://scorer", "s3cret", 2.0, stub.transport), thresholds=ThresholdStore(budget, min_clean))


async def fill(sc, n, **kw):
    out = None
    for i in range(n):
        out = await sc.score(rd(i, t=20.0 + math.sin(i / 7.0), **kw), "OK")
    return out


def test_zscore_is_mean_zero_unit_std_and_floors_a_flat_window():
    z = zscore([1.0, 2.0, 3.0, 4.0])
    assert abs(sum(z)) < 1e-12 and abs(sum(x * x for x in z) / 4 - 1) < 1e-12
    flat = zscore([5.0] * 10)
    assert flat == [0.0] * 10                       # std floored at 1e-6, no division by zero


def test_window_resets_on_missing_or_non_finite_and_hydrates_oldest_first():
    w = WindowStore(size=4)
    for v in (1, 2, 3):
        w.push("A", "temperature", v)
    assert w.count("A", "temperature") == 3 and w.scaled("A", "temperature") is None
    assert w.push("A", "temperature", float("nan")) == 0 and w.push("A", "temperature", 1) == 1
    w.push("A", "temperature", None)
    assert w.count("A", "temperature") == 0
    w.seed("B", [{"temperature": 1.0}, {"temperature": 2.0}, {"temperature": None}, {"temperature": 3.0}, {"temperature": 4.0}])
    assert w.count("B", "temperature") == 2 and "B" in w and w.count("B", "pressure") == 0


@pytest.mark.asyncio
async def test_warm_up_says_how_many_readings_are_missing_and_no_call_is_made():
    stub = Stub()
    sc = scorer(stub)
    out = await fill(sc, 10)
    v = out["variables"]["temperature"]
    assert v["status"] == "not_run" and v["reason"] == f"not run: need {WINDOW} readings, have 10" and v["error"] is None
    assert stub.requests == []


@pytest.mark.asyncio
async def test_a_full_window_is_sent_z_scored_in_one_call_for_all_variables_with_the_secret():
    stub = Stub(error=0.25)
    sc = scorer(stub)
    out = await fill(sc, WINDOW)
    secret, body = stub.requests[0]
    assert len(stub.requests) == 1 and secret == "s3cret" and len(body["windows"]) == 3 and all(len(w) == WINDOW for w in body["windows"])
    temp = body["windows"][0]
    assert abs(sum(temp) / WINDOW) < 1e-9 and abs(sum(x * x for x in temp) / WINDOW - 1) < 1e-9
    assert body["windows"][1] == [0.0] * WINDOW                  # constant pressure: flat window scales to zeros
    v = out["variables"]["temperature"]
    assert v["status"] == "scored" and v["error"] == 0.25 and v["window"] == WINDOW and v["scaling"] == "trailing z-score (assumed)"
    assert out["model_id"] == MODEL_ID and out["revision"] == "abc123" and out["validated"] is False and out["note"] == "not validated"


def test_threshold_is_the_empirical_quantile_of_clean_errors_and_needs_the_minimum():
    t = ThresholdStore(budget=0.1, min_clean=10)
    for i in range(1, 10):
        t.add_clean("A", "temperature", float(i))
    assert t.threshold("A", "temperature") is None and t.reason("A", "temperature") == "threshold not set: need 10 clean scores, have 9"
    t.add_clean("A", "temperature", 10.0)
    assert t.threshold("A", "temperature") == 9.0                # ceil(10 * 0.9) = 9th smallest
    assert t.threshold("A", "pressure") is None and t.threshold("B", "temperature") is None
    small = ThresholdStore(0.001, 1000, max_clean=5)
    for i in range(20):
        small.add_clean("A", "x", i)
    assert small.count("A", "x") == 5                            # bounded


@pytest.mark.asyncio
async def test_flag_only_with_a_threshold_computed_from_earlier_clean_errors_only():
    stub = Stub(error=[0.1, 0.1, 0.1])
    sc = scorer(stub, min_clean=3, budget=0.2)
    await fill(sc, WINDOW - 1)
    last = None
    for i in range(WINDOW - 1, WINDOW + 3):                      # 4 full-window readings, error 0.1 each
        last = await sc.score(rd(i, t=20.0 + math.sin(i / 7.0)), "OK")
        assert last["variables"]["temperature"]["flagged"] is False
    assert sc.thresholds.count("S1", "temperature") == 4
    assert last["variables"]["temperature"]["threshold"] is not None and last["calibrated"] is True
    stub.error = 5.0                                              # a large error, but the threshold exists now
    big = await sc.score(rd(WINDOW + 4, t=20.0), "OK")
    v = big["variables"]["temperature"]
    assert v["flagged"] is True and v["threshold"] == pytest.approx(0.1)
    assert sc.thresholds.count("S1", "temperature") == 4          # a flagged error is not clean: it never raises its own threshold


@pytest.mark.asyncio
async def test_no_threshold_means_no_flag_however_large_the_error():
    stub = Stub(error=99.0)
    sc = scorer(stub, min_clean=1000)
    out = await fill(sc, WINDOW)
    v = out["variables"]["temperature"]
    assert v["status"] == "scored" and v["flagged"] is False and v["threshold"] is None and v["reason"].startswith("threshold not set: need 1000 clean scores, have")
    assert out["calibrated"] is False


@pytest.mark.asyncio
async def test_error_of_a_reading_the_checks_flagged_is_not_clean():
    stub = Stub(error=0.1)
    sc = scorer(stub)
    await fill(sc, WINDOW - 1)
    await sc.score(rd(WINDOW, t=20.0), "SUSPECT")
    assert sc.thresholds.count("S1", "temperature") == 0


@pytest.mark.asyncio
async def test_outage_reports_unavailable_backs_off_and_does_not_call_again():
    stub = Stub(status=500)
    now = [0.0]
    client = ScorerClient("http://scorer", "s", 2.0, stub.transport, clock=lambda: now[0], backoff_s=30.0)
    sc = ModelScorer(client)
    await fill(sc, WINDOW - 1)
    out = await sc.score(rd(WINDOW, t=20.0), "OK")
    v = out["variables"]["temperature"]
    assert v["status"] == "unavailable" and v["reason"] == "scorer not available: HTTP 500" and v["error"] is None and v["flagged"] is False
    n = len(stub.requests)
    out2 = await sc.score(rd(WINDOW + 1, t=20.0), "OK")
    assert len(stub.requests) == n and "backing off" in out2["variables"]["temperature"]["reason"]
    stub.status = 200
    now[0] = 31.0
    out3 = await sc.score(rd(WINDOW + 2, t=20.0), "OK")
    assert out3["variables"]["temperature"]["status"] == "scored"


@pytest.mark.asyncio
async def test_timeout_and_malformed_answers_are_unavailable_not_invented():
    def boom(req):
        raise httpx.ConnectTimeout("slow")
    c = ScorerClient("http://scorer", "s", 0.1, httpx.MockTransport(boom))
    with pytest.raises(ScorerUnavailable):
        await c.score([[0.0] * WINDOW])
    bad = ScorerClient("http://scorer", "s", 0.1, httpx.MockTransport(lambda r: httpx.Response(200, json={"errors": [1.0, 2.0]})))
    with pytest.raises(ScorerUnavailable, match="malformed"):
        await bad.score([[0.0] * WINDOW])


@pytest.mark.asyncio
async def test_absent_scorer_returns_no_provider(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "SCORER_URL", "")
    sc = ModelScorer.from_settings()
    assert sc.enabled is False and await sc.score(rd(0), "OK") is None


@pytest.mark.asyncio
async def test_missing_value_resets_only_that_variable_and_says_so():
    stub = Stub()
    sc = scorer(stub)
    await fill(sc, WINDOW - 1)
    out = await sc.score(StreamReading("S1", T0 + timedelta(days=1), "fake", temperature_c=None, pressure_hpa=1000.0, humidity_pct=50.0), "OK")
    assert out["variables"]["temperature"]["status"] == "not_run" and "window reset" in out["variables"]["temperature"]["reason"]
    assert out["variables"]["pressure"]["status"] == "scored"


@pytest.mark.asyncio
async def test_stored_block_is_compact_and_expands_to_the_provider_shape():
    stub = Stub(error=0.3)
    out = await fill(scorer(stub), WINDOW)
    c = compact(out)
    assert set(c["variables"]["temperature"]) <= {"status", "error", "threshold", "flagged", "reason"} and "window" not in c["variables"]["temperature"]
    e = expand(c)
    assert e["validated"] is False and e["variables"]["temperature"]["scaling"] == "trailing z-score (assumed)" and e["variables"]["temperature"]["error"] == 0.3
    assert set(out) == {"model_id", "revision", "calibrated", "validated", "note", "variables"} and set(out["variables"]) == {"temperature", "pressure", "humidity"}
    assert set(out["variables"]["temperature"]) == {"status", "error", "threshold", "flagged", "reason", "window", "scaling"}
