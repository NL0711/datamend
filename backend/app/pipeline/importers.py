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
import shutil
import socket
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, quote, unquote, urljoin, urlsplit

import httpx

from backend.app.pipeline import aws_trigger as aws_svc
from backend.app.pipeline import cwc, isd
from backend.app.pipeline import jobs as jobs_svc
from backend.app.pipeline import kaggle_trigger as kaggle_svc
from backend.app.validation import ingest as intake_ingest

# httpx logs every request URL at INFO, and a presigned URL carries its signature in the query: keep that out of the logs.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

MAX_BYTES = jobs_svc.MAX_BYTES
MAX_FILES = 20
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_REDIRECTS = 3
KAGGLE_TIMEOUT_S = 900
DATA_SUFFIXES = (".csv", ".gz", ".txt", ".json")
FORMAT_IDS = ("auto", "cwc", "isd", "reading", "daily")
ACCEPTED_FORMATS = ("Accepted: a CWC hourly rainfall CSV (Station, Latitude, Longitude, Data Acquisition Time, Telemetry Hourly Rainfall (mm)); "
                    "an NOAA ISD hourly file (fixed-width or CSV, plain or .gz, with AA1 rainfall groups); a reading CSV or JSON (timestamp, "
                    "station_id and accumulation and/or intensity); a daily CSV or JSON (day, station_id, mm).")
ALLOWED_SUFFIX = ".amazonaws.com"
KAGGLE_HOSTS = ("kaggle.com", "www.kaggle.com")

BAD_AWS_LINK = ("this is not a supported Amazon S3 link: use s3://bucket/key, https://bucket.s3.<region>.amazonaws.com/key, "
                "https://s3.<region>.amazonaws.com/bucket/key or a presigned https URL on amazonaws.com")
BAD_KAGGLE_LINK = "this is not a supported Kaggle reference: use owner/dataset-slug or kernel:owner/notebook-slug (or a kaggle.com dataset or code URL)"
UNKNOWN_FORMAT = "the file is not a recognised format. " + ACCEPTED_FORMATS


def unknown_format(first_line: str) -> str:
    """The refusal for a file no reader recognises: what is accepted and the first line the sniffer saw (cut, printable characters only)."""
    seen = _seen(first_line)
    return UNKNOWN_FORMAT + (f" The first line of the file was: {seen!r}" if seen else " The file has no text lines.")


def _seen(first_line: str) -> str:
    return re.sub(r"[^\x20-\x7e]", "?", first_line.strip())[:120]


class Boto3Missing(Exception):
    """boto3 is not installed. A public bucket then falls back to a plain HTTPS download; a private one (credentials) cannot."""


