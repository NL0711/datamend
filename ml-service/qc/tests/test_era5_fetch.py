"""CDS download logic (qc/era5_fetch.py) with a fake client: no network, no credentials."""

import threading
from pathlib import Path

import pytest

from qc.era5_fetch import AREA, VARIABLES, build_request, fetch_and_convert, fetch_year


class FakeClient:
    def __init__(self, too_large_for_whole_year=False, fail_years=(), flaky=0):
        self.calls, self.too_large, self.fail_years, self.flaky = [], too_large_for_whole_year, set(fail_years), flaky
        self.lock = threading.Lock()

    def retrieve(self, dataset, request, target):
        with self.lock:
            self.calls.append((dataset, request, Path(target).name))
            n_calls = len(self.calls)
        year = int(request["year"][0])
        if year in self.fail_years:
            raise RuntimeError("boom 500")
        if self.too_large and len(request["month"]) == 12:
            raise RuntimeError("the request is too large: cost limits exceeded")
        if self.flaky and n_calls <= self.flaky:
            raise ConnectionError("temporary")
        Path(target).write_bytes(b"data")


def test_request_matches_the_rf25_grid_and_asks_for_every_hour():
    r = build_request(2016, range(1, 13), "grib")
    assert r["variable"] == VARIABLES == ["2m_temperature", "2m_dewpoint_temperature", "surface_pressure"]
    assert r["area"] == AREA == [38.5, 66.5, 6.5, 100.0]
    assert len(r["time"]) == 24 and len(r["month"]) == 12 and len(r["day"]) == 31 and r["year"] == ["2016"]
    assert r["data_format"] == "grib" and r["download_format"] == "unarchived" and r["product_type"] == ["reanalysis"]
    assert len(build_request(2015, [2], "netcdf")["day"]) == 28 and len(build_request(2016, [2], "grib")["day"]) == 29


def test_one_request_per_year_and_existing_files_are_not_downloaded_again(tmp_path):
    c = FakeClient()
    files = fetch_year(c, tmp_path, 2016, "grib", wait=0)
    assert [f.name for f in files] == ["era5_single_2016.grib"] and len(c.calls) == 1
    assert c.calls[0][0] == "reanalysis-era5-single-levels"
    fetch_year(c, tmp_path, 2016, "grib", wait=0)
    assert len(c.calls) == 1                                                      # already there
    assert fetch_year(FakeClient(), tmp_path, 2017, "netcdf", wait=0)[0].suffix == ".nc"


def test_a_request_that_is_too_large_is_split_into_months(tmp_path):
    c = FakeClient(too_large_for_whole_year=True)
    files = fetch_year(c, tmp_path, 2016, "grib", wait=0)
    assert len(files) == 12 and files[0].name == "era5_single_2016_01.grib"
    assert len(c.calls) == 13 and [len(x[1]["month"]) for x in c.calls[1:]] == [1] * 12      # one refused, twelve monthly
    assert not list(tmp_path.glob("*.part"))


def test_transient_errors_are_retried_and_real_failures_surface(tmp_path):
    c = FakeClient(flaky=2)
    assert fetch_year(c, tmp_path, 2016, "grib", retries=3, wait=0)[0].is_file() and len(c.calls) == 3
    with pytest.raises(RuntimeError, match="boom"):
        fetch_year(FakeClient(fail_years=[2016]), tmp_path / "x", 2016, "grib", retries=1, wait=0)


def test_years_are_converted_as_they_arrive_and_one_failure_does_not_stop_the_rest(tmp_path):
    converted = []
    status = fetch_and_convert(lambda: FakeClient(fail_years=[2014]), [2013, 2014, 2015, 2016], tmp_path, converted.append,
                               workers=2, retries=0, wait=0, skip=lambda y: y == 2016)
    assert status == {2013: "done", 2014: "failed: download: boom 500", 2015: "done", 2016: "skipped"}
    assert sorted(converted) == [2013, 2015]
    # a conversion error is reported against its year too
    def bad(y):
        raise ValueError("incomplete year")
    status = fetch_and_convert(lambda: FakeClient(), [2020], tmp_path / "y", bad, workers=1, wait=0)
    assert status == {2020: "failed: convert: incomplete year"}
