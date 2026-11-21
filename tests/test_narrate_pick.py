"""Explainer choice and narrator-problem mapping (narrate.pick_explainer, api/validation._narrator_http). No narrator is contacted."""
import pytest
from fastapi import HTTPException

from backend.app.api.validation import _narrator_http
from backend.app.validation import narrate
from backend.app.validation.explain import NarratorExplainer, NarratorRateLimited, NarratorUnavailable


def test_the_baseline_is_always_available():
    assert narrate.pick_explainer("baseline", None) is narrate.BASELINE
    assert narrate.pick_explainer("anything-else", None) is narrate.BASELINE


def test_the_narrator_is_used_only_when_configured():
    n = NarratorExplainer("https://narrator.example.com", "", 5)
    assert narrate.pick_explainer("narrator", n) is n
    with pytest.raises(narrate.NarratorNotConnected) as ei:
        narrate.pick_explainer("narrator", None)
    assert str(ei.value) == "AI narrator not connected"


@pytest.mark.parametrize("error,code", [
    (narrate.NarratorNotConnected("AI narrator not connected"), 503),
    (NarratorRateLimited("slow down"), 429),
    (narrate.NothingToExplain("no fired check"), 404),
    (NarratorUnavailable("narrator timed out"), 502),
])
def test_each_narrator_problem_has_one_http_answer(error, code):
    e = _narrator_http(error)
    assert isinstance(e, HTTPException) and e.status_code == code and e.detail == str(error)
