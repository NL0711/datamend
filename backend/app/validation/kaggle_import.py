"""Fetch one CSV or JSON file from a Kaggle dataset for the upload pipeline.

A public dataset needs no credentials. When Kaggle answers 401 or 403 (a private dataset, or one that does not exist: Kaggle gives the
same answer for both) the caller gets ``NeedsToken`` and asks the user for an API token only. The token is used for the requests of this
one call; it is never stored, logged or echoed. Only a single file is downloaded, never the whole archive, and never above MAX_BYTES.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from backend.app.validation.ingest import MAX_BYTES

API = "https://www.kaggle.com/api/v1/datasets"
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
_USABLE = (".csv", ".json")
_MAX_PAGES = 5


class KaggleError(Exception):
    """A problem the user can act on (bad link, no usable file, too large)."""


class NeedsToken(KaggleError):
    """Kaggle refused the request without a token (private dataset, or a wrong link)."""


@dataclass
class KaggleFile:
    name: str
    size: int


def parse_ref(text: str) -> str:
    """``owner/slug`` from a dataset URL or from ``owner/slug`` itself."""
    t = (text or "").strip()
    if "kaggle.com" in t:
        parts = [p for p in urlparse(t if "//" in t else f"https://{t}").path.split("/") if p]
        if len(parts) >= 3 and parts[0] == "datasets":
            t = f"{parts[1]}/{parts[2]}"
    t = t.strip("/")
    if not _REF.match(t):
        raise KaggleError("That is not a Kaggle dataset link. Paste a link like kaggle.com/datasets/owner/name.")
    return t


def _headers(token: Optional[str]) -> dict:
    return {"Authorization": f"Bearer {token.strip()}"} if token and token.strip() else {}


def _check(res: httpx.Response, token: Optional[str]) -> None:
    if res.status_code in (401, 403, 404):
        if token and token.strip():
            raise KaggleError("Kaggle did not accept that token for this dataset. Check the token and that you can open the dataset.")
        raise NeedsToken("This dataset is private or the link is wrong.")
    if res.status_code >= 400:
        raise KaggleError(f"Kaggle answered {res.status_code}. Try again later.")


async def list_files(client: httpx.AsyncClient, ref: str, token: Optional[str]) -> List[KaggleFile]:
    files: List[KaggleFile] = []
    page_token = ""
    for _ in range(_MAX_PAGES):
        res = await client.get(f"{API}/list/{ref}", params={"pageToken": page_token} if page_token else None, headers=_headers(token))
        _check(res, token)
        body = res.json()
        files += [KaggleFile(f["name"], int(f.get("totalBytes") or 0)) for f in body.get("datasetFiles", []) if f.get("name")]
        page_token = body.get("nextPageToken") or ""
        if not page_token:
            break
    return files


def pick(files: List[KaggleFile], wanted: Optional[str] = None) -> KaggleFile:
    """The file to import: the named one, else the only usable one. Never guesses between several."""
    usable = [f for f in files if f.name.lower().endswith(_USABLE)]
    if wanted:
        hit = next((f for f in files if f.name == wanted), None)
        if hit is None:
            raise KaggleError(f"{wanted} is not in this dataset.")
        usable = [hit]
    if not usable:
        kinds = sorted({f.name.rsplit(".", 1)[-1].lower() for f in files if "." in f.name})
        raise KaggleError("This dataset has no CSV or JSON file" + (f" (it holds .{', .'.join(kinds)})." if kinds else "."))
    fits = [f for f in usable if 0 < f.size <= MAX_BYTES]
    if not fits:
        raise KaggleError(f"{usable[0].name} is {usable[0].size / 1048576:.0f} MB; the limit is {MAX_BYTES // 1048576} MB.")
    if len(fits) > 1 and not wanted:
        raise KaggleError("This dataset has several files; pick one: " + ", ".join(f.name for f in fits[:8]) + ("…" if len(fits) > 8 else ""))
    return fits[0]


async def fetch(url: str, token: Optional[str] = None, filename: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
    """Return ``(file name, bytes)`` for the one usable file of the dataset."""
    ref = parse_ref(url)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False, transport=transport) as client:
        chosen = pick(await list_files(client, ref, token), filename)
        res = await client.get(f"{API}/download/{ref}", params={"fileName": chosen.name}, headers=_headers(token))
        if res.status_code in (301, 302, 303, 307, 308) and res.headers.get("location"):
            res = await client.get(res.headers["location"])           # the signed storage link takes no Authorization header
        _check(res, token)
        content = res.content
        if content[:2] == b"PK" and not chosen.name.lower().endswith(".zip"):          # Kaggle sometimes wraps a single file in a zip
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                members = [i for i in z.infolist() if not i.is_dir()]
                if len(members) != 1 or members[0].file_size > MAX_BYTES:
                    raise KaggleError(f"{chosen.name} could not be unpacked within the {MAX_BYTES // 1048576} MB limit.")
                content = z.read(members[0])
        if len(content) > MAX_BYTES:
            raise KaggleError(f"{chosen.name} is larger than the {MAX_BYTES // 1048576} MB limit.")
        return chosen.name.rsplit("/", 1)[-1], content


__all__ = ["KaggleError", "NeedsToken", "fetch", "parse_ref"]
