"""Import step: fetch a data file from a user-supplied Amazon S3 link or a Kaggle dataset, safely, onto local disk, ready for an ingest job.

Security rules (each is tested with fakes; nothing here is tested against live S3 or Kaggle):
- Links are parsed, never fetched as given: only https hosts under amazonaws.com (every S3 form) or kaggle.com, no user info, no port, no IP literal.
- The https path (presigned URLs) resolves the host and refuses private, loopback, link-local, multicast, reserved and metadata addresses, follows
  redirects by hand (at most 3) and checks every hop with the same rules, so a redirect to another host is refused.
- The S3 object path (``s3://``, plain S3 https links) goes through boto3, anonymous (unsigned) unless the caller sent credentials; its endpoint is
  built by boto3 from a validated bucket and region, never from the link's host.
- At most MAX_BYTES (300 MB) per file: a Content-Length pre-check and a streaming cap. Files stream to disk and are hashed with sha256.
- Credentials, signatures and full links are never logged, stored, put in a job row, echoed or placed in an error message: errors here are fixed
  text, with at most an AWS error code or an HTTP status number. Callers delete the temp files in ``finally``.
- Known gap: the address check and the connection are two lookups, so a DNS-rebinding host could differ between them (see TODO.md).
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import ipaddress
import logging
import os
import re
import socket
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

import httpx

from backend.app.pipeline import aws_trigger as aws_svc
from backend.app.pipeline import cwc, isd
from backend.app.pipeline import jobs as jobs_svc
from backend.app.pipeline import kaggle_trigger as kaggle_svc

# httpx logs every request URL at INFO, and a presigned URL carries its signature in the query: keep that out of the logs.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

MAX_BYTES = jobs_svc.MAX_BYTES
MAX_FILES = 20
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_REDIRECTS = 3
KAGGLE_TIMEOUT_S = 900
DATA_SUFFIXES = (".csv", ".gz", ".txt", ".isd")
ALLOWED_SUFFIX = ".amazonaws.com"
KAGGLE_HOSTS = ("kaggle.com", "www.kaggle.com")

BAD_AWS_LINK = ("this is not a supported Amazon S3 link: use s3://bucket/key, https://bucket.s3.<region>.amazonaws.com/key, "
                "https://s3.<region>.amazonaws.com/bucket/key or a presigned https URL on amazonaws.com")
BAD_KAGGLE_LINK = "this is not a supported Kaggle reference: use owner/dataset-slug or kernel:owner/notebook-slug (or a kaggle.com dataset or code URL)"
UNKNOWN_FORMAT = ("the file is not a recognised format: expected a CWC hourly rainfall CSV (Station, Latitude, Longitude, Data Acquisition Time, "
                  "Telemetry Hourly Rainfall (mm)) or an NOAA ISD fixed-width file (gz)")


class ImportRefused(Exception):
    """A refusal or failure with a SAFE message (fixed text) and the HTTP status the API should answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class Fetched:
    path: str
    sha256: str
    size: int
    name: str                    # a safe display name (no path, no query)


@dataclass
class AwsLink:
    bucket: Optional[str]
    key: Optional[str]
    region: Optional[str]
    presigned: Optional[str]     # the full URL, kept only in memory, only when the link carries a signature
    origin: str


# ------------------------------------------------------------------------------------------------ link parsing
_BUCKET = re.compile(r"[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]")
_REGION = re.compile(r"[a-z]{2}(?:-[a-z]+){1,2}-[0-9]{1,2}")
_SIGNED = {"x-amz-signature", "signature", "x-amz-credential", "awsaccesskeyid"}
_S3_HOST = re.compile(r"(?:(?P<bucket>.+)\.)?s3(?:[.\-](?:dualstack\.)?(?P<region>[a-z]{2}(?:-[a-z]+){1,2}-[0-9]{1,2}))?\.amazonaws\.com")


def _safe_name(key: str) -> str:
    base = unquote(key).rstrip("/").split("/")[-1] or "download"
    return re.sub(r"[^A-Za-z0-9._\-]", "_", base)[:120] or "download"


