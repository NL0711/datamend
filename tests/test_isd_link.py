"""A NOAA ISD hourly file arriving through a dataset link (file FORMAT only): unpacked and turned into an ordinary reading CSV. Generated data."""
import gzip

import pytest

from backend.app.validation import intake

ISD_CSV = (
    '"STATION","DATE","LATITUDE","LONGITUDE","AA1"\n'
    '"42182099999","2024-07-01T00:00:00","28.5","77.2","01,0050,1,5"\n'
    '"42182099999","2024-07-01T01:00:00","28.5","77.2","01,9999,9,5"\n'      # 9999 = missing: skipped, never zero
    '"42182099999","2024-07-01T02:00:00","28.5","77.2","01,0000,1,5"\n'      # a real zero stays a zero
)


def test_gzipped_isd_csv_becomes_a_reading_csv():
    name, content, is_isd = intake.normalize_link_file("421820-99999-2024.gz", gzip.compress(ISD_CSV.encode()))
    assert is_isd and name.endswith(".csv")
    lines = content.decode().strip().splitlines()
    assert lines[0] == "timestamp,station_id,accumulation"
    assert len(lines) == 3                      # the missing hour is skipped, not counted as rain
    assert lines[1].endswith(",5.0") and lines[2].endswith(",0.0")


def test_a_plain_csv_is_left_alone():
    raw = b"timestamp,station_id,accumulation\n2024-07-01T00:00:00Z,A,1\n"
    assert intake.normalize_link_file("x.csv", raw) == ("x.csv", raw, False)


def test_a_broken_gzip_is_refused_with_a_message():
    with pytest.raises(intake.LinkRejected):
        intake.normalize_link_file("x.gz", b"\x1f\x8bnot really gzip")