class ImportRefused(Exception):
    """A refusal or failure with a SAFE message (fixed text) and the HTTP status the API should answer with."""

    def __init__(self, message: str, status: int = 400, short: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.short = short or message              # the reason as listed beside a skipped file inside an archive


@dataclass
class Fetched:
    path: str
    sha256: str
    size: int
    name: str                    # a safe display name (no path, no query)
    ext: str = ""                # 'csv' or 'json' once prepare has settled a reading or daily file; empty otherwise


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


async def check_url(url: str, allowed_hosts: Optional[Tuple[str, ...]] = None) -> None:
    """Refuse a URL that is not https on amazonaws.com (or, with ``allowed_hosts``, on exactly those hosts), has user info or a port, or resolves
    to anything but public addresses."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        raise ImportRefused(BAD_AWS_LINK) from None
    host = (parts.hostname or "").lower()
    host_ok = host in allowed_hosts if allowed_hosts is not None else host.endswith(ALLOWED_SUFFIX)
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443) or not host_ok:
        raise ImportRefused("the link, or a redirect it follows, leaves the allowed hosts (https only): refused" if allowed_hosts is not None
                            else "the link, or a redirect it follows, leaves Amazon S3 (https on amazonaws.com): refused")
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
    """Writes blocks to a new temp file, hashing and counting them; refuses more than MAX_BYTES (or ``limit``: a zip archive may hold several files)."""

    def __init__(self, limit: Optional[int] = None) -> None:
        fd, self.path = _new_temp()
        self.f = os.fdopen(fd, "wb")
        self.sha, self.size, self.limit = hashlib.sha256(), 0, limit

    def write(self, block: bytes) -> None:
        self.size += len(block)
        cap = self.limit if self.limit is not None else MAX_BYTES
        if self.size > cap:
            raise ImportRefused(f"the file is larger than {cap // (1024 * 1024)} MB", 413)
        self.sha.update(block)
        self.f.write(block)

    def close(self) -> None:
        self.f.close()

    def discard(self) -> None:
        self.f.close()
        Path(self.path).unlink(missing_ok=True)


HTTP_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None          # tests set a mock transport here; production leaves it None


async def download_https(url: str, name: str, transport: Optional[httpx.AsyncBaseTransport] = None,
                         refusals: Optional[Dict[int, Tuple[str, int]]] = None) -> Fetched:
    """GET a presigned S3 URL, streamed to disk. Redirects are followed by hand and every hop is checked. ``refusals`` maps an HTTP status to a
    (safe message, our status) so a caller can turn 403 or 404 into a plain answer."""
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
                    if r.status_code in (refusals or {}):
                        msg, code = (refusals or {})[r.status_code]
                        raise ImportRefused(msg, code)
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
        raise Boto3Missing() from None
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
    try:
        return [await asyncio.to_thread(_download_s3_sync, link, req, region)]
    except Boto3Missing:
        if req is not None and req.key_id:        # the caller's own keys need boto3 to sign the request
            raise ImportRefused("boto3 is not installed on the server, and a private bucket needs it (pip install boto3)", 503) from None
        return [await download_s3_public(link, region, transport)]


def public_s3_url(link: AwsLink, region: str) -> str:
    """The plain HTTPS address of a public S3 object, built from the already validated bucket, region and key (never from the pasted host)."""
    key = quote(link.key, safe="/")
    if "." in link.bucket:                         # a dotted bucket name does not match the wildcard certificate: path style
        host = "s3.amazonaws.com" if region == "us-east-1" else f"s3.{region}.amazonaws.com"
        return f"https://{host}/{link.bucket}/{key}"
    host = f"{link.bucket}.s3.amazonaws.com" if region == "us-east-1" else f"{link.bucket}.s3.{region}.amazonaws.com"
    return f"https://{host}/{key}"


async def download_s3_public(link: AwsLink, region: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> Fetched:
    """Fetch a PUBLIC S3 object over HTTPS with no AWS library and no credentials (used when boto3 is not installed). A private or missing object
    answers 403 or 404, which becomes the same plain message the boto3 path gives."""
    refusals = {403: ("S3 refused access (403): the bucket is private or the object is not public; send your AWS credentials", 403),
                404: ("the object was not found in that bucket", 404),
                301: ("the bucket is in another region: use a link with the region (s3.<region>.amazonaws.com)", 400),
                400: ("the bucket is in another region: use a link with the region (s3.<region>.amazonaws.com)", 400)}
    return await download_https(public_s3_url(link, region), _safe_name(link.key or ""), transport, refusals)


# ------------------------------------------------------------------------------------------------ Kaggle
KAGGLE_API = "https://www.kaggle.com/api/v1"
KAGGLE_FETCH_HOSTS = ("www.kaggle.com", "storage.googleapis.com")      # the API host, then the signed download link it redirects to
TOKEN_REQUIRED_STATUS = 428                                           # Precondition Required: the page opens its token popup on this status
TOKEN_REQUIRED = "This dataset is private or could not be found. Paste a Kaggle API token to try again."
_TOKEN = re.compile(r"[A-Za-z0-9_\-]{8,200}")


def clean_kaggle_token(token: Optional[str]) -> Optional[str]:
    """A Kaggle API token (KGAT_...) from a header or the server's environment, or None when empty. A malformed one is refused without echo."""
    t = (token or "").strip()
    if not t:
        return None
    if not _TOKEN.fullmatch(t):
        raise ImportRefused("that does not look like a Kaggle API token (letters, digits, underscore and hyphen only)", 400)
    return t


def server_kaggle_token() -> Optional[str]:
    """The server's own token (KAGGLE_API_TOKEN in the environment), used only when the caller sent none. Never logged or returned."""
    from backend.app.config import settings
    try:
        return clean_kaggle_token(getattr(settings, "KAGGLE_API_TOKEN", ""))
    except ImportRefused:
        return None


async def download_kaggle(ref: KaggleRef, token: Optional[str], transport: Optional[httpx.AsyncBaseTransport] = None) -> Fetched:
    """Download a public Kaggle dataset (or notebook output) over HTTPS, with no account. A token, when given, goes as a Bearer header to the
    Kaggle API host only (never to the redirected storage link). The answer to an anonymous request for a private dataset is 401, 403 or 404:
    that becomes status 428 (``TOKEN_REQUIRED``) so the page can ask for a token. Hosts are allow-listed, every hop is address-checked, and the
    file streams to disk with the usual size cap."""
    path = f"/datasets/download/{ref.slug}" if ref.kind == "dataset" else f"/kernels/output/download/{ref.slug}"
    sink: Optional[_Sink] = None
    try:
        async with httpx.AsyncClient(transport=transport or HTTP_TRANSPORT, follow_redirects=False, timeout=httpx.Timeout(30.0, read=120.0), trust_env=False) as client:
            current, first = KAGGLE_API + path, True
            for _hop in range(MAX_REDIRECTS + 1):
                await check_url(current, KAGGLE_FETCH_HOSTS)
                headers = {"Authorization": f"Bearer {token}"} if (token and first) else {}
                async with client.stream("GET", current, headers=headers) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            raise ImportRefused("Kaggle answered with a redirect that has no target", 502)
                        current, first = urljoin(current, loc), False
                        continue
                    if r.status_code in (401, 403, 404):
                        if token:
                            raise ImportRefused("Kaggle refused the token, or your account has no access to that dataset", 403)
                        raise ImportRefused(TOKEN_REQUIRED, TOKEN_REQUIRED_STATUS)
                    if r.status_code != 200:
                        raise ImportRefused(f"Kaggle did not return the file (HTTP {r.status_code})", 502)
                    cl = r.headers.get("content-length")
                    if cl and cl.isdigit() and int(cl) > MAX_TOTAL_BYTES:
                        raise ImportRefused(f"the download is larger than {MAX_TOTAL_BYTES // (1024 * 1024)} MB", 413)
                    sink = _Sink(MAX_TOTAL_BYTES)               # the archive may hold several files; each one inside is still capped at MAX_BYTES
                    async for block in r.aiter_bytes(1024 * 1024):
                        sink.write(block)
                    sink.close()
                    return Fetched(sink.path, sink.sha.hexdigest(), sink.size, _safe_name(ref.slug.replace("/", "_")))
            raise ImportRefused("too many redirects", 502)
    except ImportRefused:
        if sink is not None:
            sink.discard()
        raise
    except httpx.HTTPError as e:
        if sink is not None:
            sink.discard()
        raise ImportRefused(f"the Kaggle download failed ({type(e).__name__})", 502) from None
    except BaseException:
        if sink is not None:
            sink.discard()
        raise


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


def _nothing_to_import(root: Path) -> str:
    """Why a download gave no importable file, naming what it did hold (file types only, never names or paths from the archive)."""
    counts: Dict[str, int] = {}
    for p in root.rglob("*"):
        names = []
        if p.is_file() and p.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(p) as z:
                    names = [i.filename for i in z.infolist() if not i.is_dir()]
            except zipfile.BadZipFile:
                continue
        elif p.is_file():
            names = [p.name]
        for n in names:
            ext = re.sub(r"[^a-z0-9]", "", os.path.splitext(n)[1].lower())[:8] or "no-extension"
            counts[ext] = counts.get(ext, 0) + 1
    held = ", ".join(f".{e} x{n}" if e != "no-extension" else f"{n} without an extension" for e, n in sorted(counts.items(), key=lambda kv: -kv[1])[:4])
    hint = " Gridded NetCDF (.nc) data is for model training, not for this step." if "nc" in counts else ""
    return (f"This dataset has no file the Import step can read (it holds {held}).{hint} {ACCEPTED_FORMATS}") if held else "the Kaggle download holds no file at all"


def _fetch_kaggle_sync(downloaded: Fetched) -> List[Fetched]:
    """Unpack what download_kaggle fetched (a zip, or a single data file) into data files, each as its own capped, hashed temp file."""
    sinks: List[_Sink] = []
    with tempfile.TemporaryDirectory(prefix="datamend_import_") as d:
        with open(downloaded.path, "rb") as probe:
            is_zip = probe.read(4) == b"PK\x03\x04"
        target = Path(d) / ("download.zip" if is_zip else _safe_name(downloaded.name if downloaded.name.lower().endswith(DATA_SUFFIXES) else downloaded.name + ".csv"))
        shutil.move(downloaded.path, target)                 # the temp file moves into our own folder; nothing else keeps a reference to it
        files = _collect(Path(d))
        if not files:
            raise ImportRefused(_nothing_to_import(Path(d)), 422)
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


async def fetch_kaggle(ref: KaggleRef, token: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None) -> List[Fetched]:
    """Public datasets need no token. ``token`` is the caller's (from the popup); the server's KAGGLE_API_TOKEN is the fallback. A private dataset
    with no usable token answers status 428 so the page can ask for one."""
    token = clean_kaggle_token(token) or server_kaggle_token()
    downloaded = await download_kaggle(ref, token, transport)
    try:
        return await asyncio.to_thread(_fetch_kaggle_sync, downloaded)
    finally:
        Path(downloaded.path).unlink(missing_ok=True)       # normally already moved; a failure before the move must not leave it behind


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


def _json_like(head: bytes) -> bool:
    return head.lstrip(b"\xef\xbb\xbf \t\r\n")[:1] in (b"[", b"{")


def too_big_for_intake() -> ImportRefused:
    return ImportRefused(f"the file is larger than {intake_ingest.MAX_BYTES // (1024 * 1024)} MB, the limit for reading and daily files "
                         f"(CWC and ISD files can be up to {MAX_BYTES // (1024 * 1024)} MB)", 413)


def sniff(path: str) -> str:
    """The format from the content, gzip looked through: 'cwc' (its header line), 'isd' (a fixed-width record or the CSV header), then 'reading' or
    'daily' (the platform's own headers, JSON by its keys). Raises ImportRefused, listing the accepted formats and the first line seen, otherwise."""
    head, _ = _head(path)
    text = head.decode("utf-8-sig", errors="replace")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if cwc.COLUMNS["time"] in first and cwc.COLUMNS["mm"] in first:
        return "cwc"
    if isd.sniff_layout(first):
        return "isd"
    content = head
    if _json_like(head):
        content, _ = _head(path, intake_ingest.MAX_BYTES + 1)
        if len(content) > intake_ingest.MAX_BYTES:
            raise too_big_for_intake()
    found = intake_ingest.sniff_profile(content)
    if found:
        return found[0]
    raise ImportRefused(unknown_format(first), 422, short=f"not a recognised format (first line {_seen(first)!r})")


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
    """Settle the format of a downloaded file and leave it readable by its reader. ``fmt`` is one of FORMAT_IDS. A gzip file is unpacked (every
    reader wants text), whatever its format. Returns the (possibly new) file and the format actually used: cwc, isd, reading or daily. A reading
    or daily file also gets ``ext`` ('csv' or 'json') and must fit the intake size limit."""
    detected = sniff(f.path) if fmt == "auto" else fmt
    with open(f.path, "rb") as fh:
        gz = fh.read(2) == b"\x1f\x8b"
    if gz:
        new = gunzip_to_temp(f.path)
        name = f.name[:-3] if f.name.lower().endswith(".gz") else f.name
        f = Fetched(new.path, new.sha256, new.size, name)
    if detected in ("reading", "daily"):
        if f.size > intake_ingest.MAX_BYTES:
            if gz:
                Path(f.path).unlink(missing_ok=True)          # the unpacked copy is ours and nobody else knows it
            raise too_big_for_intake()
        with open(f.path, "rb") as fh:
            f.ext = "json" if _json_like(fh.read(64)) else "csv"
    return f, detected


def declaration_hint(reason: str) -> str:
    """A file-level rejection from intake, with what to send added when the cause is a missing declaration."""
    if "accumulation_mode" in reason and "declare" in reason:
        return (f"{reason}. Send the request field accumulation_mode: 'cumulative' (each value is a running total) or 'per_reading' "
                "(each value is the rain since the previous reading).")
    if "no time zone" in reason:
        return f"{reason}. Send the request field timezone ('UTC', an offset such as '+05:30', or an IANA name such as 'Asia/Kolkata')."
    return reason


async def run_reading_file(session: Any, f: Fetched, profile: str, accumulation_mode: Optional[str] = None, timezone: Optional[str] = None,
                           interval_minutes: Optional[float] = None, synthetic: bool = False) -> Any:
    """A prepared reading or daily file through the SAME intake as an upload (``intake.run_file``): header aliases, file-level reject, row-level
    flags, the declared accumulation mode, zone and interval. A rejected file is stored as a failed run, as for an upload, and raised as an
    ImportRefused (422) whose message says what to send. Returns the ValidationRun."""
    from backend.app.validation import intake
    from backend.app.validation.ingest import InputRejected
    content = await asyncio.to_thread(_read_all, f.path)
    stem = f.name.rsplit(".", 1)[0] if "." in f.name else f.name
    try:
        return await intake.run_file(session, content, f"{stem or 'import'}.{f.ext or 'csv'}", profile, accumulation_mode, timezone, interval_minutes, synthetic)
    except InputRejected as e:
        raise ImportRefused(declaration_hint(str(e)), 422) from None


def _read_all(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(intake_ingest.MAX_BYTES + 1)