def parse_aws_link(url: str) -> AwsLink:
    url = (url or "").strip()
    if not url or len(url) > 2048 or any(ord(c) < 33 or ord(c) > 126 for c in url):
        raise ImportRefused(BAD_AWS_LINK)
    parts = urlsplit(url)
    if parts.scheme == "s3":
        if parts.query or parts.username or parts.password or parts.port:
            raise ImportRefused(BAD_AWS_LINK)
        bucket, key = (parts.netloc or ""), unquote(parts.path.lstrip("/"))
        if not _BUCKET.fullmatch(bucket) or ".." in bucket or not key or ".." in key.split("/"):
            raise ImportRefused(BAD_AWS_LINK)
        return AwsLink(bucket, key, None, None, f"s3://{bucket}/{key}")
    if parts.scheme != "https" or parts.username or parts.password:
        raise ImportRefused(BAD_AWS_LINK)
    try:
        port = parts.port
    except ValueError:
        raise ImportRefused(BAD_AWS_LINK) from None
    host = (parts.hostname or "").lower()
    if port not in (None, 443) or not host.endswith(ALLOWED_SUFFIX):
        raise ImportRefused(BAD_AWS_LINK)
    m = _S3_HOST.fullmatch(host)
    if not m or not parts.path.strip("/"):
        raise ImportRefused(BAD_AWS_LINK)
    path = unquote(parts.path)
    if ".." in path.split("/"):
        raise ImportRefused(BAD_AWS_LINK)
    if m.group("bucket"):
        bucket, key = m.group("bucket"), path.lstrip("/")
    else:
        bucket, _, key = path.lstrip("/").partition("/")
    if not _BUCKET.fullmatch(bucket) or ".." in bucket or not key:
        raise ImportRefused(BAD_AWS_LINK)
    region = m.group("region")
    signed = any(k.lower() in _SIGNED for k, _ in parse_qsl(parts.query, keep_blank_values=True))
    origin = f"{host}{parts.path}"                       # host and path only: never the query (signatures, tokens)
    return AwsLink(bucket, key, region, url if signed else None, origin)


@dataclass
class KaggleRef:
    kind: str                    # dataset | kernel
    slug: str                    # owner/name
    origin: str


_SLUG = re.compile(r"[A-Za-z0-9_.\-]{1,60}/[A-Za-z0-9_.\-]{1,100}")


def parse_kaggle_ref(url: str) -> KaggleRef:
    url = (url or "").strip()
    if not url or len(url) > 512:
        raise ImportRefused(BAD_KAGGLE_LINK)
    if url.startswith("kernel:"):
        slug = url[len("kernel:"):]
        if not _SLUG.fullmatch(slug):
            raise ImportRefused(BAD_KAGGLE_LINK)
        return KaggleRef("kernel", slug, f"kaggle.com/code/{slug}")
    if "://" in url:
        parts = urlsplit(url)
        try:
            port = parts.port
        except ValueError:
            raise ImportRefused(BAD_KAGGLE_LINK) from None
        if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443) or (parts.hostname or "").lower() not in KAGGLE_HOSTS:
            raise ImportRefused(BAD_KAGGLE_LINK)
        segs = [s for s in parts.path.split("/") if s]
        if len(segs) >= 3 and segs[0] in ("datasets", "code") and _SLUG.fullmatch("/".join(segs[1:3])):
            kind = "dataset" if segs[0] == "datasets" else "kernel"
            return KaggleRef(kind, "/".join(segs[1:3]), f"kaggle.com/{segs[0]}/{'/'.join(segs[1:3])}")
        raise ImportRefused(BAD_KAGGLE_LINK)
    if not _SLUG.fullmatch(url):
        raise ImportRefused(BAD_KAGGLE_LINK)
    return KaggleRef("dataset", url, f"kaggle.com/datasets/{url}")


