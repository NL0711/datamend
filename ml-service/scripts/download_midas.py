"""Download UK MIDAS Open daily rainfall from the CEDA archive.

Standard library only. The CEDA access token is read from the CEDA_TOKEN
environment variable, or from a `.env` file (see `ml-service/.env.example`).
The token is never written to disk or printed.

Setup on a new machine:
  1. Create a free CEDA account and generate a token at
     https://services.ceda.ac.uk/account/token/
  2. Copy `ml-service/.env.example` to `ml-service/.env` and paste the token in,
     or set CEDA_TOKEN in the shell.
  3. Run, from `ml-service/`:
       python scripts/download_midas.py --check
       python scripts/download_midas.py --county devon --dry-run
       python scripts/download_midas.py --county devon cornwall

Modes:
  pairs (default)  every qc-version-0 file (original records that QC changed)
                   plus the qc-version-1 file for the same station-year.
                   Enough to count what QC changed.
  full             every qc-version-0 and qc-version-1 file. Needed to grid
                   the stations.

Files that already exist are skipped, so an interrupted run can be restarted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

ARCHIVE = "https://dap.ceda.ac.uk/badc/ukmo-midas-open/data/uk-daily-rain-obs/"
TOKEN_CHECK = "https://dap.ceda.ac.uk/badc/ARCHIVE_INFO/ACCESS_TEST/RESTRICTED/TOKEN_CHECK"
TOKEN_PAGE = "https://services.ceda.ac.uk/account/token/"
ML_SERVICE = Path(__file__).resolve().parent.parent
HREF = re.compile(r'href="([^"#?]+)"', re.IGNORECASE)
YEAR = re.compile(r"_qcv-[01]_(\d{4})\.csv$")


class DownloadError(RuntimeError):
    pass


def read_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines; ignores blanks and comments. No interpolation."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def setting(name: str, env_file: Path | None) -> str:
    """A setting from the environment first, then from .env files."""
    value = os.environ.get(name, "").strip()
    if not value:
        candidates = [env_file] if env_file else [Path.cwd() / ".env", ML_SERVICE / ".env"]
        for path in candidates:
            value = read_env_file(path).get(name, "").strip()
            if value:
                break
    return value


def load_token(env_file: Path | None) -> str:
    token = setting("CEDA_TOKEN", env_file)
    if not token:
        raise DownloadError(
            "No CEDA access token found. Set CEDA_TOKEN in the shell, or copy "
            f"ml-service/.env.example to ml-service/.env and fill it in. Get a token at {TOKEN_PAGE}"
        )
    return token


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # CEDA answers an unauthenticated file request with a redirect to its login
    # page. Following it would save the login page as if it were data.
    def redirect_request(self, *args, **kwargs):
        return None


class Ceda:
    def __init__(self, token: str, retries: int = 5):
        self._headers = {"Authorization": f"Bearer {token}", "User-Agent": "midas-open-downloader"}
        self._opener = urllib.request.build_opener(_NoRedirect)
        self._retries = retries

    def get(self, url: str) -> tuple[int, str, bytes]:
        """Returns (status, content type, body). Retries on transient failures."""
        for attempt in range(self._retries):
            try:
                req = urllib.request.Request(url, headers=self._headers)
                with self._opener.open(req, timeout=120) as resp:
                    return resp.status, resp.headers.get("Content-Type", ""), resp.read()
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < self._retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return e.code, e.headers.get("Content-Type", "") if e.headers else "", b""
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt == self._retries - 1:
                    raise DownloadError(f"network error for {url}: {e}") from e
                time.sleep(2 ** attempt)
        raise DownloadError(f"gave up on {url}")

    def check_token(self) -> None:
        status, ctype, body = self.get(TOKEN_CHECK)
        if status != 200 or "text/html" in ctype:
            raise DownloadError(
                f"CEDA rejected the access token (HTTP {status}). Tokens expire after a few days; "
                f"generate a new one at {TOKEN_PAGE}"
            )

    def listdir(self, url: str) -> list[str]:
        status, _, body = self.get(url)
        if status == 404:
            return []
        if status != 200:
            raise DownloadError(f"cannot list {url}: HTTP {status}")
        names = set()
        for href in HREF.findall(body.decode("utf-8", "replace")):
            full = urljoin(url, href)
            if full.startswith(url) and full.rstrip("/") != url.rstrip("/"):
                names.add(full[len(url):])
        return sorted(names)

    def fetch(self, url: str, dest: Path) -> str:
        if dest.is_file() and dest.stat().st_size > 0:
            return "skipped"
        status, ctype, body = self.get(url)
        head = body[:200].lstrip().lower()
        if status != 200 or "text/html" in ctype or head.startswith((b"<!doctype", b"<html")):
            raise DownloadError(f"not a data file (HTTP {status}, {ctype or 'no content type'}): {url}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        tmp.write_bytes(body)
        tmp.replace(dest)
        return "downloaded"


def plan_county(ceda: Ceda, base: str, county: str, mode: str, workers: int) -> tuple[list[str], dict]:
    county_url = f"{base}{county}/"
    stations = [s for s in ceda.listdir(county_url) if s.endswith("/")]
    if not stations:
        raise DownloadError(f"no stations found for county '{county}' at {county_url}")

    def scan(station: str):
        top = ceda.listdir(county_url + station)
        q0 = ceda.listdir(county_url + station + "qc-version-0/") if "qc-version-0/" in top else []
        q1 = ceda.listdir(county_url + station + "qc-version-1/") if "qc-version-1/" in top else []
        return station, [t for t in top if t.endswith(".csv")], q0, q1

    with ThreadPoolExecutor(workers) as pool:
        scans = list(pool.map(scan, stations))

    urls: list[str] = []
    n_q0 = n_q1 = n_q1_all = 0
    for station, capability, q0, q1 in scans:
        urls += [county_url + station + c for c in capability]
        n_q1_all += len(q1)
        years_q0 = {m.group(1) for f in q0 if (m := YEAR.search(f))}
        for f in q0:
            if YEAR.search(f):
                urls.append(county_url + station + "qc-version-0/" + f)
                n_q0 += 1
        for f in q1:
            m = YEAR.search(f)
            if m and (mode == "full" or m.group(1) in years_q0):
                urls.append(county_url + station + "qc-version-1/" + f)
                n_q1 += 1
    summary = {
        "county": county, "stations": len(stations),
        "qc_version_0_files": n_q0, "qc_version_1_files_selected": n_q1,
        "qc_version_1_files_available": n_q1_all, "files": len(urls),
    }
    return urls, summary


def default_out(env_file: Path | None) -> Path:
    data_dir = setting("DATAMEND_DATA_DIR", env_file)
    return (Path(data_dir) if data_dir else ML_SERVICE / "data") / "midas-open" / "uk-daily-rain-obs"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--county", nargs="+", help="county folder names on CEDA, e.g. devon cornwall")
    p.add_argument("--mode", choices=["pairs", "full"], default="pairs")
    p.add_argument("--version", default="202607", help="dataset version (default: 202607)")
    p.add_argument("--out", type=Path, default=None,
                   help="output folder (default: $DATAMEND_DATA_DIR/midas-open/uk-daily-rain-obs, "
                        "else ml-service/data/midas-open/uk-daily-rain-obs)")
    p.add_argument("--env-file", type=Path, default=None, help="read CEDA_TOKEN from this file")
    p.add_argument("--check", action="store_true", help="only test the token, then exit")
    p.add_argument("--dry-run", action="store_true", help="count files without downloading")
    p.add_argument("--workers", type=int, default=4, help="parallel requests (default 4; be polite)")
    a = p.parse_args(argv)

    try:
        ceda = Ceda(load_token(a.env_file))
        ceda.check_token()
        print("CEDA token accepted.")
        if a.check:
            return 0
        if not a.county:
            p.error("--county is required unless --check is given")

        base = f"{ARCHIVE}dataset-version-{a.version}/"
        out = (a.out or default_out(a.env_file)) / f"dataset-version-{a.version}"
        urls = [base + "00README_catalogue_and_licence.txt"]
        summaries = []
        for county in a.county:
            county_urls, summary = plan_county(ceda, base, county.lower(), a.mode, a.workers)
            urls += county_urls
            summaries.append(summary)
            print(json.dumps(summary))
        print(f"{len(urls)} files -> {out}")
        if a.dry_run:
            return 0

        counts = {"downloaded": 0, "skipped": 0, "failed": 0}

        def job(url: str) -> str:
            try:
                return ceda.fetch(url, out.joinpath(*url[len(base):].split("/")))
            except DownloadError as e:
                return f"failed: {e}"

        with ThreadPoolExecutor(a.workers) as pool:
            for i, status in enumerate(pool.map(job, urls), 1):
                key = status.split(":")[0]
                counts[key] += 1
                if key == "failed" and counts["failed"] <= 10:
                    print(status, file=sys.stderr)
                if i % 500 == 0:
                    print(f"{i}/{len(urls)} {counts}", flush=True)

        out.mkdir(parents=True, exist_ok=True)
        record = {"version": a.version, "mode": a.mode, "counties": summaries, "result": counts}
        (out / "download_summary.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
        print(f"done {counts}")
        return 1 if counts["failed"] else 0
    except DownloadError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
