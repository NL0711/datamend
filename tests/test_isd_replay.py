"""NOAA ISD India replay: the fixed-width parser, the capped fetch, the stored 'replay' run and the map's IMD stations.
Lines are GENERATED in ISD's documented format and the transport is mocked: no network, no NOAA data in the repository."""
import asyncio
import gzip

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from backend.app.api import replay as replay_api
from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.rainfall import isd_replay as isd
from backend.app.validation import runs as runs_svc
from backend.app.validation.models import Explanation, Review, ValidationCheckHit, ValidationResult, ValidationRun

TOKEN = "t" * 32
H = {"X-Admin-Token": TOKEN}
DELHI = "421820-99999"      # Safdarjung, in the committed IMD list
PUNE = "430630-99999"


def isd_line(sid: str, stamp: str, groups=(("24", "0000", "9", "1"),)) -> str:
    """One generated ISD record: the 105-character mandatory section, then 'ADD' and the AA precipitation groups."""
    usaf, wban = sid.split("-")
    head = f"0200{usaf}{wban}{stamp[:8]}{stamp[8:12]}4+28584+077200FM-12+0216VIDP "
    head = head.ljust(105)
    return head + "ADD" + "".join(f"AA{i}{p}{d}{c}{q}" for i, (p, d, c, q) in enumerate(groups, start=1)) + "REM"