# ------------------------------------------------------------------------------------------------ address guard
def resolve_addresses(host: str) -> List[str]:
    """All addresses a host name resolves to. Tests replace this function."""
    return [ai[4][0] for ai in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


def _public(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv6Address) and ip.sixtofour is not None and not ip.sixtofour.is_global:
        return False
    return ip.is_global and not (ip.is_multicast or ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_unspecified)


async def check_url(url: str) -> None:
    """Refuse a URL that is not https on amazonaws.com, has user info or a port, or resolves to anything but public addresses."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        raise ImportRefused(BAD_AWS_LINK) from None
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443) or not host.endswith(ALLOWED_SUFFIX):
        raise ImportRefused("the link, or a redirect it follows, leaves Amazon S3 (https on amazonaws.com): refused")
    try:
        addrs = await asyncio.to_thread(resolve_addresses, host)
    except OSError:
        raise ImportRefused("the host of the link could not be resolved", 502) from None
    if not addrs or not all(_public(a) for a in addrs):
        raise ImportRefused("the host of the link resolves to a non-public address: refused")


# ------------------------------------------------------------------------------------------------ streaming to disk
def _new_temp() -> Tuple[int, str]:
    jobs_svc.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return tempfile.mkstemp(dir=jobs_svc.UPLOAD_DIR, suffix=".csv")


class _Sink:
    """Writes blocks to a new temp file, hashing and counting them; refuses more than MAX_BYTES."""

    def __init__(self) -> None:
        fd, self.path = _new_temp()
        self.f = os.fdopen(fd, "wb")
        self.sha, self.size = hashlib.sha256(), 0

    def write(self, block: bytes) -> None:
        self.size += len(block)
        if self.size > MAX_BYTES:
            raise ImportRefused(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MB", 413)
        self.sha.update(block)
        self.f.write(block)

    def close(self) -> None:
        self.f.close()

    def discard(self) -> None:
        self.f.close()
        Path(self.path).unlink(missing_ok=True)


HTTP_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None          # tests set a mock transport here; production leaves it None


async def download_https(url: str, name: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> Fetched:
    """GET a presigned S3 URL, streamed to disk. Redirects are followed by hand and every hop is checked."""
    sink: Optional[_Sink] = None
    try:
        async with httpx.AsyncClient(transport=transport or HTTP_TRANSPORT, follow_redirects=False, timeout=httpx.Timeout(30.0, read=60.0), trust_env=False) as client:
            current = url
            for _hop in range(MAX_REDIRECTS + 1):
                await check_url(current)
                async with client.stream("GET", current) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            raise ImportRefused("the host answered with a redirect that has no target", 502)
                        current = urljoin(current, loc)
                        continue
                    if r.status_code != 200:
                        raise ImportRefused(f"the host refused the download (HTTP {r.status_code}); an expired or wrong link, or no permission", 502)
                    cl = r.headers.get("content-length")
                    if cl and cl.isdigit() and int(cl) > MAX_BYTES:
                        raise ImportRefused(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MB", 413)
                    sink = _Sink()
                    async for block in r.aiter_bytes(1024 * 1024):
                        sink.write(block)
                    sink.close()
                    return Fetched(sink.path, sink.sha.hexdigest(), sink.size, name)
            raise ImportRefused("too many redirects", 502)
    except ImportRefused:
        if sink is not None:
            sink.discard()
        raise
    except httpx.HTTPError as e:
        if sink is not None:
            sink.discard()
        raise ImportRefused(f"the download failed ({type(e).__name__})", 502) from None
    except BaseException:
        if sink is not None:
            sink.discard()
        raise


def make_s3_client(req: Optional[aws_svc.Request], region: str) -> Any:
    """A boto3 S3 client: signed with the caller's keys when sent, otherwise anonymous (unsigned). The server's own keys are never used for an
    import. Tests replace this function."""
    try:
        import boto3                                           # lazy: the app and the tests start without it
        from botocore import UNSIGNED
        from botocore.config import Config
    except ImportError:
        raise ImportRefused("boto3 is not installed on the server (pip install boto3)", 503) from None
    kw: Dict[str, Any] = {}
    cfg_kw: Dict[str, Any] = {"region_name": region, "retries": {"max_attempts": 3, "mode": "standard"}, "connect_timeout": 10, "read_timeout": 60}
    if req is not None and req.key_id:
        kw.update(aws_access_key_id=req.key_id, aws_secret_access_key=req.secret)
        if req.token:
            kw["aws_session_token"] = req.token
    else:
        cfg_kw["signature_version"] = UNSIGNED
    return boto3.client("s3", config=Config(**cfg_kw), **kw)


def _s3_error(e: BaseException) -> ImportRefused:
    code = aws_svc._code_of(e)
    if code in aws_svc._MISSING_KEY:
        return ImportRefused("the object was not found in that bucket", 404)
    if code == "NoSuchBucket":
        return ImportRefused("the S3 bucket does not exist", 404)
    if code in aws_svc._AUTH:
        return ImportRefused(f"S3 refused access ({code}): the bucket is private or the credentials lack permission; send your AWS credentials", 403)
    if code in ("301", "PermanentRedirect", "AuthorizationHeaderMalformed", "400", "IllegalLocationConstraintException"):
        return ImportRefused("the bucket is in another region: use a link with the region (s3.<region>.amazonaws.com) or send X-Aws-Region", 400)
    name = type(e).__name__ if re.fullmatch(r"[A-Za-z0-9_]{1,60}", type(e).__name__) else "error"
    return ImportRefused(f"the S3 download failed ({code or name})", 502)


def _download_s3_sync(link: AwsLink, req: Optional[aws_svc.Request], region: str) -> Fetched:
    client = make_s3_client(req, region)
    sink: Optional[_Sink] = None
    try:
        try:
            head = client.head_object(Bucket=link.bucket, Key=link.key)
            n = head.get("ContentLength") if isinstance(head, dict) else None
            if isinstance(n, int) and n > MAX_BYTES:
                raise ImportRefused(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MB", 413)
            body = client.get_object(Bucket=link.bucket, Key=link.key)["Body"]
            sink = _Sink()
            while True:
                block = body.read(1024 * 1024)
                if not block:
                    break
                sink.write(block)
            sink.close()
        except ImportRefused:
            raise
        except Exception as e:                                  # noqa: BLE001: translated to a safe message, the original is dropped
            raise _s3_error(e) from None
        return Fetched(sink.path, sink.sha.hexdigest(), sink.size, _safe_name(link.key or ""))
    except BaseException:
        if sink is not None:
            sink.discard()
        raise


async def fetch_aws(link: AwsLink, req: Optional[aws_svc.Request], transport: Optional[httpx.AsyncBaseTransport] = None) -> List[Fetched]:
    if link.presigned:
        return [await download_https(link.presigned, _safe_name(link.key or ""), transport)]
    region = (req.region if req and req.region else None) or link.region or "us-east-1"
    return [await asyncio.to_thread(_download_s3_sync, link, req, region)]


# ------------------------------------------------------------------------------------------------ Kaggle
def run_command(args: List[str], creds: kaggle_svc.Credentials, cwd: str) -> str:
    """Run the kaggle command line with the caller's credentials. Tests replace this function. Output has the key removed."""
    try:
        p = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=KAGGLE_TIMEOUT_S, env=kaggle_svc._env(creds), cwd=cwd)
    except FileNotFoundError:
        raise ImportRefused("the kaggle command line is not installed on the server (pip install kaggle)", 503) from None
    except subprocess.TimeoutExpired:
        raise ImportRefused("the kaggle download timed out", 504) from None
    out = ((p.stdout or "") + (p.stderr or "")).replace(creds.key, "***")
    if p.returncode != 0:
        low = out.lower()
        if "401" in low or "403" in low or "unauthorized" in low or "forbidden" in low:
            raise ImportRefused("Kaggle refused the credentials or the dataset is private", 403)
        if "404" in low or "not found" in low:
            raise ImportRefused("Kaggle does not know that dataset or notebook", 404)
        raise ImportRefused(f"the kaggle command failed (exit {p.returncode})", 502)
    return out


