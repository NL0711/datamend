"""Build the Weather Union station catalogue CSV from Zomato's published locality list.

Source list: https://b.zmtcdn.com/data/file_assets/65fa362da3aa560a92f0b8aeec0dfda31713163042.pdf
("Live Weather - A Zomato Giveback"; columns cityName, localityName, localityId, latitude, longitude, device_type).

Usage (pdftotext comes with poppler):
    pdftotext -layout stations.pdf stations.txt
    python scripts/build_weather_union_catalog.py stations.txt backend/app/rainfall/data/weather_union_stations.csv

Output columns: locality_id, city, place, latitude, longitude, device_type (1 = automated weather system, 2 = rain gauge system).
The PDF text sometimes separates city and locality by one space only, so `place` keeps the full "city locality" text and
`city` is matched against the cities named in the list.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Dict, List

# Cities named in the published list (checked 2026-11-19). Longest match wins.
CITIES = [
    "Delhi NCR", "Ahmedabad", "Amritsar", "Bengaluru", "Bhopal", "Bhubaneswar", "Chandigarh", "Chennai", "Coimbatore",
    "Goa", "Guwahati", "Hyderabad", "Jaipur", "Jalandhar", "Jammu", "Kochi", "Kolkata", "Lucknow", "Ludhiana",
    "Mangalore", "Mumbai", "Mysore", "Nagpur", "Pune", "Raipur", "Surat", "Trivandrum", "Vadodara", "Vijayawada",
    "Visakhapatnam",
]

ROW = re.compile(
    r"^(?P<place>\S.*?)\s+(?P<id>ZWL\d+)\s+(?P<lat>-?\d+(?:\.\d+)?)\s+(?P<lon>-?\d+(?:\.\d+)?)\s+(?P<dev>\d)\s*-"
)


def parse_catalog(text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen = set()
    for line in text.splitlines():
        m = ROW.match(line.strip())
        if not m or m["id"] in seen:
            continue
        place = re.sub(r"\s+", " ", m["place"]).strip()
        city = next((c for c in sorted(CITIES, key=len, reverse=True) if place.lower().startswith(c.lower())), "")
        lat, lon = float(m["lat"]), float(m["lon"])
        if not (6.0 <= lat <= 38.0 and 66.0 <= lon <= 100.0):
            raise ValueError(f"{m['id']} has coordinates outside India: {lat}, {lon}")
        if m["dev"] not in ("1", "2"):
            raise ValueError(f"{m['id']} has unknown device_type {m['dev']}")
        seen.add(m["id"])
        rows.append({"locality_id": m["id"], "city": city, "place": place, "latitude": f"{lat:.6f}",
                     "longitude": f"{lon:.6f}", "device_type": m["dev"]})
    if not rows:
        raise ValueError("no station rows found; was the input made with `pdftotext -layout`?")
    return rows


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    rows = parse_catalog(Path(argv[1]).read_text(encoding="utf8"))
    out = Path(argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=["locality_id", "city", "place", "latitude", "longitude", "device_type"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} stations to {out} ({sum(r['device_type'] == '2' for r in rows)} rain gauges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
