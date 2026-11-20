"""The Import step: S3 and Kaggle links, the safety rules, format detection and the ISD adapter. No network and no real data: S3 is a fake client or a
mock transport, the Kaggle command line is a fake, ISD lines are GENERATED in the documented layout, credentials are obviously fake values."""
import gzip
import io
import json
import zipfile
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.pipeline import cwc, importers, isd
from backend.app.pipeline import jobs as jobs_svc
from backend.app.pipeline.models import IngestJob, Observation, PipelineStation

TOKEN = "i" * 32
H = {"X-Admin-Token": TOKEN}
AWS_KEY, AWS_SECRET, AWS_TOKEN = "FAKEACCESSKEYID0001", "fake-secret-not-real-0001", "fake-session-token-0001"
KG_TOKEN = "KGAT_faketoken0000000000000000000001"          # obviously fake
DELHI = "421820-99999"
PUBLIC = "52.0.0.1"
HEADER = ("SlNo,Station,Agency,State LGD Code,State,District LGD Code,District,Tehsil,Block,Village,River,Basin,Tributary,Subtributary,"
          "SubSubtributary,Local River,Latitude,Longitude,Data Acquisition Time,Telemetry Hourly Rainfall (mm)")


def cwc_csv(station="Amarpur", days=4) -> bytes:
    rows = [f"{i},{station},CWC,16,Tripura,654,Gomati,T,-,-,R,B,T,S,-,L,23.5,91.6,{i:02d}-06-2026 14:00,{4 + i * 0.7:.1f}" for i in range(1, days + 1)]
    return (HEADER + "\n" + "\n".join(rows) + "\n").encode()


def isd_line(sid: str, stamp: str, groups=(("01", "0000", "9", "1"),), lat="+28584", lon="+077200") -> str:
    usaf, wban = sid.split("-")
    head = f"0200{usaf}{wban}{stamp[:8]}{stamp[8:12]}4{lat}{lon}FM-12+0216VIDP ".ljust(105)
    return head + "ADD" + "".join(f"AA{i}{p}{d}{c}{q}" for i, (p, d, c, q) in enumerate(groups, start=1)) + "REM"


def isd_gz(lines) -> bytes:
    return gzip.compress(("\n".join(lines) + "\n").encode())