def _extract_zip(zpath: Path, dest: Path, budget: List[int]) -> List[Path]:
    """Extract data members of a zip with our own file names and streaming caps (never trusts declared sizes or member paths)."""
    out: List[Path] = []
    try:
        with zipfile.ZipFile(zpath) as z:
            for i, info in enumerate(z.infolist()):
                if info.is_dir() or not info.filename.lower().endswith(DATA_SUFFIXES):
                    continue
                folder = dest / f"unzipped_{zpath.stem[:40]}_{i}"                 # our own folder and a sanitised name: the member's path is never used
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / _safe_name(info.filename)
                n = 0
                with z.open(info) as src, open(target, "wb") as dst:
                    while True:
                        block = src.read(1024 * 1024)
                        if not block:
                            break
                        n += len(block)
                        budget[0] += len(block)
                        if n > MAX_BYTES or budget[0] > MAX_TOTAL_BYTES:
                            dst.close()
                            target.unlink(missing_ok=True)
                            raise ImportRefused(f"a file inside the Kaggle download is larger than {MAX_BYTES // (1024 * 1024)} MB (or the total is too large)", 413)
                        dst.write(block)
                out.append(target)
    except zipfile.BadZipFile:
        raise ImportRefused("the Kaggle download is not a valid zip file", 502) from None
    return out


