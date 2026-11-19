"""Input contract and input-integrity conformance suite (spec slice 3).

Each integrity check fires on a minimal generated case and stays silent on a clean one; each file-level problem rejects the upload.
Pass or fail only: this says nothing about recall or precision. All data here is generated.
"""
from datetime import datetime, timezone

import pytest

from backend.app.rainfall.weather_union import RainObservation
from backend.app.validation.adapters import reading_from_observation
from backend.app.validation.ingest import InputRejected, UploadOptions, parse_upload, sorted_for_scoring

HDR = "timestamp,station_id,accumulation\n"


def reading(rows, **kw):
    opts = dict(profile="reading", accumulation_mode="cumulative")
    opts.update(kw)
    return parse_upload((HDR + "\n".join(rows) + "\n").encode(), UploadOptions(**opts))


def daily(rows, header="day,station_id,mm\n", **kw):
    return parse_upload((header + "\n".join(rows) + "\n").encode(), UploadOptions(profile="daily", **kw))


def codes(p):
    return [[i.code for i in r.issues] for r in p.records]


CLEAN = ["2026-07-01T00:00:00Z,A,0.0", "2026-07-01T00:15:00Z,A,0.2", "2026-07-01T00:30:00Z,A,0.4"]


# ---------------------------------------------------------------- clean input stays silent
def test_clean_reading_file_has_no_issues():
    p = reading(CLEAN, interval_minutes=15)
    assert p.issue_counts == {} and p.not_run == [] and not p.out_of_order
    assert [r.row_ref for r in p.records] == [1, 2, 3]


def test_clean_daily_file_has_no_issues():
    p = daily(["2026-07-01,A,1.0", "2026-07-02,A,0.0", "2026-07-03,A,12.5"])
    assert p.issue_counts == {}


# ---------------------------------------------------------------- row-level checks fire and keep the row
def test_duplicate_timestamp_flags_every_row_of_the_group_and_keeps_them():
    p = reading([CLEAN[0], CLEAN[1], "2026-07-01T00:15:00Z,A,0.3", CLEAN[2]], interval_minutes=15)
    assert len(p.records) == 4
    assert codes(p) == [[], ["duplicate_timestamp"], ["duplicate_timestamp"], []]


def test_same_time_at_two_stations_is_not_a_duplicate():
    p = reading(["2026-07-01T00:00:00Z,A,0.0", "2026-07-01T00:00:00Z,B,0.0"], interval_minutes=15)
    assert p.issue_counts == {}


def test_out_of_order_is_flagged_reported_and_sorted_only_afterwards():
    p = reading(["2026-07-01T00:30:00Z,A,0.4", "2026-07-01T00:00:00Z,A,0.0", "2026-07-01T00:15:00Z,A,0.2"], interval_minutes=15)
    assert p.out_of_order is True
    assert [r.row_ref for r in p.records] == [1, 2, 3]                    # file order untouched
    assert codes(p) == [[], ["out_of_order"], ["out_of_order"]]
    assert [r.row_ref for r in sorted_for_scoring(p)] == [2, 3, 1]


def test_gap_needs_a_declared_interval_and_is_not_run_without_one():
    rows = ["2026-07-01T00:00:00Z,A,0.0", "2026-07-01T02:00:00Z,A,0.1"]
    p = reading(rows, interval_minutes=15)
    assert codes(p) == [[], ["gap"]]
    q = reading(rows)
    assert q.issue_counts == {} and q.not_run == [{"check": "gap", "reason": "no interval_minutes declared for this upload"}]


def test_daily_gap_and_duplicate_day():
    p = daily(["2026-07-01,A,1", "2026-07-04,A,1", "2026-07-04,A,2"])
    assert [sorted(c) for c in codes(p)] == [[], ["duplicate_day", "gap"], ["duplicate_day"]]


@pytest.mark.parametrize("cell,code", [("abc", "non_numeric"), ("nan", "non_numeric"), ("inf", "non_numeric"), ("", "missing_value"), ("-1.5", "negative_value")])
def test_bad_values_are_flagged_and_the_row_is_kept(cell, code):
    p = reading(CLEAN[:1] + [f"2026-07-01T00:15:00Z,A,{cell}"], interval_minutes=15)
    assert len(p.records) == 2 and codes(p)[1] == [code]
    assert p.records[1].raw["accumulation"] == cell                       # original row untouched
    if code == "negative_value":
        assert p.records[1].accumulation == -1.5                          # kept as given, never corrected


def test_row_with_unparseable_timestamp_is_kept_with_a_flag():
    p = reading(CLEAN[:2] + ["not-a-time,A,0.5"], interval_minutes=15)
    assert len(p.records) == 3 and codes(p)[2] == ["bad_timestamp"] and p.records[2].timestamp is None


