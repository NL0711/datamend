"""Intake (validation/intake.py): the input contract and the choice of fetcher for a link. Fetchers are replaced; no network."""
import httpx
import pytest

from backend.app.validation import intake, kaggle_import, s3_import


def test_the_file_type_comes_from_the_extension_and_is_checked_before_anything_is_stored():
    o = intake.upload_options("rain.CSV", "reading", accumulation_mode="cumulative", timezone="Asia/Kolkata", interval_minutes=15)
    assert (o.fmt, o.profile, o.accumulation_mode, o.timezone, o.interval_minutes) == ("csv", "reading", "cumulative", "Asia/Kolkata", 15)
    assert intake.upload_options("a.json", "daily").fmt == "json"
    for bad in ("data.parquet", "noextension", "x."):
        with pytest.raises(intake.UnsupportedFile) as ei:
            intake.upload_options(bad, "daily")
        assert "use .csv or .json" in str(ei.value)


def test_blank_options_become_none():
    o = intake.upload_options("a.csv", "daily", accumulation_mode="", timezone="")
    assert o.accumulation_mode is None and o.timezone is None


@pytest.mark.asyncio
async def test_an_s3_link_goes_to_the_anonymous_fetcher_and_never_passes_a_token(monkeypatch):
    seen = {}

    async def s3_fetch(url, file=None):
        seen["s3"] = (url, file)
        return "r.csv", b"x"

    async def kaggle_fetch(*a, **k):
        raise AssertionError("a public S3 link must not reach the Kaggle fetcher")
    monkeypatch.setattr(s3_import, "fetch", s3_fetch)
    monkeypatch.setattr(kaggle_import, "fetch", kaggle_fetch)
    assert await intake.fetch_link("s3://bucket/key.csv", token="SECRET", file="f.csv") == ("r.csv", b"x")
    assert seen["s3"] == ("s3://bucket/key.csv", "f.csv")


@pytest.mark.asyncio
async def test_any_other_link_goes_to_kaggle_with_the_token(monkeypatch):
    seen = {}

    async def kaggle_fetch(url, token=None, file=None):
        seen["k"] = (url, token, file)
        return "k.csv", b"y"
    monkeypatch.setattr(kaggle_import, "fetch", kaggle_fetch)
    assert await intake.fetch_link("https://www.kaggle.com/datasets/a/b", token="T") == ("k.csv", b"y")
    assert seen["k"] == ("https://www.kaggle.com/datasets/a/b", "T", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("raised,expected", [
    (kaggle_import.NeedsToken("private"), intake.LinkNeedsToken),
    (kaggle_import.KaggleError("no file"), intake.LinkRejected),
    (s3_import.S3Error("not public"), intake.LinkRejected),
    (httpx.ConnectError("down"), intake.LinkUnreachable),
])
async def test_fetcher_problems_become_typed_intake_errors(monkeypatch, raised, expected):
    async def boom(*a, **k):
        raise raised
    monkeypatch.setattr(kaggle_import, "fetch", boom)
    monkeypatch.setattr(s3_import, "fetch", boom)
    for url in ("https://www.kaggle.com/datasets/a/b", "s3://b/k"):
        if isinstance(raised, kaggle_import.NeedsToken) and url.startswith("s3"):
            continue                                   # an S3 fetcher never asks for a token
        with pytest.raises(expected):
            await intake.fetch_link(url)