@pytest_asyncio.fixture(autouse=True)
async def _env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "KAGGLE_USERNAME", "")
    monkeypatch.setattr(settings, "KAGGLE_KEY", "")
    monkeypatch.setattr(settings, "KAGGLE_API_TOKEN", "")
    monkeypatch.setattr(jobs_svc, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(importers, "resolve_addresses", lambda host: [PUBLIC])
    from backend.app.api import settings as settings_api
    settings_api._failures.clear()
    async with async_session_factory() as s:
        for m in (Observation, PipelineStation, IngestJob):
            await s.execute(delete(m))
        await s.commit()
    yield


def no_temp_left(tmp_path) -> bool:
    d = tmp_path / "uploads"
    return not d.exists() or not list(d.iterdir())


class FakeBody:
    def __init__(self, data: bytes):
        self.b = io.BytesIO(data)

    def read(self, n):
        return self.b.read(n)


class FakeS3:
    def __init__(self, objects, seen):
        self.objects, self.seen = objects, seen

    def head_object(self, Bucket, Key):
        return {"ContentLength": len(self._get(Bucket, Key))}

    def get_object(self, Bucket, Key):
        return {"Body": FakeBody(self._get(Bucket, Key))}

    def _get(self, b, k):
        if (b, k) not in self.objects:
            err = Exception("boom")
            err.response = {"Error": {"Code": "NoSuchKey"}}
            raise err
        return self.objects[(b, k)]


@pytest.fixture
def fake_s3(monkeypatch):
    seen = {"calls": []}
    objects = {}

    def factory(req, region):
        seen["calls"].append((req, region))
        return FakeS3(objects, seen)
    monkeypatch.setattr(importers, "make_s3_client", factory)
    seen["objects"] = objects
    return seen


async def post_import(c: AsyncClient, provider, url, fmt="auto", headers=None):
    return await c.post("/api/pipeline/import", headers={**H, **(headers or {})}, json={"provider": provider, "url": url, "format": fmt})


async def get_job(c: AsyncClient, jid):
    return (await c.get(f"/api/pipeline/jobs/{jid}")).json()


# ---------------------------------------------------------------------------------------------- sources
@pytest.mark.asyncio
async def test_sources_lists_providers_formats_and_limits(async_client: AsyncClient):
    body = (await async_client.get("/api/pipeline/import/sources")).json()
    assert [p["id"] for p in body["providers"]] == ["aws", "kaggle"]
    aws = body["providers"][0]
    assert aws["label"] == "Amazon S3 (AWS)" and "s3://bucket/key" in aws["accepts"] and aws["credentials"].startswith("optional")
    assert body["providers"][1]["accepts"] == ["owner/dataset-slug", "a kaggle.com dataset link", "kernel:owner/notebook-slug (output)"]
    assert body["providers"][1]["credentials"].startswith("none for public datasets")
    assert [f["id"] for f in body["formats"]] == ["auto", "cwc", "isd"] and body["limits"]["max_mb"] == 300


@pytest.mark.asyncio
async def test_import_needs_the_admin_session(async_client: AsyncClient):
    r = await async_client.post("/api/pipeline/import", json={"provider": "aws", "url": "s3://bucket-one/a.csv", "format": "auto"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------------------------- aws, boto3 path
@pytest.mark.asyncio
async def test_public_s3_link_is_fetched_anonymously_and_ingested_as_cwc(async_client: AsyncClient, fake_s3, tmp_path):
    fake_s3["objects"][("bucket-one", "rain/tr.csv")] = cwc_csv()
    r = await post_import(async_client, "aws", "s3://bucket-one/rain/tr.csv")
    assert r.status_code == 202, r.text
    j = r.json()
    assert fake_s3["calls"] == [(None, "us-east-1")]                           # no credentials sent: anonymous
    assert (j["provider"], j["origin"], j["source"], j["filename"]) == ("aws", "s3://bucket-one/rain/tr.csv", "cwc", "tr.csv")
    assert j["job_ids"] == [j["id"]] and j["skipped_files"] == []
    for key in ("id", "created_at", "sha256", "size_bytes", "status", "rows_read", "assumptions", "error", "run_id"):
        assert key in j
    assert j["assumptions"]["format"] == "cwc" and j["assumptions"]["omits_zero_values"] is True
    assert j["assumptions"]["format_detection"] == "sniffed from the file content"
    done = await get_job(async_client, j["id"])
    assert done["status"] == "done" and done["rows_inserted"] == 4 and done["rows_bad"] == 0
    assert no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_private_bucket_uses_the_callers_credentials_and_they_never_leak(async_client: AsyncClient, fake_s3, caplog):
    caplog.set_level("DEBUG")
    fake_s3["objects"][("bucket-one", "tr.csv")] = cwc_csv()
    hdr = {"X-Aws-Access-Key-Id": AWS_KEY, "X-Aws-Secret-Access-Key": AWS_SECRET, "X-Aws-Session-Token": AWS_TOKEN, "X-Aws-Region": "eu-west-1"}
    r = await post_import(async_client, "aws", "https://bucket-one.s3.ap-south-1.amazonaws.com/tr.csv?note=1", headers=hdr)
    assert r.status_code == 202, r.text
    req, region = fake_s3["calls"][0]
    assert (req.key_id, region) == (AWS_KEY, "eu-west-1")                      # the header region wins over the link's
    async with async_session_factory() as s:
        rows = [jobs_svc.job_dict(j) for j in (await s.execute(select(IngestJob))).scalars()]
    blob = r.text + json.dumps(rows, default=str) + json.dumps((await async_client.get("/api/pipeline/jobs")).json()) + caplog.text
    for secret in (AWS_KEY, AWS_SECRET, AWS_TOKEN, "note=1"):
        assert secret not in blob
    assert r.json()["origin"] == "bucket-one.s3.ap-south-1.amazonaws.com/tr.csv"


@pytest.mark.asyncio
async def test_malformed_credential_headers_are_refused_without_echo(async_client: AsyncClient, fake_s3):
    r = await post_import(async_client, "aws", "s3://bucket-one/a.csv", headers={"X-Aws-Access-Key-Id": AWS_KEY})
    assert r.status_code == 400 and AWS_KEY not in r.text
    r = await post_import(async_client, "kaggle", "own/set", headers={"X-Kaggle-Token": "bad token with spaces!"})
    assert r.status_code == 400 and "bad token" not in r.text


@pytest.mark.asyncio
async def test_missing_object_and_access_denied_give_safe_messages(async_client: AsyncClient, fake_s3, monkeypatch):
    r = await post_import(async_client, "aws", "s3://bucket-one/none.csv")
    assert r.status_code == 404 and "not found" in r.json()["detail"]

    class Denied(FakeS3):
        def head_object(self, Bucket, Key):
            e = Exception(f"secret detail {AWS_SECRET}")
            e.response = {"Error": {"Code": "AccessDenied"}}
            raise e
    monkeypatch.setattr(importers, "make_s3_client", lambda req, region: Denied({}, {}))
    r = await post_import(async_client, "aws", "s3://bucket-one/x.csv")
    assert r.status_code == 403 and AWS_SECRET not in r.text and "credentials" in r.json()["detail"]


# ---------------------------------------------------------------------------------------------- aws, link parsing and SSRF
@pytest.mark.parametrize("url,bucket,key,region", [
    ("s3://bucket-one/a/b.csv", "bucket-one", "a/b.csv", None),
    ("https://bucket-one.s3.eu-west-1.amazonaws.com/a/b.csv", "bucket-one", "a/b.csv", "eu-west-1"),
    ("https://s3.eu-west-1.amazonaws.com/bucket-one/a/b.csv", "bucket-one", "a/b.csv", "eu-west-1"),
    ("https://bucket-one.s3.amazonaws.com/a/b.csv", "bucket-one", "a/b.csv", None),
])
def test_accepted_link_forms(url, bucket, key, region):
    link = importers.parse_aws_link(url)
    assert (link.bucket, link.key, link.region, link.presigned) == (bucket, key, region, None)


def test_a_presigned_link_is_marked_and_its_origin_has_no_query():
    url = "https://bucket-one.s3.eu-west-1.amazonaws.com/a.csv?X-Amz-Signature=fakesig&X-Amz-Credential=fakecred"
    link = importers.parse_aws_link(url)
    assert link.presigned == url and "fakesig" not in link.origin and "?" not in link.origin


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "https://evil.example.com/bucket/key.csv",
    "http://bucket-one.s3.amazonaws.com/key.csv",                     # not https
    "https://bucket-one.s3.amazonaws.com.evil.example.com/key.csv",   # suffix trick
    "https://169.254.169.254/latest/meta-data/",
    "https://user:pw@bucket-one.s3.amazonaws.com/key.csv",
    "https://bucket-one.s3.amazonaws.com:8443/key.csv",
    "https://ec2.amazonaws.com/key.csv",                              # an amazonaws host that is not S3
    "file:///etc/passwd",
    "s3://bucket-one",
    "not a link",
    "",
])
async def test_bad_links_get_400_and_are_never_echoed(async_client: AsyncClient, fake_s3, url):
    r = await post_import(async_client, "aws", url)
    assert r.status_code == 400
    assert "Amazon S3" in r.json()["detail"]
    if url:
        assert url not in r.text
    assert fake_s3["calls"] == []


def link(extra=""):
    return "https://bucket-one.s3.eu-west-1.amazonaws.com/a.csv?X-Amz-Signature=fakesig" + extra


@pytest.mark.asyncio
@pytest.mark.parametrize("addr", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1", "::1", "fe80::1", "fd00::1", "::ffff:127.0.0.1", "0.0.0.0"])
async def test_a_host_that_resolves_to_a_non_public_address_is_refused(async_client: AsyncClient, monkeypatch, addr, tmp_path):
    monkeypatch.setattr(importers, "resolve_addresses", lambda host: [PUBLIC, addr])           # ONE bad address among good ones is enough
    hits = []
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(lambda req: hits.append(1) or httpx.Response(200, content=b"x")))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 400 and "non-public" in r.json()["detail"] and "fakesig" not in r.text
    assert hits == [] and no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_a_redirect_to_another_host_is_refused_and_never_followed(async_client: AsyncClient, monkeypatch, tmp_path):
    seen = []

    def handler(req: httpx.Request):
        seen.append(req.url.host)
        return httpx.Response(302, headers={"location": "https://evil.example.com/steal"})
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 400 and "leaves Amazon S3" in r.json()["detail"] and "evil" not in r.text
    assert seen == ["bucket-one.s3.eu-west-1.amazonaws.com"] and no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_a_redirect_that_resolves_to_a_private_address_is_refused(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(importers, "resolve_addresses", lambda host: ["10.1.1.1"] if host.startswith("inner") else [PUBLIC])
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(
        lambda req: httpx.Response(307, headers={"location": "https://inner.s3.amazonaws.com/a.csv"})))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 400 and "non-public" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_redirect_inside_s3_is_followed(async_client: AsyncClient, monkeypatch):
    def handler(req: httpx.Request):
        if req.url.host.startswith("bucket-one"):
            return httpx.Response(307, headers={"location": "https://other-bucket.s3.eu-west-1.amazonaws.com/a.csv?X-Amz-Signature=fakesig2"})
        return httpx.Response(200, content=cwc_csv())
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 202 and "fakesig" not in r.text


@pytest.mark.asyncio
async def test_too_many_redirects_stop(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(
        lambda req: httpx.Response(302, headers={"location": "https://bucket-one.s3.eu-west-1.amazonaws.com/a.csv?X-Amz-Signature=x"})))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 502 and "redirects" in r.json()["detail"]


@pytest.mark.asyncio
async def test_oversize_is_refused_by_content_length_and_by_the_streaming_cap(async_client: AsyncClient, monkeypatch, tmp_path):
    monkeypatch.setattr(importers, "MAX_BYTES", 100)
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * 500)))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 413 and "larger than" in r.json()["detail"]
    class Chunks(httpx.AsyncByteStream):                                     # no Content-Length: the cap must stop the stream
        async def __aiter__(self):
            yield b"x" * 60
            yield b"x" * 60
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, stream=Chunks())))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 413 and no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_oversize_object_in_s3_is_refused_before_download(async_client: AsyncClient, fake_s3, monkeypatch, tmp_path):
    monkeypatch.setattr(importers, "MAX_BYTES", 100)
    fake_s3["objects"][("bucket-one", "big.csv")] = b"x" * 500
    r = await post_import(async_client, "aws", "s3://bucket-one/big.csv")
    assert r.status_code == 413 and no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_http_errors_say_the_status_only(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(403, content=b"<Error>SignatureDoesNotMatch fakesig</Error>")))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 502 and "HTTP 403" in r.json()["detail"] and "fakesig" not in r.text


