"""The interim Gemini layer on a MOCKED transport. No real call is made and no real key is used (the key below is a made-up string)."""
import json

import httpx
import pytest

from backend.app.validation import narrate
from backend.app.validation.explain import NarratorRateLimited, NarratorUnavailable
from backend.app.validation.gemini import GeminiExplainer, _DayBudget, _Minute, invented_numbers

KEY = "test-key-not-real-0000"
EVIDENCE = {"check": "repeated_value", "observed": {"value": 12.5, "unit": "mm", "basis": "measured"}, "threshold": {"value": 3, "why": "design choice"},
            "row": {"row_ref": "r1", "station_id": "A", "rule_score": 0.8}, "reason": "same positive total on consecutive days"}


def reply(obj, status=200, finish="STOP"):
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps(obj) if not isinstance(obj, str) else obj}]}, "finishReason": finish}]}
    return httpx.Response(status, json=body)


def make(handler, **kw):
    seen = []

    def wrapped(req: httpx.Request):
        seen.append(req)
        return handler(req)
    lim = (_Minute(100), _DayBudget(1000))
    ex = GeminiExplainer(KEY, transport=httpx.MockTransport(wrapped), limits=lim, **kw)
    ex.retry_wait = 0
    return ex, seen


@pytest.mark.asyncio
async def test_503_is_retried_once_then_reported():
    calls = []

    def flaky(r):
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else reply({"text": "Seen 12.5 mm."})
    ex, _ = make(flaky)
    assert (await ex.explain(EVIDENCE)).text and len(calls) == 2
    ex2, seen = make(lambda r: httpx.Response(503))
    with pytest.raises(NarratorUnavailable) as e:
        await ex2.explain(EVIDENCE)
    assert "high demand" in str(e.value) and len(seen) == 2


@pytest.mark.asyncio
async def test_unknown_model_says_so():
    ex, _ = make(lambda r: httpx.Response(404))
    with pytest.raises(NarratorUnavailable) as e:
        await ex.explain(EVIDENCE)
    assert "GEMINI_MODEL" in str(e.value)