def _collect(root: Path) -> List[Path]:
    budget = [0]
    found: List[Path] = []
    for p in sorted(root.rglob("*")):
        if p.is_symlink() or not p.is_file():
            continue
        if p.suffix.lower() == ".zip":
            found.extend(_extract_zip(p, root, budget))
        elif p.name.lower().endswith(DATA_SUFFIXES):
            found.append(p)
    return found


def _fetch_kaggle_sync(ref: KaggleRef, creds: kaggle_svc.Credentials) -> List[Fetched]:
    sinks: List[_Sink] = []
    with tempfile.TemporaryDirectory(prefix="datamend_import_") as d:
        args = ["datasets", "download", ref.slug, "-p", d] if ref.kind == "dataset" else ["kernels", "output", ref.slug, "-p", d]
        run_command(args, creds, d)
        files = _collect(Path(d))
        if not files:
            raise ImportRefused("the Kaggle download holds no CSV, gz or txt file", 422)
        out: List[Fetched] = []
        try:
            for p in files[:MAX_FILES]:
                if p.stat().st_size > MAX_BYTES:
                    raise ImportRefused(f"a file in the Kaggle download is larger than {MAX_BYTES // (1024 * 1024)} MB", 413)
                sink = _Sink()
                sinks.append(sink)
                with open(p, "rb") as src:
                    while True:
                        block = src.read(1024 * 1024)
                        if not block:
                            break
                        sink.write(block)
                sink.close()
                out.append(Fetched(sink.path, sink.sha.hexdigest(), sink.size, _safe_name(p.name)))
            return out
        except BaseException:
            for s in sinks:
                s.discard()
            raise


async def fetch_kaggle(ref: KaggleRef, creds: Optional[kaggle_svc.Credentials]) -> List[Fetched]:
    creds = kaggle_svc.resolve(creds)
    if creds is None:
        raise ImportRefused(kaggle_svc.NO_CREDENTIALS, 409)
    return await asyncio.to_thread(_fetch_kaggle_sync, ref, creds)


# ------------------------------------------------------------------------------------------------ format detection
def _head(path: str, n: int = 65536) -> Tuple[bytes, bool]:
    with open(path, "rb") as f:
        magic = f.read(2)
        f.seek(0)
        if magic == b"\x1f\x8b":
            try:
                return gzip.GzipFile(fileobj=f).read(n), True
            except (gzip.BadGzipFile, EOFError, OSError):
                raise ImportRefused("the gzip file is damaged", 422) from None
        return f.read(n), False


def sniff(path: str) -> str:
    """'cwc' or 'isd' from the content (the header line of a CSV, or the fixed-width layout of the first record). Raises ImportRefused otherwise."""
    head, _ = _head(path)
    text = head.decode("utf-8-sig", errors="replace")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if cwc.COLUMNS["time"] in first and cwc.COLUMNS["mm"] in first:
        return "cwc"
    if isd.looks_like_isd(first):
        return "isd"
    raise ImportRefused(UNKNOWN_FORMAT, 422)


def gunzip_to_temp(path: str) -> Fetched:
    """Decompress a gzip file into a new temp file (capped at MAX_BYTES), remove the original."""
    sink = _Sink()
    try:
        with gzip.open(path, "rb") as f:
            while True:
                block = f.read(1024 * 1024)
                if not block:
                    break
                sink.write(block)
        sink.close()
    except (gzip.BadGzipFile, EOFError, OSError):
        sink.discard()
        raise ImportRefused("the gzip file is damaged", 422) from None
    except BaseException:
        sink.discard()
        raise
    Path(path).unlink(missing_ok=True)
    return Fetched(sink.path, sink.sha.hexdigest(), sink.size, "")


def prepare(f: Fetched, fmt: str) -> Tuple[Fetched, str]:
    """Settle the format of a downloaded file and leave it readable by its adapter. ``fmt`` is 'auto', 'cwc' or 'isd'. A gzip CSV is unpacked
    (the CWC reader wants text); ISD reads gzip itself. Returns the (possibly new) file and the format actually used."""
    detected = sniff(f.path) if fmt == "auto" else fmt
    if detected == "cwc":
        with open(f.path, "rb") as fh:
            gz = fh.read(2) == b"\x1f\x8b"
        if gz:
            new = gunzip_to_temp(f.path)
            name = f.name[:-3] if f.name.lower().endswith(".gz") else f.name
            f = Fetched(new.path, new.sha256, new.size, name)
    return f, detected