@pytest.mark.asyncio
async def test_a_presigned_url_never_reaches_the_logs(async_client: AsyncClient, monkeypatch, caplog):
    caplog.set_level("DEBUG")                                              # httpx logs every request URL at INFO unless silenced
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, content=cwc_csv())))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 202 and "fakesig" not in caplog.text and "X-Amz" not in caplog.text


@pytest.mark.asyncio
async def test_presigned_isd_gz_is_detected_ingested_and_labelled(async_client: AsyncClient, monkeypatch, tmp_path):
    lines = [isd_line(DELHI, f"2025070{d}0300", (("24", f"{d * 10:04d}", "3", "1"),)) for d in range(1, 4)]
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, content=isd_gz(lines))))
    r = await post_import(async_client, "aws", "https://noaa-isd-example.s3.amazonaws.com/data/2025/421820-99999-2025.gz?X-Amz-Signature=fakesig")
    assert r.status_code == 202, r.text
    j = r.json()
    assert j["source"] == "isd" and j["assumptions"]["format"] == "isd" and j["assumptions"]["omits_zero_values"] is False
    assert "overlap_rule" in j["assumptions"] and "Resolution 40" in j["assumptions"]["licence"] and j["filename"] == "421820-99999-2025.gz"
    done = await get_job(async_client, j["id"])
    assert done["status"] == "done" and done["rows_inserted"] == 3 and done["stations"] == 1
    async with async_session_factory() as s:
        st = (await s.execute(select(PipelineStation))).scalars().one()
        obs = (await s.execute(select(Observation).order_by(Observation.observed_at))).scalars().all()
    assert st.station_key == f"isd:{DELHI}" and st.name == "Safdarjung" and (st.latitude, st.longitude) == (28.584, 77.2)
    assert [o.value_mm for o in obs] == [1.0, 2.0, 3.0] and obs[0].source == "isd"
    assert no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_a_gzipped_cwc_csv_is_unpacked_and_an_unknown_file_is_refused(async_client: AsyncClient, monkeypatch, tmp_path):
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, content=gzip.compress(cwc_csv()))))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 202 and r.json()["source"] == "cwc" and r.json()["filename"] == "a.csv"
    assert (await get_job(async_client, r.json()["id"]))["rows_inserted"] == 4
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, content=b"hello,world\n1,2\n")))
    r = await post_import(async_client, "aws", link())
    assert r.status_code == 422 and "not a recognised format" in r.json()["detail"] and no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_a_given_format_that_does_not_match_fails_the_job_not_the_server(async_client: AsyncClient, fake_s3):
    fake_s3["objects"][("bucket-one", "tr.csv")] = cwc_csv()
    r = await post_import(async_client, "aws", "s3://bucket-one/tr.csv", fmt="isd")
    assert r.status_code == 202 and r.json()["source"] == "isd" and r.json()["assumptions"]["format_detection"] == "given by the caller"
    j = await get_job(async_client, r.json()["id"])
    assert j["status"] == "failed" and "not an NOAA ISD file" in j["error"]