@pytest.mark.asyncio
async def test_explain_ok_sends_key_in_header_not_url_and_only_the_evidence():
    ex, seen = make(lambda r: reply({"text": "The check saw 12.5 mm on consecutive days.", "contributions": [{"check": "repeated_value", "note": "same total"}]}))
    out = await ex.explain(EVIDENCE)
    assert out.generated and out.generator == "gemini" and out.model_id.startswith("gemini:") and out.confidence is None
    req = seen[0]
    assert req.headers["x-goog-api-key"] == KEY and KEY not in str(req.url)
    body = json.loads(req.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "repeated_value" in body["contents"][0]["parts"][0]["text"] and KEY not in req.content.decode()


@pytest.mark.asyncio
@pytest.mark.parametrize("handler,needle", [
    (lambda r: httpx.Response(429), "quota"),
    (lambda r: httpx.Response(403), "refused"),
    (lambda r: httpx.Response(500), "HTTP 500"),
    (lambda r: reply("not json at all"), "JSON shape"),
    (lambda r: reply({"text": "ok"}, finish="SAFETY"), "did not finish"),
    (lambda r: httpx.Response(200, json={"candidates": []}), "no answer"),
    (lambda r: reply({"text": ""}), "usable"),
    (lambda r: reply({"text": "x" * 5000}), "usable"),
])
async def test_explain_failures_raise_plain_errors_and_never_leak_the_key(handler, needle):
    ex, _ = make(handler)
    with pytest.raises(NarratorUnavailable) as e:
        await ex.explain(EVIDENCE)
    assert needle in str(e.value) and KEY not in str(e.value)


@pytest.mark.asyncio
async def test_429_is_a_rate_limit_error():
    ex, _ = make(lambda r: httpx.Response(429))
    with pytest.raises(NarratorRateLimited):
        await ex.explain(EVIDENCE)


@pytest.mark.asyncio
async def test_timeout_is_reported_without_the_key():
    def boom(r):
        raise httpx.ConnectTimeout("slow")
    ex, _ = make(boom)
    with pytest.raises(NarratorUnavailable) as e:
        await ex.explain(EVIDENCE)
    assert "ConnectTimeout" in str(e.value) and KEY not in str(e.value)


@pytest.mark.asyncio
async def test_invented_number_is_refused():
    ex, _ = make(lambda r: reply({"text": "The gauge read 999.9 mm."}))
    with pytest.raises(NarratorUnavailable) as e:
        await ex.explain(EVIDENCE)
    assert "999.9" in str(e.value)


def test_invented_numbers_allows_small_counts_and_numbers_from_the_evidence():
    assert invented_numbers("Two days, 12.5 mm and a threshold of 3; 5 stations", EVIDENCE) == []
    assert invented_numbers("It was 42.1 mm", EVIDENCE) == ["42.1"]


@pytest.mark.asyncio
async def test_oversize_request_is_refused_before_any_call():
    ex, seen = make(lambda r: reply({"text": "ok"}))
    big = dict(EVIDENCE, window=["x" * 100] * 1000)
    with pytest.raises(NarratorUnavailable):
        await ex.explain(big)
    assert seen == []


@pytest.mark.asyncio
async def test_minute_limit_and_daily_budget():
    ex = GeminiExplainer(KEY, transport=httpx.MockTransport(lambda r: reply({"text": "ok"})), limits=(_Minute(1), _DayBudget(1000)))
    await ex.explain(EVIDENCE)
    with pytest.raises(NarratorRateLimited):
        await ex.explain(EVIDENCE)
    ex2 = GeminiExplainer(KEY, transport=httpx.MockTransport(lambda r: reply({"text": "ok"})), limits=(_Minute(100), _DayBudget(1)))
    await ex2.explain(EVIDENCE)
    with pytest.raises(NarratorRateLimited):
        await ex2.explain(EVIDENCE)


@pytest.mark.asyncio
async def test_chat_needs_no_evidence_but_explain_does():
    ex, _ = make(lambda r: reply({"text": "The run flagged some rows."}))
    out = await ex.explain(None, question="what happened?", kind="chat", context={"run_headline": {"flagged": 3}})
    assert out.text
    with pytest.raises(NarratorUnavailable):
        await ex.explain(None)


@pytest.mark.asyncio
async def test_propose_label_validates_label_and_reason():
    ex, _ = make(lambda r: reply({"label": "genuine_extreme", "reason": "Neighbours also wet; 12.5 mm is plausible."}))
    assert (await ex.propose_label([EVIDENCE]))["label"] == "genuine_extreme"
    bad, _ = make(lambda r: reply({"label": "delete_everything", "reason": "x"}))
    with pytest.raises(NarratorUnavailable):
        await bad.propose_label([EVIDENCE])
    inv, _ = make(lambda r: reply({"label": "confirmed_fault", "reason": "It read 777.7 mm."}))
    with pytest.raises(NarratorUnavailable):
        await inv.propose_label([EVIDENCE])
    with pytest.raises(NarratorUnavailable):
        await ex.propose_label([])


def test_constructor_rejects_bad_settings():
    for kw in ({"api_key": ""}, {"api_key": KEY, "model": "../evil"}, {"api_key": KEY, "base_url": "http://insecure"}):
        with pytest.raises(ValueError):
            GeminiExplainer(**kw)


def test_get_narrator_precedence_and_status_never_shows_the_key(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "NARRATOR_URL", "")
    assert narrate.get_narrator() is None
    assert narrate.narrator_status(None)["connected"] is False
    monkeypatch.setattr(settings, "GEMINI_API_KEY", KEY)
    g = narrate.get_narrator()
    st = narrate.narrator_status(g)
    assert st["connected"] and st["provider"] == "gemini" and KEY not in json.dumps(st)
    monkeypatch.setattr(settings, "NARRATOR_URL", "https://narrator.example.org/explain")
    assert narrate.narrator_status(narrate.get_narrator())["provider"] == "mcp-narrator"
