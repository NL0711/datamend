"""Download IMD's sub-division boundary file and record where it came from. The file is NOT committed to the repository.

Usage (from ml-service/):
    python scripts/fetch_imd_regions.py            # writes data/regions/sd_boundary_rainfall.json and its provenance file

IMD publishes the file at https://mausam.imd.gov.in/imd_latest/contents/district_shapefiles/sd_boundary_rainfall.json. It states no licence and no
coordinate system; ``qc.imd_regions.acceptance_known_points`` checks that it is in degrees. Do not publish maps derived from it until IMD's
terms are known. The provenance file stores the URL, size, SHA-256, the server's Last-Modified header and the fetch date.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://mausam.imd.gov.in/imd_latest/contents/district_shapefiles/sd_boundary_rainfall.json"
ROOT = Path(__file__).resolve().parents[1]


def default_dir() -> Path:
    base = os.environ.get("DATAMEND_DATA_DIR")
    return (Path(base) if base else ROOT / "data") / "regions"


def fetch(dest: Path, url: str = URL) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "datamend-research/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        last_modified = r.headers.get("Last-Modified")
    d = json.loads(body.decode("utf-8"))
    n = len(d.get("features", []))
    if n != 36:
        raise ValueError(f"expected 36 sub-division features, the file has {n}; refusing to keep it")
    (dest / "sd_boundary_rainfall.json").write_bytes(body)
    prov = {"url": url, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "last_modified": last_modified,
            "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "features": n,
            "licence": "not stated by IMD", "crs": "not stated by IMD (checked as degrees by qc.imd_regions.acceptance_known_points)"}
    (dest / "sd_boundary_rainfall.provenance.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
    return prov


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dest", default=None, help="folder to write to (default: <data dir>/regions)")
    a = ap.parse_args(argv)
    try:
        prov = fetch(Path(a.dest) if a.dest else default_dir())
    except Exception as e:                                           # network and parse errors come in many types
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(prov, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
