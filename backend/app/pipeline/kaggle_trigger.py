"""Start a retraining run as a private Kaggle script notebook, check on it, and fetch its result.

The notebook is the standalone trainer (pipeline/fusion.py) with the snapshot embedded, so it needs no dataset upload and no internet. It
runs on Kaggle's free CPU (the label-fusion model does not need a GPU; a GPU would be for the RF25 STNet, which this does not retrain).
Uses the ``kaggle`` command line (pip install kaggle) with the CALLER's credentials for one request (headers X-Kaggle-Username and
X-Kaggle-Key) or, when none are sent, KAGGLE_USERNAME and KAGGLE_KEY from the server's environment. The key lives in memory for the request
and in the command's environment; it is never logged, stored or put in an error message. UNTESTED against live Kaggle: the tests mock the command line. Kaggle's public API cannot show
the remaining weekly quota or cancel a running notebook, so this module cannot either.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config import settings

TIMEOUT_S = 120
FUSION_SOURCE = Path(__file__).with_name("fusion.py")


class KaggleError(RuntimeError):
    pass


USERNAME_RE = re.compile(r"[A-Za-z0-9_.\-]{1,60}")
KEY_RE = re.compile(r"[\x21-\x7e]{1,200}")                      # printable, no spaces or control characters, at most 200 long
NO_CREDENTIALS = ("Kaggle is not configured: set KAGGLE_USERNAME and KAGGLE_KEY in the server's environment, "
                  "or supply your own Kaggle username and API key (the X-Kaggle-Username and X-Kaggle-Key headers; the Data pipeline page has a form)")


class Credentials:
    """A Kaggle account for ONE request. Held in memory only: never stored, logged, or shown (repr and str hide the key)."""
    __slots__ = ("username", "key")

    def __init__(self, username: str, key: str):
        self.username, self.key = username, key

    def __repr__(self) -> str:
        return f"Credentials(username={self.username!r}, key='***')"

    __str__ = __repr__


def from_request(username: Optional[str], key: Optional[str]) -> Optional[Credentials]:
    """The caller's own credentials from the two headers. None when neither is sent; ValueError (no value echoed) when only one is sent or
    a value is malformed."""
    username, key = (username or "").strip(), (key or "").strip()
    if not username and not key:
        return None
    if not username or not key:
        raise ValueError("send both X-Kaggle-Username and X-Kaggle-Key, or neither")
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("the Kaggle username may contain only letters, digits, underscore, dot and hyphen (at most 60 characters)")
    if not KEY_RE.fullmatch(key):
        raise ValueError("the Kaggle API key is malformed (printable characters without spaces, at most 200)")
    return Credentials(username, key)


def server_credentials() -> Optional[Credentials]:
    return Credentials(settings.KAGGLE_USERNAME, settings.KAGGLE_KEY) if settings.KAGGLE_USERNAME and settings.KAGGLE_KEY else None


def resolve(creds: Optional[Credentials]) -> Optional[Credentials]:
    """The caller's credentials when given, otherwise the server's, otherwise None."""
    return creds or server_credentials()


def configured() -> bool:
    """Whether the SERVER has its own credentials (a caller may still bring theirs)."""
    return server_credentials() is not None


def owner_of(notebook_id: str) -> str:
    return notebook_id.split("/", 1)[0]


def same_account(notebook_id: str, creds: Credentials) -> bool:
    return owner_of(notebook_id).lower() == creds.username.lower()


def _env(creds: Credentials) -> Dict[str, str]:
    return {**os.environ, "KAGGLE_USERNAME": creds.username, "KAGGLE_KEY": creds.key}


def _run(args: List[str], creds: Optional[Credentials]) -> str:
    if creds is None:
        raise KaggleError(NO_CREDENTIALS)
    try:
        p = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=TIMEOUT_S, env=_env(creds))
    except FileNotFoundError:
        raise KaggleError("the kaggle command line is not installed on the server (pip install kaggle)")
    except subprocess.TimeoutExpired:
        raise KaggleError("the kaggle command timed out")
    out = (p.stdout or "") + (p.stderr or "")
    out = out.replace(creds.key, "***")
    if p.returncode != 0:
        raise KaggleError(out.strip()[-400:] or f"kaggle exited with {p.returncode}")
    return out


def slug_for(snapshot_id: int, job_id: int) -> str:
    return f"datamend-fusion-s{snapshot_id}-j{job_id}"


def build_bundle(snapshot_content: str, snapshot_sha: str, dest: Path, slug: str, username: str) -> Path:
    """Write train.py (the trainer plus the embedded snapshot and a runner) and kernel-metadata.json into ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    blob = base64.b64encode(gzip.compress(snapshot_content.encode("utf-8"))).decode("ascii")
    runner = (
        "\n\n# ---- embedded snapshot and runner (generated by the platform) ----\n"
        "import base64 as _b64, gzip as _gz, json as _json, os as _os\n"
        f"_SNAPSHOT = {blob!r}\n"
        f"_SHA = {snapshot_sha!r}\n"
        "_text = _gz.decompress(_b64.b64decode(_SNAPSHOT)).decode('utf-8')\n"
        "_out = '/kaggle/working' if _os.path.isdir('/kaggle/working') else '.'\n"
        "try:\n"
        "    _res = {'ok': True, 'metrics': train(parse_snapshot(_text), snapshot_sha256=_SHA)}\n"
        "except NotEnoughLabels as _e:\n"
        "    _res = {'ok': False, 'error': str(_e)}\n"
        "open(_os.path.join(_out, 'result.json'), 'w').write(_json.dumps(_res))\n"
        "print(_json.dumps(_res)[:2000])\n")
    source = FUSION_SOURCE.read_text(encoding="utf-8").split('\nif __name__ == "__main__":')[0]       # the runner below replaces the command-line entry
    (dest / "train.py").write_text(source + runner, encoding="utf-8")
    meta = {"id": f"{username}/{slug}", "title": slug, "code_file": "train.py", "language": "python", "kernel_type": "script",
            "is_private": "true", "enable_gpu": "false", "enable_internet": "false", "dataset_sources": [], "competition_sources": [], "kernel_sources": []}
    (dest / "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return dest


def push(snapshot_content: str, snapshot_sha: str, slug: str, creds: Optional[Credentials]) -> str:
    """Build the bundle in a temporary folder and push it to the account in ``creds``; Kaggle starts the run. Returns the notebook id (user/slug)."""
    if creds is None:
        raise KaggleError(NO_CREDENTIALS)
    with tempfile.TemporaryDirectory(prefix="datamend_kaggle_") as d:
        build_bundle(snapshot_content, snapshot_sha, Path(d), slug, creds.username)
        _run(["kernels", "push", "-p", d], creds)
    return f"{creds.username}/{slug}"


def status(notebook_id: str, creds: Optional[Credentials]) -> str:
    """running | complete | failed, from ``kaggle kernels status`` (queued and running are both 'running')."""
    out = _run(["kernels", "status", notebook_id], creds).lower()
    m = re.search(r'status\s*"?([a-z_.]+)"?', out)
    word = (m.group(1) if m else out).replace("kernelworkerstatus.", "")
    if "complete" in word:
        return "complete"
    if any(w in word for w in ("error", "cancel", "fail")):
        return "failed"
    return "running"


def fetch_result(notebook_id: str, creds: Optional[Credentials]) -> Dict[str, Any]:
    """Download the notebook's output and return its result.json. Raises KaggleError when there is none."""
    with tempfile.TemporaryDirectory(prefix="datamend_kaggle_out_") as d:
        _run(["kernels", "output", notebook_id, "-p", d], creds)
        f = Path(d) / "result.json"
        if not f.exists():
            raise KaggleError("the notebook finished but wrote no result.json")
        return json.loads(f.read_text(encoding="utf-8"))