def test_sniff_by_content(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(cwc_csv())
    assert importers.sniff(str(p)) == "cwc"
    p.write_bytes(isd_gz([isd_line(DELHI, "202507010300")]))
    assert importers.sniff(str(p)) == "isd"
    p.write_bytes(("\n".join([isd_line(DELHI, "202507010300")])).encode())
    assert importers.sniff(str(p)) == "isd"
    p.write_bytes(b"\x1f\x8bnot really gzip")
    with pytest.raises(importers.ImportRefused):
        importers.sniff(str(p))


# ---------------------------------------------------------------------------------------------- kaggle
@pytest.fixture
def fake_kaggle(monkeypatch):
    """Kaggle's REST API as a mock transport: the API host answers 302 to a signed storage link, the storage host answers with a zip of ``files``.
    ``private`` makes the API answer 404 (what Kaggle does for a private dataset) unless the request carries a Bearer token. ``calls`` records
    (host, path, authorization header) of every request so tests can see where the token went."""
    calls, files = [], {}
    state = {"private": False, "status": None}

    def handler(req: httpx.Request) -> httpx.Response:
        auth = req.headers.get("authorization")
        calls.append((req.url.host, req.url.path, auth))
        if req.url.host == "www.kaggle.com":
            if state["status"]:
                return httpx.Response(state["status"])
            if state["private"] and not auth:
                return httpx.Response(404)
            if state["private"] and auth != f"Bearer {KG_TOKEN}":
                return httpx.Response(401)
            return httpx.Response(302, headers={"location": "https://storage.googleapis.com/kaggle-data-sets/1/bundle/archive.zip?X-Goog-Signature=sig-0001"})
        if req.url.host == "storage.googleapis.com":
            return httpx.Response(200, content=make_zip(files) if files else b"PK\x05\x06" + b"\x00" * 18)     # an empty zip when there are no files
        return httpx.Response(500)
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    return {"calls": calls, "files": files, "state": state}


def make_zip(members: dict) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, d in members.items():
            z.writestr(n, d)
    return b.getvalue()


KG_HDR = {"X-Kaggle-Token": KG_TOKEN}


@pytest.mark.asyncio
async def test_a_public_dataset_imports_with_no_token_and_one_job_per_file(async_client: AsyncClient, fake_kaggle, caplog, tmp_path):
    caplog.set_level("DEBUG")
    fake_kaggle["files"].update({"tripura.csv": cwc_csv("Amarpur"), "assam.csv": cwc_csv("Dhubri"),
                                 "421820-99999-2025.gz": isd_gz([isd_line(DELHI, "202507010100")]), "README.txt": "about this data",
                                 "../../evil.csv": cwc_csv("Evil")})
    r = await post_import(async_client, "kaggle", "example-owner/example-rain")                    # no token header at all
    assert r.status_code == 202, r.text
    j = r.json()
    assert fake_kaggle["calls"][0] == ("www.kaggle.com", "/api/v1/datasets/download/example-owner/example-rain", None)
    assert fake_kaggle["calls"][1][0] == "storage.googleapis.com"
    assert j["provider"] == "kaggle" and j["origin"] == "kaggle.com/datasets/example-owner/example-rain"
    assert len(j["job_ids"]) == 4 and j["id"] == j["job_ids"][0] and j["skipped_files"] == ["README.txt"]
    jobs = [await get_job(async_client, i) for i in j["job_ids"]]
    assert sorted(x["source"] for x in jobs) == ["cwc", "cwc", "cwc", "isd"] and all(x["status"] == "done" for x in jobs)
    assert "sig-0001" not in r.text + caplog.text + json.dumps(jobs)                                  # the signed storage link is never logged or returned
    assert no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_a_dataset_link_from_the_browser_address_bar_works_too(async_client: AsyncClient, fake_kaggle):
    fake_kaggle["files"]["out.csv"] = cwc_csv()
    r = await post_import(async_client, "kaggle", "https://www.kaggle.com/datasets/example-owner/example-rain")
    assert r.status_code == 202 and r.json()["origin"] == "kaggle.com/datasets/example-owner/example-rain"
    assert fake_kaggle["calls"][0][1] == "/api/v1/datasets/download/example-owner/example-rain"


@pytest.mark.asyncio
async def test_a_private_dataset_asks_for_a_token_then_works_with_one_sent_to_kaggle_only(async_client: AsyncClient, fake_kaggle, caplog):
    caplog.set_level("DEBUG")
    fake_kaggle["state"]["private"] = True
    fake_kaggle["files"]["out.csv"] = cwc_csv()
    r = await post_import(async_client, "kaggle", "example-owner/private-rain")
    assert r.status_code == 428 and "Paste a Kaggle API token" in r.json()["detail"]                    # 428: the page opens its token popup
    assert [c[0] for c in fake_kaggle["calls"]] == ["www.kaggle.com"]
    fake_kaggle["calls"].clear()
    r = await post_import(async_client, "kaggle", "example-owner/private-rain", headers=KG_HDR)
    assert r.status_code == 202, r.text
    assert fake_kaggle["calls"][0][2] == f"Bearer {KG_TOKEN}"                                          # the token goes to the Kaggle API host ...
    assert all(c[2] is None for c in fake_kaggle["calls"][1:]) and fake_kaggle["calls"][1][0] == "storage.googleapis.com"   # ... and not to the storage link
    assert KG_TOKEN not in r.text + caplog.text


@pytest.mark.asyncio
async def test_a_wrong_token_or_a_dataset_that_does_not_exist_is_refused_plainly(async_client: AsyncClient, fake_kaggle):
    fake_kaggle["state"]["private"] = True
    r = await post_import(async_client, "kaggle", "example-owner/private-rain", headers={"X-Kaggle-Token": "KGAT_wrongtoken0001"})
    assert r.status_code == 403 and "refused the token" in r.json()["detail"] and "wrongtoken" not in r.text
    fake_kaggle["state"]["status"] = 500
    r = await post_import(async_client, "kaggle", "example-owner/example-rain")
    assert r.status_code == 502 and "HTTP 500" in r.json()["detail"]


@pytest.mark.asyncio
async def test_the_servers_own_token_is_the_fallback_when_the_caller_sends_none(async_client: AsyncClient, fake_kaggle, monkeypatch):
    monkeypatch.setattr(settings, "KAGGLE_API_TOKEN", KG_TOKEN)
    fake_kaggle["state"]["private"] = True
    fake_kaggle["files"]["out.csv"] = cwc_csv()
    r = await post_import(async_client, "kaggle", "example-owner/private-rain")
    assert r.status_code == 202 and fake_kaggle["calls"][0][2] == f"Bearer {KG_TOKEN}"


@pytest.mark.asyncio
async def test_notebook_output_is_fetched_from_the_kernel_endpoint(async_client: AsyncClient, fake_kaggle):
    fake_kaggle["files"]["out.csv"] = cwc_csv()
    r = await post_import(async_client, "kaggle", "kernel:example-owner/example-nb")
    assert r.status_code == 202 and fake_kaggle["calls"][0][1] == "/api/v1/kernels/output/download/example-owner/example-nb"
    r = await post_import(async_client, "kaggle", "https://www.kaggle.com/code/example-owner/example-nb")
    assert r.status_code == 202 and r.json()["origin"] == "kaggle.com/code/example-owner/example-nb"


@pytest.mark.asyncio
async def test_bad_references_are_not_echoed_and_nothing_is_requested(async_client: AsyncClient, fake_kaggle):
    for bad in ("https://evil.example.com/datasets/a/b", "http://www.kaggle.com/datasets/a/b", "a/b/c/d", "../etc/passwd", "kernel:nope", "a b/c"):
        r = await post_import(async_client, "kaggle", bad)
        assert r.status_code == 400 and bad not in r.text, bad
    assert fake_kaggle["calls"] == []


@pytest.mark.asyncio
async def test_a_gridded_netcdf_dataset_is_explained_not_just_refused(async_client: AsyncClient, fake_kaggle, tmp_path):
    fake_kaggle["files"].update({f"RF25_ind{1900 + i}_rfp25.nc": b"CDF\x01" for i in range(3)})        # what the real majorproj-rainfall dataset holds
    r = await post_import(async_client, "kaggle", "nathashalewis/majorproj-rainfall")
    assert r.status_code == 422
    msg = r.json()["detail"]
    assert ".nc x3" in msg and "NetCDF" in msg and "RF25_ind" not in msg                                 # file types are named, archive file names are not
    assert no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_a_redirect_to_another_host_is_refused_and_a_token_never_follows_a_redirect(async_client: AsyncClient, monkeypatch):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.host, req.headers.get("authorization")))
        return httpx.Response(302, headers={"location": "https://evil.example.com/steal"})
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    r = await post_import(async_client, "kaggle", "example-owner/example-rain", headers=KG_HDR)
    assert r.status_code == 400 and "allowed hosts" in r.json()["detail"]
    assert seen == [("www.kaggle.com", f"Bearer {KG_TOKEN}")]                                          # evil.example.com was never contacted


