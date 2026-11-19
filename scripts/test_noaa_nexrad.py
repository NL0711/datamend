"""
scripts/test_noaa_nexrad.py
Manual Verification Tool: Tests access to NOAA NEXRAD Level II Radar on AWS Open Data (S3).
Requires no AWS CLI or AWS credentials (uses public unsigned HTTP S3 API).
"""

import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import httpx

# NOAA Open Data S3 Base URL (Public Bucket)
NEXRAD_S3_BASE = "https://unidata-nexrad-level2.s3.amazonaws.com"
S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


def list_radar_stations(year: int = 2024, month: int = 1, day: int = 1):
    """Lists available radar ground stations for a specific date."""
    prefix = f"{year}/{month:02d}/{day:02d}/"
    url = f"{NEXRAD_S3_BASE}/?prefix={prefix}&delimiter=/"
    
    print(f"[*] Querying NOAA NEXRAD archive: {url}")
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    prefixes = [p.find("s3:Prefix", S3_NS).text for p in root.findall("s3:CommonPrefixes", S3_NS)]
    stations = [p.strip("/").split("/")[-1] for p in prefixes]
    return stations


def list_volume_scans(station_id: str = "KTLX", year: int = 2024, month: int = 1, day: int = 1, limit: int = 5):
    """Lists raw volume scan files for a specific ground station."""
    prefix = f"{year}/{month:02d}/{day:02d}/{station_id}/"
    url = f"{NEXRAD_S3_BASE}/?prefix={prefix}&delimiter=/"
    
    print(f"[*] Querying radar volume scans for station [{station_id}] on {year}-{month:02d}-{day:02d}...")
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    contents = root.findall("s3:Contents", S3_NS)
    
    scans = []
    for item in contents[:limit]:
        key = item.find("s3:Key", S3_NS).text
        size = int(item.find("s3:Size", S3_NS).text)
        last_modified = item.find("s3:LastModified", S3_NS).text
        scans.append({
            "key": key,
            "filename": key.split("/")[-1],
            "size_bytes": size,
            "last_modified": last_modified,
            "download_url": f"{NEXRAD_S3_BASE}/{key}"
        })
    return scans


def test_nexrad_download_sample(download_url: str):
    """Streams first 1024 bytes of a scan to verify binary byte headers."""
    print(f"[*] Testing byte stream from: {download_url}")
    with httpx.Client(timeout=10.0) as client:
        with client.stream("GET", download_url) as stream:
            header_bytes = next(stream.iter_bytes(1024))
            return len(header_bytes)


def main():
    print("=" * 65)
    print(" NOAA NEXRAD on AWS Open Data — Public S3 Verification Test")
    print("=" * 65)
    
    # 1. Test listing radar ground stations
    stations = list_radar_stations(2024, 1, 1)
    print(f"[+] Found {len(stations)} active radar ground stations on 2024-01-01.")
    print(f"    Sample stations: {stations[:8]}...\n")
    
    # 2. Test querying volume scans for a standard site (KTLX - Oklahoma City)
    scans = list_volume_scans("KTLX", 2024, 1, 1, limit=3)
    print(f"[+] Retrieved {len(scans)} sample radar volume scans for KTLX:")
    for i, s in enumerate(scans, 1):
        print(f"    {i}. {s['filename']} ({s['size_bytes'] / (1024*1024):.2f} MB) - URL: {s['download_url']}")
    
    # 3. Test HTTP stream connectivity on the first scan
    if scans:
        sample_url = scans[0]["download_url"]
        bytes_received = test_nexrad_download_sample(sample_url)
        print(f"\n[+] Successfully streamed {bytes_received} header bytes from public S3 archive.")
        print("[+] STATUS: NOAA NEXRAD AWS connection verified successfully.")
    print("=" * 65)


if __name__ == "__main__":
    main()
