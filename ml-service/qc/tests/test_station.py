"""Station lane tests on generated ISD-format lines (no real ISD data)."""
from datetime import date, timedelta

import numpy as np
import pytest

from qc.station import DailyTotal, StationScorer, daily_totals, parse_line, replay


def line(day: str, hhmm: str, groups: str, station: str = "42182099999") -> str:
    head = "0100" + station + day + hhmm
    return head.ljust(105, "9") + groups


def test_parse_line_reads_groups_and_missing():
    rec = parse_line(line("20220715", "0300", "AA124" "0123" "3" "1" "AA106" "9999" "9" "9"))
    assert rec is not None
    station, when, groups = rec
    assert station == "42182099999" and when.hour == 3
    assert groups[0] == (24, 12.3, "3", "1")
    assert groups[1] == (6, None, "9", "9")


def test_malformed_lines_are_skipped_not_raised():
    assert parse_line("short") is None
    assert parse_line(line("20221345", "0300", "")) is None


def test_daily_totals_only_24h_at_03utc_and_missing_skipped():
    lines = [
        line("20220715", "0300", "AA1240123" "31"),      # kept: 12.3 mm
        line("20220716", "0300", "AA1060050" "31"),      # 6-hour period: ignored
        line("20220717", "0900", "AA1240100" "31"),      # not the 03 UTC stamp: ignored
        line("20220718", "0300", "AA1249999" "91"),      # missing depth: skipped, not zero
        line("20220719", "0300", "AA1240000" "31"),      # genuine zero kept
    ]
    out = daily_totals(lines)
    assert [(d.day, d.mm) for d in out] == [(date(2022, 7, 15), 12.3), (date(2022, 7, 19), 0.0)]


def test_good_quality_beats_suspect_for_same_day():
    lines = [line("20220715", "0300", "AA1240500" "32"), line("20220715", "0300", "AA1240100" "31")]
    out = daily_totals(lines)
    assert len(out) == 1 and out[0].mm == 10.0 and out[0].quality == "1"


def _series(n=2200, seed=0):
    rng = np.random.default_rng(seed)
    d0 = date(2019, 1, 1)
    out = []
    for i in range(n):
        day = d0 + timedelta(days=i)
        wet = rng.random() < 0.4
        mm = round(float(rng.gamma(2.0, 5.0)), 1) if wet else 0.0
        out.append(DailyTotal("S1", day, mm, "1", "3"))
    return out


def test_scorer_is_causal_and_flags_extreme_and_impossible():
    s = _series()
    base = [StationScorer()]
    sc = base[0]
    scores = [sc.score(t) for t in s]
    # same prefix gives same scores whatever comes later
    sc2 = StationScorer()
    again = [sc2.score(t) for t in s[:400]]
    assert [x.score for x in again] == [x.score for x in scores[:400]]
    # an absurd but physically possible total late in the record scores high; an impossible one hits the rules
    extreme = sc.score(DailyTotal("S1", s[-1].day + timedelta(days=1), 400.0, "1", "3"))
    assert extreme.climatology > 4.0 and extreme.n_history_wet >= 30
    bad = sc.score(DailyTotal("S1", s[-1].day + timedelta(days=2), 5000.0, "1", "3"))
    assert bad.rules == 1.0 and bad.score >= 10.0
    # typical days stay low
    assert np.median([x.score for x in scores[1000:]]) < 1.0


def test_no_history_means_no_climatology_judgement():
    sc = StationScorer()
    r = sc.score(DailyTotal("S1", date(2022, 7, 1), 300.0, "1", "3"))
    assert r.climatology == 0.0 and r.n_history_wet == 0


def test_repeat_run_reaches_one():
    sc = StationScorer(repeat_days=3)
    d0 = date(2022, 7, 1)
    r = [sc.score(DailyTotal("S1", d0 + timedelta(days=i), 7.5, "1", "3")) for i in range(3)]
    assert [x.repeat for x in r] == [0.0, 0.5, 1.0]


def test_days_must_increase():
    sc = StationScorer()
    sc.score(DailyTotal("S1", date(2022, 7, 2), 1.0, "1", "3"))
    with pytest.raises(ValueError):
        sc.score(DailyTotal("S1", date(2022, 7, 2), 1.0, "1", "3"))


def test_replay_interleaves_stations_in_time_order():
    a = [DailyTotal("A", date(2022, 7, i), 1.0, "1", "3") for i in (1, 2)]
    b = [DailyTotal("B", date(2022, 7, i), 2.0, "1", "3") for i in (1, 2)]
    order = [(t.day.day, t.station) for t, _ in replay(a + b)]
    assert order == [(1, "A"), (1, "B"), (2, "A"), (2, "B")]