@pytest.mark.asyncio
async def test_a_dataset_with_no_data_files_or_an_oversize_zip_member_is_refused(async_client: AsyncClient, fake_kaggle, monkeypatch, tmp_path):
    fake_kaggle["files"]["notes.md"] = b"nothing"
    r = await post_import(async_client, "kaggle", "example-owner/example-rain")
    assert r.status_code == 422 and no_temp_left(tmp_path)
    fake_kaggle["files"].clear()
    monkeypatch.setattr(importers, "MAX_BYTES", 400)
    fake_kaggle["files"]["z.csv"] = b"x" * 5000
    r = await post_import(async_client, "kaggle", "example-owner/example-rain")
    assert r.status_code == 413 and no_temp_left(tmp_path)


def test_clean_kaggle_token_accepts_a_token_and_refuses_junk_without_echo():
    assert importers.clean_kaggle_token(None) is None and importers.clean_kaggle_token("  ") is None
    assert importers.clean_kaggle_token(f" {KG_TOKEN} ") == KG_TOKEN
    for bad in ("short", "has space in it 12345", "semi;colon;12345", "x" * 300):
        with pytest.raises(importers.ImportRefused) as e:
            importers.clean_kaggle_token(bad)
        assert bad not in str(e.value)


# ---------------------------------------------------------------------------------------------- public S3 without boto3
@pytest.fixture
def no_boto3(monkeypatch):
    """boto3 is not installed (as on a fresh machine) and S3 answers over plain HTTPS from a mock transport. ``seen`` records (host, path, authorization)."""
    seen, objects = [], {}

    def missing(req, region):
        raise importers.Boto3Missing()

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.host, req.url.path, req.headers.get("authorization")))
        key = (req.url.host, req.url.path)
        if key in objects:
            return httpx.Response(objects[key]) if isinstance(objects[key], int) else httpx.Response(200, content=objects[key])
        return httpx.Response(404)
    monkeypatch.setattr(importers, "make_s3_client", missing)
    monkeypatch.setattr(importers, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    return {"seen": seen, "objects": objects}


@pytest.mark.asyncio
async def test_a_public_s3_object_imports_over_https_when_boto3_is_missing(async_client: AsyncClient, no_boto3, tmp_path):
    no_boto3["objects"][("bucket-one.s3.amazonaws.com", "/rain/tr.csv")] = cwc_csv()
    r = await post_import(async_client, "aws", "s3://bucket-one/rain/tr.csv")
    assert r.status_code == 202, r.text
    assert (await get_job(async_client, r.json()["id"]))["status"] == "done"
    assert no_boto3["seen"] == [("bucket-one.s3.amazonaws.com", "/rain/tr.csv", None)]            # anonymous: no credentials were sent
    assert no_temp_left(tmp_path)


@pytest.mark.asyncio
async def test_a_regional_link_uses_the_regional_host_and_a_dotted_bucket_uses_path_style(async_client: AsyncClient, no_boto3):
    no_boto3["objects"][("bucket-one.s3.ap-south-1.amazonaws.com", "/tr.csv")] = cwc_csv()
    r = await post_import(async_client, "aws", "https://bucket-one.s3.ap-south-1.amazonaws.com/tr.csv")
    assert r.status_code == 202, r.text
    link = importers.parse_aws_link("s3://my.dotted.bucket/dir/a%20b.csv")
    assert importers.public_s3_url(link, "us-east-1") == "https://s3.amazonaws.com/my.dotted.bucket/dir/a%20b.csv"
    assert importers.public_s3_url(link, "eu-west-1") == "https://s3.eu-west-1.amazonaws.com/my.dotted.bucket/dir/a%20b.csv"
    plain = importers.parse_aws_link("s3://bucket-one/dir/a.csv")
    assert importers.public_s3_url(plain, "us-east-1") == "https://bucket-one.s3.amazonaws.com/dir/a.csv"


@pytest.mark.asyncio
async def test_private_or_missing_public_s3_objects_get_the_same_plain_answers(async_client: AsyncClient, no_boto3):
    no_boto3["objects"][("bucket-one.s3.amazonaws.com", "/secret.csv")] = 403
    r = await post_import(async_client, "aws", "s3://bucket-one/secret.csv")
    assert r.status_code == 403 and "private" in r.json()["detail"] and "send your AWS credentials" in r.json()["detail"]
    r = await post_import(async_client, "aws", "s3://bucket-one/none.csv")
    assert r.status_code == 404 and "not found" in r.json()["detail"]
    no_boto3["objects"][("bucket-one.s3.amazonaws.com", "/moved.csv")] = 301
    r = await post_import(async_client, "aws", "s3://bucket-one/moved.csv")
    assert r.status_code in (400, 502) and "region" in r.json()["detail"] or r.status_code == 502


@pytest.mark.asyncio
async def test_a_private_bucket_with_credentials_still_needs_boto3_and_says_so_without_echo(async_client: AsyncClient, no_boto3):
    hdr = {"X-Aws-Access-Key-Id": AWS_KEY, "X-Aws-Secret-Access-Key": AWS_SECRET, "X-Aws-Region": "ap-south-1"}
    r = await post_import(async_client, "aws", "s3://bucket-one/tr.csv", headers=hdr)
    assert r.status_code == 503 and "pip install boto3" in r.json()["detail"]
    assert AWS_KEY not in r.text and AWS_SECRET not in r.text
    assert no_boto3["seen"] == []                                                                   # nothing was requested without signing


# ---------------------------------------------------------------------------------------------- the ISD adapter
def read(tmp_path, lines, gz=True):
    p = tmp_path / "x.dat"
    p.write_bytes(isd_gz(lines) if gz else "\n".join(lines).encode())
    return list(isd.read_rows(str(p)))


def test_adapter_exposes_the_zero_value_flag():
    assert cwc.omits_zero_values is True and isd.omits_zero_values is False
    assert all(isinstance(getattr(m, "omits_zero_values"), bool) and m.ASSUMPTIONS for m in jobs_svc.SOURCES.values())


def test_parse_line_reads_station_time_groups_position_and_never_raises():
    ln = isd_line(DELHI, "202507010300", (("24", "0123", "3", "1"), ("06", "9999", "9", "9")))
    sid, when, groups = isd.parse_line(ln)
    assert sid == DELHI and when == datetime(2025, 7, 1, 3, tzinfo=timezone.utc) and groups == [(24, 12.3, "3", "1"), (6, None, "9", "9")]
    assert isd.parse_position(ln) == (28.584, 77.2)
    assert isd.parse_position(isd_line(DELHI, "202507010300", lat="+99999", lon="+999999")) == (None, None)
    for bad in ("", "short", isd_line(DELHI, "20251301030")[:60], "0200" + "x" * 150):
        assert isd.parse_line(bad) is None


def test_hourly_values_are_kept_and_stamped_at_the_start_of_their_hour(tmp_path):
    rows = read(tmp_path, [isd_line(DELHI, "202507010100", (("01", "0050", "3", "1"),)), isd_line(DELHI, "202507010200", (("01", "0000", "9", "1"),))])
    assert [(r.observed_at.isoformat(), r.value_mm, r.problem) for r in rows] == [("2025-07-01T00:00:00+00:00", 5.0, None), ("2025-07-01T01:00:00+00:00", 0.0, None)]
    assert rows[0].station_key == f"isd:{DELHI}" and rows[0].name == "Safdarjung" and (rows[0].latitude, rows[0].longitude) == (28.584, 77.2)


def test_overlap_rule_a_24_hour_total_is_dropped_when_finer_groups_lie_inside_it(tmp_path):
    lines = [isd_line(DELHI, "202507010100", (("01", "0100", "3", "1"),)),            # 1-hour value inside the 24-hour window
             isd_line(DELHI, "202507010300", (("24", "0900", "3", "1"),)),            # 24 h ending 03:00 overlaps it
             isd_line(DELHI, "202507020300", (("24", "0200", "3", "1"),))]            # the next window has no finer group: kept
    rows = read(tmp_path, lines)
    kept = [r for r in rows if not r.problem]
    dropped = [r for r in rows if r.problem]
    assert [(r.observed_at.isoformat(), r.value_mm) for r in kept] == [("2025-07-01T00:00:00+00:00", 10.0), ("2025-07-02T02:00:00+00:00", 20.0)]
    assert len(dropped) == 1 and "overlaps" in dropped[0].problem and "double counting" in dropped[0].problem
    assert "24-hour total stored as one value" in kept[1].warning and kept[0].warning is None
    assert sum(r.value_mm for r in kept) == 30.0                                       # 90 mm of the dropped total was NOT added on top


def test_two_reports_of_the_same_hour_count_once_and_the_better_quality_wins(tmp_path):
    lines = [isd_line(DELHI, "202507010551", (("01", "0100", "3", "2"),)), isd_line(DELHI, "202507010530", (("01", "0200", "3", "1"),))]
    kept = [r for r in read(tmp_path, lines) if not r.problem]
    assert [(r.observed_at.hour, r.value_mm) for r in kept] == [(5, 20.0)]


def test_missing_depth_and_erroneous_quality_are_not_stored_and_suspect_gets_a_warning(tmp_path):
    lines = [isd_line(DELHI, "202507010100", (("01", "9999", "9", "9"),)), isd_line(DELHI, "202507010200", (("01", "0300", "3", "3"),)),
             isd_line(DELHI, "202507010300", (("01", "0400", "3", "2"),)), "garbage line that is not an ISD record"]
    rows = read(tmp_path, lines)
    problems = [r.problem for r in rows if r.problem]
    assert any("missing (9999)" in p for p in problems) and any("erroneous" in p for p in problems) and "malformed ISD record" in problems
    kept = [r for r in rows if not r.problem]
    assert [(r.value_mm, "suspect" in r.warning) for r in kept] == [(40.0, True)]


def test_a_non_isd_file_is_rejected_whole_and_a_damaged_gzip_too(tmp_path):
    p = tmp_path / "x"
    p.write_bytes(b"a,b\n1,2\n")
    with pytest.raises(isd.IsdFormatError):
        list(isd.read_rows(str(p)))
    p.write_bytes(gzip.compress(b"x" * 1000)[:-8] + b"\x00" * 8)
    with pytest.raises(isd.IsdFormatError):
        list(isd.read_rows(str(p)))


def test_the_decompression_guard_and_unknown_stations_keep_their_own_position(tmp_path, monkeypatch):
    p = tmp_path / "x.gz"
    p.write_bytes(isd_gz([isd_line("999999-99999", "202507010100", lat="+12345", lon="+054321")]))
    rows = list(isd.read_rows(str(p)))
    assert rows[0].name == "ISD 999999-99999" and (rows[0].latitude, rows[0].longitude) == (12.345, 54.321)
    monkeypatch.setattr(isd, "MAX_TEXT_BYTES", 50)
    with pytest.raises(isd.IsdFormatError, match="safety limit"):
        list(isd.read_rows(str(p)))


@pytest.mark.asyncio
async def test_reimporting_the_same_file_stores_nothing_twice(async_client: AsyncClient, fake_s3):
    fake_s3["objects"][("bucket-one", "tr.csv")] = cwc_csv()
    a = (await post_import(async_client, "aws", "s3://bucket-one/tr.csv")).json()
    b = (await post_import(async_client, "aws", "s3://bucket-one/tr.csv")).json()
    assert a["sha256"] == b["sha256"] and a["id"] != b["id"]
    again = await get_job(async_client, b["id"])
    assert again["rows_inserted"] == 0 and again["rows_duplicate"] == 4
    async with async_session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Observation))).scalar_one() == 4
