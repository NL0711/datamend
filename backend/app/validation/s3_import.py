"""Fetch one CSV or JSON file from a PUBLIC S3 bucket (anonymous read; no AWS credentials are asked for or supported).

Accepts ``s3://bucket/key``, ``https://bucket.s3[.region].amazonaws.com/key`` or ``https://s3[.region].amazonaws.com/bucket/key``. A link
that ends in ``/`` (or names only a bucket) is a folder: its files are listed and the one usable CSV/JSON is taken. The request host is
always built from the validated bucket name under amazonaws.com, so a link cannot point this fetch at another server.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

import httpx

from backend.app.validation.ingest import MAX_BYTES
from backend.app.validation.kaggle_import import KaggleError, KaggleFile, pick

_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class S3Error(Exception):
    """A problem the user can act on (bad link, not public, no usable file, too large)."""


def looks_like_s3(text: str) -> bool:
    t = (text or "").strip().lower()
    return t.startswith("s3://") or "amazonaws.com" in t


def parse(text: str) -> Tuple[str, str]:
    """``(bucket, key)``; the key is empty or ends in ``/`` for a folder."""
    t = (text or "").strip()
    if t.lower().startswith("s3://"):
        bucket, _, key = t[5:].partition("/")
    else:
        u = urlparse(t if "//" in t else f"https://{t}")
        host = (u.hostname or "").lower()
        path = unquote(u.path).lstrip("/")
        if not host.endswith(".amazonaws.com"):
            raise S3Error("That is not an S3 link. Use s3://bucket/path or an amazonaws.com URL.")
        if re.match(r"^s3[.-]", host):                      # path style: s3.region.amazonaws.com/bucket/key
            bucket, _, key = path.partition("/")
        else:                                               # virtual-hosted: bucket.s3[.region].amazonaws.com/key
            bucket, key = host.split(".s3", 1)[0], path
    if not _BUCKET.match(bucket or "") or ".." in bucket:
        raise S3Error("That is not an S3 link. Use s3://bucket/path or an amazonaws.com URL.")
    return bucket, key


def _denied(res: httpx.Response) -> None:
    if res.status_code in (401, 403):
        raise S3Error("That bucket or file is not public. Only public S3 data can be imported.")
    if res.status_code == 404:
        raise S3Error("Nothing found at that S3 link.")
    if res.status_code >= 400:
        raise S3Error(f"S3 answered {res.status_code}. Try again later.")


async def _list(client: httpx.AsyncClient, bucket: str, prefix: str) -> List[KaggleFile]:
    res = await client.get(f"https://{bucket}.s3.amazonaws.com/", params={"list-type": "2", "prefix": prefix, "delimiter": "/", "max-keys": "1000"})
    _denied(res)
    try:
        root = ET.fromstring(res.content)
    except ET.ParseError:
        raise S3Error("S3 sent a reply that could not be read.")
    return [KaggleFile(c.findtext(f"{_NS}Key") or "", int(c.findtext(f"{_NS}Size") or 0)) for c in root.iter(f"{_NS}Contents")]


async def fetch(url: str, filename: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
    """Return ``(file name, bytes)``."""
    bucket, key = parse(url)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, max_redirects=3, transport=transport) as client:
        if not key or key.endswith("/"):
            try:
                chosen = pick([f for f in await _list(client, bucket, key) if f.name != key], filename)
            except KaggleError as e:                      # the same file-choice rules and wording as a Kaggle dataset
                raise S3Error(str(e).replace("dataset", "folder"))
            key = chosen.name
        elif not key.lower().endswith((".csv", ".json")):
            raise S3Error("That file is not a CSV or JSON file.")
        body = bytearray()
        async with client.stream("GET", f"https://{bucket}.s3.amazonaws.com/{quote(key)}") as res:
            if res.status_code >= 400:
                await res.aread()
                _denied(res)
            async for chunk in res.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise S3Error(f"That file is larger than the {MAX_BYTES // 1048576} MB limit.")
        return key.rsplit("/", 1)[-1], bytes(body)
