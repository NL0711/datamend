"""Kaggle import: link parsing, file choice, the public path (no token), the private path (needs a token). A mocked transport; no network."""
import httpx
import pytest

from backend.app.validation import kaggle_import as k

CSV = b"timestamp,station_id,accumulation\n2026-07-01T00:00:00Z,A,0\n"


def transport(files, private=False, wrap=False, seen=None):
    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append((req.url.path, req.headers.get("authorization")))
        if req.url.host == "storage.example":
            return httpx.Response(200, content=CSV)                  # the signed link needs no token
        if private and req.headers.get("authorization") != "Bearer good":
            return httpx.Response(403, json={"code": 403})
        if req.url.path.endswith("/list/o/n"):
            return httpx.Response(200, json={"datasetFiles": [{"name": n, "totalBytes": s} for n, s in files]})
        if "/download/o/n" in req.url.path:
            return httpx.Response(302, headers={"location": "https://storage.example/file"})
        return httpx.Response(200, content=CSV)
    return httpx.MockTransport(handler)


def test_parse_ref_accepts_links_and_refs():
    assert k.parse_ref("https://www.kaggle.com/datasets/nathashalewis/majorproj-rainfall") == "nathashalewis/majorproj-rainfall"
    assert k.parse_ref("kaggle.com/datasets/o/n/data?select=a.csv") == "o/n"
    assert k.parse_ref("o/n") == "o/n"
    for bad in ("", "hello", "https://example.com/x/y/z", "a/b/c"):
        with pytest.raises(k.KaggleError):
            k.parse_ref(bad)


@pytest.mark.asyncio
async def test_public_dataset_needs_no_token():
    seen = []
    name, content = await k.fetch("o/n", transport=transport([("rain.csv", 50)], seen=seen))
    assert (name, content) == ("rain.csv", CSV)
    assert all(auth is None for _, auth in seen)


@pytest.mark.asyncio
async def test_private_dataset_asks_for_a_token_then_accepts_it():
    t = transport([("rain.csv", 50)], private=True)
    with pytest.raises(k.NeedsToken):
        await k.fetch("o/n", transport=t)
    assert (await k.fetch("o/n", token="good", transport=t))[1] == CSV
    with pytest.raises(k.KaggleError) as e:
        await k.fetch("o/n", token="wrong", transport=t)
    assert not isinstance(e.value, k.NeedsToken)


@pytest.mark.asyncio
async def test_no_usable_file_and_oversize_and_ambiguity_are_plain_errors():
    with pytest.raises(k.KaggleError, match="no CSV or JSON"):
        await k.fetch("o/n", transport=transport([("a.nc", 50_000_000)]))
    with pytest.raises(k.KaggleError, match="limit"):
        await k.fetch("o/n", transport=transport([("big.csv", 50_000_000)]))
    with pytest.raises(k.KaggleError, match="several files"):
        await k.fetch("o/n", transport=transport([("a.csv", 5), ("b.csv", 5)]))
    assert (await k.fetch("o/n", filename="b.csv", transport=transport([("a.csv", 5), ("b.csv", 5)])))[0] == "b.csv"


@pytest.mark.asyncio
async def test_token_is_not_in_the_error_text():
    with pytest.raises(k.KaggleError) as e:
        await k.fetch("o/n", token="SECRET123", transport=transport([("rain.csv", 50)], private=True))
    assert "SECRET123" not in str(e.value)


def test_s3_link_forms_and_rejections():
    from backend.app.validation import s3_import as s
    assert s.parse("s3://example-bucket/data/a.csv") == ("example-bucket", "data/a.csv")
    assert s.parse("https://my-bkt.s3.amazonaws.com/x/y.csv") == ("my-bkt", "x/y.csv")
    assert s.parse("https://my-bkt.s3.ap-south-1.amazonaws.com/x/") == ("my-bkt", "x/")
    assert s.parse("https://s3.us-west-2.amazonaws.com/my-bkt/x.json") == ("my-bkt", "x.json")
    for bad in ("https://evil.example.com/a.csv", "s3://", "s3://A_B/x.csv", "https://x.amazonaws.com.evil.com/a"):
        with pytest.raises(s.S3Error):
            s.parse(bad)


@pytest.mark.asyncio
async def test_s3_public_file_folder_and_private():
    from backend.app.validation import s3_import as s
    listing = (b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Contents><Key>d/</Key><Size>0</Size></Contents>'
               b'<Contents><Key>d/rain.csv</Key><Size>50</Size></Contents><Contents><Key>d/map.nc</Key><Size>99</Size></Contents></ListBucketResult>')

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host.startswith("priv."):
            return httpx.Response(403)
        if req.url.params.get("list-type"):
            return httpx.Response(200, content=listing)
        return httpx.Response(200, content=CSV)
    t = httpx.MockTransport(handler)
    assert await s.fetch("s3://bkt/d/rain.csv", transport=t) == ("rain.csv", CSV)
    assert await s.fetch("s3://bkt/d/", transport=t) == ("rain.csv", CSV)             # the folder holds one usable file
    with pytest.raises(s.S3Error, match="not public"):
        await s.fetch("s3://priv.bkt/d/rain.csv", transport=t)
    with pytest.raises(s.S3Error, match="CSV or JSON"):
        await s.fetch("s3://bkt/d/map.nc", transport=t)


@pytest.mark.asyncio
async def test_route_reports_needs_token_as_401(client=None):
    from httpx import ASGITransport, AsyncClient
    from backend.app.main import app
    orig = k.fetch

    async def fake(url, token=None, filename=None, transport=None):
        raise k.NeedsToken("private")
    k.fetch = fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/validation/runs/kaggle", json={"url": "o/n"})
    finally:
        k.fetch = orig
    assert r.status_code == 401 and r.json()["detail"]["needs_token"] is True