@pytest_asyncio.fixture(autouse=True)
async def _clean(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    from backend.app.api import settings as settings_api
    settings_api._failures.clear()
    isd.JOB.__init__()
    async with async_session_factory() as s:
        for m in (Review, Explanation, ValidationCheckHit, ValidationResult, ValidationRun):
            await s.execute(delete(m))
        await s.commit()
    yield


# ---------------------------------------------------------------- parser
def test_a_generated_record_has_the_documented_layout():
    ln = isd_line(DELHI, "202507010300")
    assert len(ln) > isd.MANDATORY_LEN and ln[4:15] == "42182099999" and ln[15:23] == "20250701" and ln[23:27] == "0300"


def test_parse_line_reads_station_time_and_groups_and_never_raises():
    sid, when, groups = isd.parse_line(isd_line(DELHI, "202507010300", (("24", "0123", "3", "1"), ("06", "9999", "9", "9"))))
    assert sid == DELHI and when.isoformat() == "2025-07-01T03:00:00+00:00"
    assert groups == [(24, 12.3, "3", "1"), (6, None, "9", "9")]
    for bad in ("", "short", isd_line(DELHI, "20251301030")[:60], "0200" + "x" * 150):
        assert isd.parse_line(bad) is None


def test_daily_totals_keep_only_24_hour_reports_stamped_at_03_utc_and_never_turn_missing_into_zero():
    lines = [
        isd_line(DELHI, "202507010300", (("24", "0123", "3", "1"),)),       # kept: 12.3 mm
        isd_line(DELHI, "202507020300", (("24", "0000", "9", "1"),)),       # kept: a real zero
        isd_line(DELHI, "202507030300", (("24", "9999", "9", "9"),)),       # missing depth: skipped
        isd_line(DELHI, "202507040300", (("12", "0500", "3", "1"),)),       # 12-hour period: ignored
        isd_line(DELHI, "202507050900", (("24", "0900", "3", "1"),)),       # not stamped at 03 UTC: ignored
        "garbage line",
    ]
    out = isd.daily_totals(lines, {DELHI: (28.584, 77.2)})
    assert [(d.day.isoformat(), d.mm) for d in out] == [("2025-07-01", 12.3), ("2025-07-02", 0.0)]
    first = out[0]
    assert (first.source, first.station_id, first.complete, first.units_confirmed) == ("isd_replay", DELHI, True, True)
    assert (first.latitude, first.longitude) == (28.584, 77.2) and first.row_ref == 1 and out[1].row_ref == 2
    assert first.raw["isd_condition"] == "3" and first.raw["isd_quality"] == "1"       # the source's own codes are passed through


def test_the_better_quality_group_wins_and_a_tie_keeps_the_first():
    one_day = isd_line(DELHI, "202507010300", (("24", "0100", "3", "2"), ("24", "0200", "3", "1")))
    assert isd.daily_totals([one_day])[0].mm == 20.0
    tie = isd_line(DELHI, "202507010300", (("24", "0100", "3", "1"), ("24", "0200", "3", "5")))
    assert isd.daily_totals([tie])[0].mm == 10.0


def test_split_id_and_the_decompression_guard():
    assert isd.split_id(DELHI) == ("421820", "99999")
    for bad in ("421820", "42182-99999", "../../etc-passwd"):
        with pytest.raises(ValueError):
            isd.split_id(bad)
    assert isd.gunzip_capped(gzip.compress(b"abc")) == "abc"
    with pytest.raises(ValueError, match="safety limit"):
        isd.gunzip_capped(gzip.compress(b"x" * 5000), limit=100)


# ---------------------------------------------------------------- fetch and build (mocked transport)
def station_file(sid: str, n_days=5, other: str = None) -> bytes:
    lines = [isd_line(sid, f"2025070{d}0300", (("24", f"{d * 10:04d}", "3", "1"),)) for d in range(1, n_days + 1)]
    if other:
        lines.append(isd_line(other, "202507060300"))
    return gzip.compress(("\n".join(lines) + "\n").encode())


def transport(files: dict):
    def handler(req: httpx.Request):
        for sid, body in files.items():
            if f"/{sid}-2025.gz" in str(req.url):
                return httpx.Response(200, content=body)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_build_fetches_each_station_reports_failures_and_keeps_only_the_requested_station():
    t = transport({DELHI: station_file(DELHI, 5, other=PUNE)})
    res = await isd.build([DELHI, PUNE], 2025, t)
    assert [r.station_id for r in res.records] == [DELHI] * 5 and [r.row_ref for r in res.records] == [1, 2, 3, 4, 5]
    ok = {s["id"]: s for s in res.stations}
    assert ok[DELHI]["ok"] and ok[DELHI]["totals"] == 5 and ok[DELHI]["name"]
    assert not ok[PUNE]["ok"] and "404" in ok[PUNE]["error"]
    assert "not live" in res.note and "Resolution 40" in res.note


# ---------------------------------------------------------------- stored run, map, endpoints
@pytest.mark.asyncio
async def test_a_replay_is_stored_as_one_labelled_run_and_replaces_the_previous_one():
    res = await isd.build([DELHI], 2025, transport({DELHI: station_file(DELHI, 6)}))
    async with async_session_factory() as s:
        a = await runs_svc.run_replay(s, res.records, "first", {"note": isd.NOTE})
        b = await runs_svc.run_replay(s, res.records, "second", {"note": isd.NOTE})
        left = list((await s.execute(select(ValidationRun).where(ValidationRun.source == "replay"))).scalars())
    assert len(left) == 1 and left[0].label == "second" and a.label == "first"      # one replay run at a time (SQLite may reuse the id)
    assert (b.profile, b.status, b.n_rows, b.n_stations, b.synthetic) == ("daily", "completed", 6, 1, False)
    assert b.settings["replay"]["note"] == isd.NOTE


@pytest.mark.asyncio
async def test_replay_stations_appear_on_the_map_as_imd_stations_with_their_replay_rows(async_client: AsyncClient, monkeypatch):
    # ISD depths are tenths of a millimetre; the same 50.0 mm on five consecutive days is what the repeated-value check flags
    lines = [isd_line(DELHI, f"2025070{d}0300", (("24", "0500", "3", "1"),)) for d in range(1, 6)]
    t = transport({DELHI: gzip.compress("\n".join(lines).encode())})
    res = await isd.build([DELHI], 2025, t)
    async with async_session_factory() as s:
        await runs_svc.run_replay(s, res.records, "replay", {"note": isd.NOTE})
    body = (await async_client.get("/api/validation/stations")).json()
    st = {x["station_id"]: x for x in body["stations"]}[DELHI]
    assert st["position_source"] == "imd" and st["place"] and st["latitude"] is not None and st["longitude"] is not None
    assert (st["checked"], st["replay_rows"], st["synthetic_rows"]) == (5, 5, 0) and st["flagged"] >= 1 and "repeated_value" in st["top_checks"]
    assert body["positioned"] == 1


@pytest.mark.asyncio
async def test_status_is_open_but_starting_needs_the_admin_token_and_a_second_start_is_refused(async_client: AsyncClient, monkeypatch):
    calls = []

    async def fake_build(ids, year, transport=None, timeout=30.0):
        calls.append(list(ids))
        await asyncio.sleep(0.05)
        return await real_build([DELHI], year, globals()["transport"]({DELHI: station_file(DELHI, 4)}))

    real_build = isd.build
    monkeypatch.setattr(isd, "build", fake_build)
    idle = (await async_client.get("/api/validation/replay/isd")).json()
    assert idle["state"] == "idle" and idle["stored_run_id"] is None and "not live" in idle["note"]
    assert (await async_client.post("/api/validation/replay/isd")).status_code == 401
    assert (await async_client.post("/api/validation/replay/isd", headers=H)).status_code == 202
    assert (await async_client.post("/api/validation/replay/isd", headers=H)).status_code == 409
    await isd.JOB._task
    done = (await async_client.get("/api/validation/replay/isd")).json()
    assert done["state"] == "done" and done["run_id"] == done["stored_run_id"] and done["stations_ok"] == 1 and "4 daily totals" in done["message"]
    assert len(calls) == 1 and tuple(calls[0]) == tuple(isd.DEFAULT_STATIONS)


@pytest.mark.asyncio
async def test_a_failed_replay_ends_in_a_state_the_page_can_show(async_client: AsyncClient, monkeypatch):
    async def nothing(ids, year, transport=None, timeout=30.0):
        return isd.ReplayResult([], [{"id": DELHI, "name": "x", "ok": False, "totals": 0, "error": "HTTP 503"}], year, "now")
    monkeypatch.setattr(isd, "build", nothing)
    assert replay_api.start_job() is True
    await isd.JOB._task
    s = (await async_client.get("/api/validation/replay/isd")).json()
    assert s["state"] == "failed" and "no daily totals" in s["message"] and s["finished_at"] and s["stored_run_id"] is None


@pytest.mark.asyncio
async def test_start_at_boot_only_when_asked_and_not_when_a_replay_is_already_stored(monkeypatch):
    started = []
    monkeypatch.setattr(replay_api, "start_job", lambda transport=None: started.append(1) or True)
    monkeypatch.setattr(settings, "ISD_REPLAY_ON_START", False)
    await replay_api.start_replay_on_boot()
    assert started == []
    monkeypatch.setattr(settings, "ISD_REPLAY_ON_START", True)
    await replay_api.start_replay_on_boot()
    assert started == [1]
    res = await isd.build([DELHI], 2025, transport({DELHI: station_file(DELHI, 3)}))
    async with async_session_factory() as s:
        await runs_svc.run_replay(s, res.records, "stored", {})
    await replay_api.start_replay_on_boot()
    assert started == [1]


def test_custom_station_list_comes_from_the_setting(monkeypatch):
    monkeypatch.setattr(settings, "ISD_REPLAY_STATIONS", f" {DELHI} , {PUNE},")
    assert replay_api._ids() == [DELHI, PUNE]
    monkeypatch.setattr(settings, "ISD_REPLAY_STATIONS", "")
    assert tuple(replay_api._ids()) == tuple(isd.DEFAULT_STATIONS)
    assert all(i in {s["id"] for s in __import__("backend.app.places.imd", fromlist=["stations"]).stations()} for i in isd.DEFAULT_STATIONS)