# ---------------------------------------------------------------- file-level problems reject the whole upload
@pytest.mark.parametrize("content,opts,msg", [
    (b"", dict(profile="reading"), "empty"),
    (b"   \n", dict(profile="reading"), "empty"),
    (b"timestamp,station_id,accumulation\n", dict(profile="reading", accumulation_mode="cumulative"), "no data rows"),
    (b"timestamp,accumulation\n2026-07-01T00:00:00Z,1\n", dict(profile="reading", accumulation_mode="cumulative"), "station_id"),
    (b"timestamp,station_id\n2026-07-01T00:00:00Z,A\n", dict(profile="reading"), "accumulation"),
    (b"timestamp,station_id,accumulation\nx,A,1\ny,A,2\n", dict(profile="reading", accumulation_mode="cumulative"), "parses"),
    (b"day,station_id,mm\nx,A,1\n", dict(profile="daily"), "parses"),
    (b"day,station_id\n2026-07-01,A\n", dict(profile="daily"), "mm"),
    (b"timestamp,station_id,accumulation,unit\n2026-07-01T00:00:00Z,A,1,inch\n", dict(profile="reading", accumulation_mode="cumulative"), "unsupported unit"),
    (b"day,station_id,mm\n2026-07-01,A,1\n", dict(profile="reading"), "timestamp"),
    (b"\xff\xfe\x00bad", dict(profile="reading"), "UTF-8"),
    (b"{not json", dict(profile="reading", fmt="json"), "JSON"),
    (b"[1,2]", dict(profile="reading", fmt="json"), "list of row objects"),
    (b"x", dict(profile="reading", fmt="parquet"), "NOT IMPLEMENTED"),
    (b"x", dict(profile="weekly"), "profile"),
])
def test_file_level_problems_reject(content, opts, msg):
    with pytest.raises(InputRejected, match=msg):
        parse_upload(content, UploadOptions(**opts))


def test_accumulation_column_without_a_declared_mode_is_rejected():
    with pytest.raises(InputRejected, match="accumulation_mode"):
        parse_upload((HDR + CLEAN[0] + "\n").encode(), UploadOptions(profile="reading"))


def test_intensity_only_file_needs_no_mode():
    p = parse_upload(b"timestamp,station_id,intensity\n2026-07-01T00:00:00Z,A,3.0\n", UploadOptions(profile="reading"))
    assert p.records[0].intensity == 3.0 and p.records[0].accumulation_mode is None


def test_oversize_file_is_rejected():
    with pytest.raises(InputRejected, match="larger than"):
        parse_upload(b"x" * (10 * 1024 * 1024 + 1), UploadOptions(profile="reading"))


# ---------------------------------------------------------------- timestamps and zones
def test_timestamp_without_zone_is_rejected_unless_one_zone_is_declared():
    rows = ["2026-07-01T05:30:00,A,0.0"]
    with pytest.raises(InputRejected, match="time zone"):
        reading(rows)
    p = reading(rows, timezone="+05:30")
    assert p.records[0].timestamp == datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)


def test_offsets_are_converted_to_utc_and_unknown_zone_is_rejected():
    p = reading(["2026-07-01T05:30:00+05:30,A,0.0"])
    assert p.records[0].timestamp == datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(InputRejected, match="unknown time zone"):
        reading(["2026-07-01T05:30:00,A,0.0"], timezone="Not/AZone")


# ---------------------------------------------------------------- aliases, JSON, metadata, record fields
def test_header_aliases_are_reported_back():
    p = daily(["2026-07-01,A,1.0"], header="Date,Station,Rain_MM\n")
    assert p.renamed == {"Date": "day", "Station": "station_id", "Rain_MM": "mm"}
    assert p.records[0].mm == 1.0


def test_two_columns_for_one_field_is_rejected():
    with pytest.raises(InputRejected, match="map to"):
        daily(["2026-07-01,A,1.0,2.0"], header="day,station_id,mm,rain_mm\n")


def test_json_input_and_optional_coordinates():
    body = b'{"rows":[{"day":"2026-07-01","station_id":"A","mm":2.5,"lat":19.0,"lon":72.8}]}'
    p = parse_upload(body, UploadOptions(profile="daily", fmt="json"))
    r = p.records[0]
    assert (r.mm, r.latitude, r.longitude) == (2.5, 19.0, 72.8) and r.source == "upload" and r.units_confirmed is True


def test_reading_record_fields_and_untouched_raw_row():
    p = reading(CLEAN[1:2], interval_minutes=15)
    r = p.records[0]
    assert r.source == "upload" and r.time_basis == "observed" and r.accumulation_mode == "cumulative"
    assert r.raw == {"timestamp": "2026-07-01T00:15:00Z", "station_id": "A", "accumulation": "0.2"}


# ---------------------------------------------------------------- one record for the live source too
def test_weather_union_observation_becomes_a_received_unconfirmed_reading():
    t = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)
    ok = reading_from_observation(RainObservation("S1", t, 2, 0.0, 5.0, "OK", {"x": 1}), "cumulative", 7)
    assert (ok.source, ok.time_basis, ok.units_confirmed, ok.accumulation_mode, ok.row_ref) == ("weather_union", "received", False, "cumulative", 7)
    none = reading_from_observation(RainObservation("S1", t, None, None, None, "NO_RAIN_FIELDS", {}), "cumulative", 8)
    assert none.accumulation is None and none.intensity is None and none.accumulation_mode is None
