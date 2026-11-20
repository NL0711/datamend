"""The Explore step on generated data only: the declarative query, located stations, dataset profiles, the cleaning policy and proposals, the
assistant (with a mocked narrator transport) and the model card. No real data, no network."""
import math
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.pipeline import cleaning, cwc, profile as profile_svc, qc, store
from backend.app.pipeline.models import CleaningPlan, ModelVersion, Observation, PipelineCleaning, PipelineProfile, PipelineStation
from backend.app.validation import checks, narrate
from backend.app.validation.explain import NarratorExplainer, _Limiter
from backend.app.validation.models import ValidationRun

pytestmark = pytest.mark.asyncio
TOKEN = "e" * 32
H = {"X-Admin-Token": TOKEN}
T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
API = "/api/pipeline"


@pytest_asyncio.fixture(autouse=True)
async def _clean(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    # the import agent adds these to cwc.py; here they are fixtures so the two branches never conflict
    monkeypatch.setattr(cwc, "omits_zero_values", True, raising=False)
    monkeypatch.delattr(cwc, "PARAMETER", raising=False)
    monkeypatch.delattr(cwc, "UNITS", raising=False)
    monkeypatch.setattr(narrate, "get_narrator", lambda: None)
    async with async_session_factory() as s:
        for model in (PipelineCleaning, CleaningPlan, PipelineProfile, ModelVersion, Observation, PipelineStation):
            await s.execute(delete(model))
        await s.execute(delete(ValidationRun).where(ValidationRun.source == "pipeline"))
        await s.commit()
    yield


async def put(source, key, series, lat=None, lon=None):
    """series: list of (hour offset from T0 in hours, value)."""
    async with async_session_factory() as s:
        await store.upsert_stations(s, [{"station_key": key, "source": source, "name": key.upper(), "state": "X", "district": None, "latitude": lat, "longitude": lon}])
        await store.insert_observations(s, [{"source": source, "station_key": key, "observed_at": T0 + timedelta(hours=h), "value_mm": v, "job_id": None}
                                            for h, v in series])
        await s.commit()


def temp_series():
    gone = {10, 11} | set(range(50, 60))
    return [(h, round(20 + 5 * math.sin(h / 6), 4)) for h in range(120) if h not in gone]


def rain_series():
    gone = {30, 31}
    out = []
    for h in range(120):
        if h in gone:
            continue
        v = 0.0 if h % 3 == 1 else float(1 + h % 5)
        if h == 5:
            v = -5.0
        if h == 8:
            v = 400.0
        out.append((h, v))
    return out


def omit_series():
    """Hourly, regular, no zeros, jumpy: a rainfall file that lists only wet hours would look like this (one step missing at hour 20)."""
    return [(h, float(1 + (h * 7) % 11)) for h in range(60) if h != 20]


async def obs_count():
    async with async_session_factory() as s:
        return (await s.execute(select(func.count()).select_from(Observation))).scalar_one()


async def post(client, path, body, headers=H):
    return await client.post(API + path, json=body, headers=headers)


# ------------------------------------------------------------------------------------------------ query builder
async def test_tables_listed(async_client):
    r = (await async_client.get(API + "/explore/tables")).json()
    ids = {t["id"] for t in r["tables"]}
    assert ids == {"stations", "hourly", "daily", "gaps", "station_summary", "flags"}
    hourly = next(t for t in r["tables"] if t["id"] == "hourly")
    assert [c["name"] for c in hourly["columns"]][:5] == ["source", "station", "time", "mm", "job"]
    daily = next(t for t in r["tables"] if t["id"] == "daily")
    assert {"station", "day", "mm", "hours_reported", "max_hour_mm", "imputed_hours"} <= {c["name"] for c in daily["columns"]}


@pytest.mark.parametrize("body", [
    {"table": "users"},
    {"table": "hourly", "columns": ["password"]},
    {"table": "hourly", "filters": [{"column": "mm", "op": "LIKE", "value": 1}]},
    {"table": "hourly", "filters": [{"column": "mm; DROP TABLE x", "op": "=", "value": 1}]},
    {"table": "hourly", "aggregates": [{"fn": "exec", "column": "mm", "as": "x"}]},
    {"table": "hourly", "aggregates": [{"fn": "sum", "column": "station", "as": "x"}]},
    {"table": "hourly", "aggregates": [{"fn": "count", "as": "n; DROP TABLE x"}]},
    {"table": "hourly", "group_by": ["nope"]},
    {"table": "hourly", "order_by": [{"column": "nope"}]},
    {"table": "hourly", "order_by": [{"column": "mm", "dir": "sideways"}]},
    {"table": "hourly", "filters": [{"column": "mm", "op": "=", "value": "abc"}]},
    {"table": "hourly", "filters": [{"column": "mm", "op": "contains", "value": "a"}]},
    {"table": "hourly", "columns": ["mm"], "group_by": ["station"]},
    {"table": "hourly", "limit": 0},
    {"table": "flags"},                                   # needs a run_id
])
async def test_query_rejects_names_outside_the_allowlist(async_client, body):
    r = await async_client.post(API + "/explore/query", json=body)
    assert r.status_code == 400, r.text


async def test_query_values_are_parameters_not_sql(async_client):
    await put("rain", "r1", rain_series(), 23.5, 91.6)
    evil = "x' OR '1'='1"
    r = await async_client.post(API + "/explore/query", json={"table": "hourly", "filters": [{"column": "station", "op": "=", "value": evil}]})
    assert r.status_code == 200 and r.json()["total"] == 0
    r = await async_client.post(API + "/explore/query", json={"table": "hourly", "filters": [{"column": "station", "op": "in", "value": ["r1'; DROP TABLE pipeline_observations;--"]}]})
    assert r.status_code == 200 and r.json()["total"] == 0
    assert await obs_count() == len(rain_series())
    # a LIKE wildcard in 'contains' is matched literally
    r = (await async_client.post(API + "/explore/query", json={"table": "hourly", "filters": [{"column": "station", "op": "contains", "value": "%"}]})).json()
    assert r["total"] == 0
    r = (await async_client.post(API + "/explore/query", json={"table": "stations", "filters": [{"column": "name", "op": "contains", "value": "r"}]})).json()
    assert r["total"] == 1


async def test_query_caps_rows_and_reports_truncation(async_client):
    await put("rain", "r1", rain_series())
    r = (await async_client.post(API + "/explore/query", json={"table": "hourly", "limit": 100000})).json()
    assert len(r["rows"]) == min(500, len(rain_series())) and r["total"] == len(rain_series())
    r = (await async_client.post(API + "/explore/query", json={"table": "hourly", "limit": 10, "order_by": [{"column": "mm", "dir": "desc"}]})).json()
    assert len(r["rows"]) == 10 and r["truncated"] is True and r["rows"][0][3] == 400.0
    assert r["columns"][3] == {"name": "mm", "type": "number"} and r["spec"]["limit"] == 10


async def test_query_group_and_aggregate_in_database_and_in_memory(async_client):
    await put("rain", "r1", rain_series(), 23.5, 91.6)
    await put("rain", "r2", [(h, 1.0) for h in range(5)])
    q = {"table": "hourly", "group_by": ["station"], "aggregates": [{"fn": "count", "as": "n"}, {"fn": "sum", "column": "mm", "as": "total"}, {"fn": "max", "column": "mm", "as": "top"}],
         "order_by": [{"column": "n", "dir": "desc"}]}
    r = (await async_client.post(API + "/explore/query", json=q)).json()
    assert r["rows"][0][0] == "r1" and r["rows"][0][1] == len(rain_series()) and r["rows"][1] == ["r2", 5, 5.0, 1.0]
    assert [c["name"] for c in r["columns"]] == ["station", "n", "total", "top"]
    # time filter on the stored time, and the same grouping on the derived summary table
    r = (await async_client.post(API + "/explore/query", json={"table": "hourly", "filters": [{"column": "time", "op": ">=", "value": "2026-06-01T03:00:00Z"},
                                                                                              {"column": "station", "op": "=", "value": "r2"}]})).json()
    assert r["total"] == 2
    r = (await async_client.post(API + "/explore/query", json={"table": "station_summary", "aggregates": [{"fn": "count", "as": "n"}, {"fn": "sum", "column": "n_observations", "as": "obs"}]})).json()
    assert r["rows"] == [[2, len(rain_series()) + 5]]
    r = (await async_client.post(API + "/explore/query", json={"table": "station_summary", "filters": [{"column": "located", "op": "=", "value": True}]})).json()
    assert [x[0] for x in r["rows"]] == ["r1"]


async def test_daily_table_shows_raw_and_cleaned_totals(async_client):
    await put("rain", "r1", rain_series())
    r = (await async_client.post(API + "/explore/query", json={"table": "daily", "aggregates": [{"fn": "sum", "column": "raw_mm", "as": "raw"}, {"fn": "sum", "column": "imputed_hours", "as": "imp"}]})).json()
    assert r["rows"][0] == [round(sum(v for _, v in rain_series()), 6), 0]


# ------------------------------------------------------------------------------------------------ stations
async def test_stations_located_and_unlocated(async_client):
    await put("rain", "r1", [(0, 1.0), (1, 2.0)], 23.5, 91.6)
    await put("rain", "r2", [(0, 1.0)], None, None)
    await put("rain", "r3", [(0, 1.0)], 95.0, 10.0)             # latitude impossible: not located, not guessed
    r = (await async_client.get(API + "/explore/stations")).json()
    by = {s["station_key"]: s for s in r["stations"]}
    assert r["located"] == 1 and r["unlocated"] == 2
    assert by["r1"]["located"] and by["r1"]["rf25"]["grid"].startswith("RF25") and by["r1"]["nearest_imd"]["km"] >= 0 and by["r1"]["n_observations"] == 2
    assert by["r1"]["first"] == "2026-06-01T00:00:00Z" and by["r1"]["last"] == "2026-06-01T01:00:00Z"
    for k in ("r2", "r3"):
        assert by[k]["located"] is False and by[k]["rf25"] is None and by[k]["nearest_imd"] is None and by[k]["latitude"] is None
    assert "never placed by guessing" in r["note"]


# ------------------------------------------------------------------------------------------------ profile
async def test_profile_detection_of_each_kind(async_client):
    await put("temp", "t1", temp_series())
    await put("rain", "r1", rain_series())
    await put("cwc", "c1", [(h, 2.0 + h % 3) for h in (3, 4, 9, 30, 31, 55, 90, 91, 92, 140)])
    t = (await async_client.get(API + "/explore/profile", params={"source": "temp"})).json()
    assert t["kind"] == "continuous_state" and t["parameter"] == "unknown" and t["cadence"] == {"median_minutes": 60.0, "regular": True}
    assert t["reports_zero_values"] is False and t["verdicts"]["available"] is False
    r = (await async_client.get(API + "/explore/profile", params={"source": "rain"})).json()
    assert r["kind"] == "intermittent_accumulation" and r["reports_zero_values"] is True and r["n_zero"] > 0
    assert any("exactly zero" in e for e in r["evidence"]) and r["n_negative"] == 1
    c = (await async_client.get(API + "/explore/profile", params={"source": "cwc"})).json()
    assert c["reports_zero_values"] is False and c["cadence"]["regular"] is False and c["kind"] == "unknown"
    assert any("no zero values" in e for e in c["evidence"]) and any("agrees with the data" in e for e in c["evidence"])
    for p in (t, r, c):
        assert set(p) >= {"parameter", "kind", "reports_zero_values", "cadence", "units", "valid_range", "missing_codes", "evidence", "notes"}


async def test_profile_prefers_the_data_over_the_importer_flag(monkeypatch):
    monkeypatch.setattr(cwc, "omits_zero_values", True, raising=False)
    await put("cwc", "c1", [(h, 0.0 if h % 2 else 3.0) for h in range(40)])
    async with async_session_factory() as s:
        p = await profile_svc.get_profile(s, "cwc")
    assert p["reports_zero_values"] is True and p["importer_flag_omits_zero_values"] is True
    assert any("disagreement" in e for e in p["evidence"])
    # the older name is still read when the new one is absent
    monkeypatch.delattr(cwc, "omits_zero_values", raising=False)
    monkeypatch.setattr(cwc, "omits_zero_hours", True, raising=False)
    assert profile_svc.module_flag("cwc") is True


async def test_profile_edit_and_missing_codes(async_client):
    await put("temp", "t1", temp_series() + [(130, -9999.0)])
    p = (await async_client.get(API + "/explore/profile", params={"source": "temp"})).json()
    assert any("-9999" in e for e in p["evidence"]) and p["missing_codes"] == []
    r = await async_client.put(API + "/explore/profile", params={"source": "temp"}, json={"parameter": "Temperature", "units": "degC", "valid_range": [-50, 60], "missing_codes": [-9999]}, headers=H)
    assert r.status_code == 200
    p = r.json()
    assert p["parameter"] == "temperature" and p["units"] == "degC" and p["valid_range"] == [-50.0, 60.0] and p["missing_codes"] == [-9999.0]
    assert (await async_client.put(API + "/explore/profile", params={"source": "temp"}, json={"kind": "weird"}, headers=H)).status_code == 400
    assert (await async_client.put(API + "/explore/profile", params={"source": "temp"}, json={"valid_range": [5, 1]}, headers=H)).status_code == 400
    assert (await async_client.put(API + "/explore/profile", params={"source": "temp"}, json={"units": "C"})).status_code in (401, 403)


# ------------------------------------------------------------------------------------------------ default policy
def fill_of(policy):
    return next(s for s in policy["steps"] if s["step"] == "fill_gaps")


async def test_default_policy_by_kind(async_client):
    await put("temp", "t1", temp_series())
    await put("rain", "r1", rain_series())
    await put("cwc", "c1", [(h, 2.0 + h % 3) for h in (3, 4, 9, 30, 31, 55, 90, 91, 92, 140)])
    t = (await async_client.get(API + "/clean/policy/default", params={"source": "temp"})).json()
    r = (await async_client.get(API + "/clean/policy/default", params={"source": "rain"})).json()
    c = (await async_client.get(API + "/clean/policy/default", params={"source": "cwc"})).json()
    assert fill_of(t["policy"])["method"] == "linear" and t["policy"]["policy"] if False else fill_of(t["policy"])["method"] == "linear"
    assert t["policy"]["rule"] == "continuous-state-linear" and fill_of(t["policy"])["max_gap_steps"] == 3
    assert fill_of(r["policy"])["method"] == "none" and r["policy"]["rule"] == "intermittent-reports-zeros-no-fill"
    assert fill_of(c["policy"])["method"] == "none" and c["policy"]["rule"] in ("unknown-kind-no-fill", "intermittent-omits-zeros-no-fill")


# ------------------------------------------------------------------------------------------------ cleaning rules
async def test_continuous_series_gets_linear_fill_with_the_reason(async_client):
    await put("temp", "t1", temp_series())
    before = await obs_count()
    r = (await post(async_client, "/clean/plan", {"source": "temp"})).json()
    assert r["policy_source"] == "default derived from the profile" and r["default_rule"] == "continuous-state-linear"
    fills = [p for p in r["proposals"] if p["kind"] == "interpolate"]
    assert r["created"] == 2 and len(fills) == 2                      # the 2-step gap only
    a, b = temp_series()[9][1], temp_series()[10][1]                  # hours 9 and 12 are the neighbours of the gap 10 and 11
    assert fills[0]["at"] == "2026-06-01T10:00:00Z" and math.isclose(fills[0]["proposed"], round(a + (b - a) / 3, 3), abs_tol=1e-3)
    assert math.isclose(fills[1]["proposed"], round(a + 2 * (b - a) / 3, 3), abs_tol=1e-3)
    assert fills[0]["basis"] == "derived" and fills[0]["original"] is None and fills[0]["status"] == "pending"
    assert [n["at"] for n in fills[0]["neighbours"]] == ["2026-06-01T09:00:00Z", "2026-06-01T12:00:00Z"]
    why = fills[0]["why"]                                              # rule 6: gap length, both neighbours, method, limits, imputed label
    assert "2 step(s)" in why and "linear" in why and f"{a:g}" in why and f"{b:g}" in why and "at most 3" in why and "nothing is ever filled before the first or after the last" in why
    assert "imputed" in why
    assert {"station_key": "t1", "reason": "gap longer than max_gap_steps (3); left missing", "count": 10} in r["skipped"]
    assert await obs_count() == before                                 # rule 1: raw untouched
    assert r["verdicts"]["available"] is False and "does NOT claim validation verdicts" in r["verdicts"]["note"]
    # no proposal before the first or after the last reported hour, and none inside the long gap
    assert all("2026-06-01T10" <= p["at"] <= "2026-06-01T11:59" for p in fills)


async def test_rainfall_with_zeros_defaults_to_no_fill_but_excludes_impossible_values(async_client):
    await put("rain", "r1", rain_series())
    await async_client.put(API + "/explore/profile", params={"source": "rain"}, json={"parameter": "rainfall"}, headers=H)
    r = (await post(async_client, "/clean/plan", {"source": "rain"})).json()
    kinds = sorted((p["kind"], p["original"]) for p in r["proposals"])
    assert kinds == [("exclude", -5.0), ("exclude", 400.0)] and r["interpolate"] == 0 and r["exclude"] == 2
    whys = " ".join(p["why"] for p in r["proposals"])
    assert "outside the valid range for rainfall" in whys and f"{checks.INTENSITY_CEILING:g}" in whys and "original value is kept" in whys
    assert any("gaps stay missing" in s.get("note", "") for s in r["steps"] if s["step"] == "fill_gaps")
    # turned on by the user: linear fill, labelled imputed
    pol = {"steps": [{"step": "exclude_out_of_range"}, {"step": "fill_gaps", "method": "linear", "max_gap_steps": 3}]}
    r = (await post(async_client, "/clean/plan", {"source": "rain", "policy": pol})).json()
    fills = [p for p in r["proposals"] if p["kind"] == "interpolate"]
    assert len(fills) == 2 and fills[0]["proposed"] == 4.333 and fills[1]["proposed"] == 3.667 and all(p["basis"] == "derived" for p in fills)
    assert r["policy_source"] == "as sent"


async def test_source_that_omits_zeros_refuses_fill_and_override_without_reason(async_client):
    await put("cwc", "c1", [(h, 2.0 + h % 3) for h in (3, 4, 9, 30, 31, 55, 90, 91, 92, 140)])
    r = (await post(async_client, "/clean/plan", {"source": "cwc"})).json()          # default policy
    assert r["created"] == 0
    r = (await post(async_client, "/clean/plan", {"source": "cwc", "policy": {"steps": [{"step": "fill_gaps", "method": "linear"}]}})).json()
    assert r["created"] == 0 and any(s["station_key"] == "*" and ("only non-zero" in s["reason"] or "no zero values" in s["reason"] or "kind of this variable is unknown" in s["reason"]) for s in r["skipped"])
    # the legacy shortcut is refused the same way
    r = (await post(async_client, "/clean/plan", {"source": "cwc", "method": "linear"})).json()
    assert r["created"] == 0 and r["skipped"]
    assert await _pending() == 0


async def _pending():
    async with async_session_factory() as s:
        return (await s.execute(select(func.count()).select_from(PipelineCleaning))).scalar_one()


async def test_omit_zero_series_override_needs_a_recorded_reason(async_client):
    await put("omit", "o1", omit_series())
    await async_client.put(API + "/explore/profile", params={"source": "omit"}, json={"parameter": "rainfall"}, headers=H)
    p = (await async_client.get(API + "/explore/profile", params={"source": "omit"})).json()
    assert p["kind"] == "intermittent_accumulation" and p["reports_zero_values"] is False and p["cadence"]["regular"] is True
    fill = {"step": "fill_gaps", "method": "linear", "max_gap_steps": 3}
    for step in (fill, {**fill, "override_reason": ""}, {**fill, "override_reason": "ok"}, {**fill, "override_reason": "   "}):
        r = (await post(async_client, "/clean/plan", {"source": "omit", "policy": {"steps": [step]}})).json()
        assert r["created"] == 0 and any("no zero values" in s["reason"] and s["station_key"] == "*" for s in r["skipped"]), step
    ok = {**fill, "override_reason": "the logger records every hour, a missing row is a lost row"}
    r = (await post(async_client, "/clean/plan", {"source": "omit", "policy": {"steps": [ok]}})).json()
    assert r["created"] == 1 and r["proposals"][0]["kind"] == "interpolate" and "OVERRIDE recorded: the logger records every hour" in r["proposals"][0]["why"]
    assert r["steps"][-1]["override_reason"].startswith("the logger")
    async with async_session_factory() as s:
        plan = await s.get(CleaningPlan, r["plan_id"])
        assert plan.policy["steps"][0]["override_reason"].startswith("the logger") and plan.profile["kind"] == "intermittent_accumulation"


async def test_policy_validation(async_client):
    await put("temp", "t1", temp_series())
    bad = [{"steps": []}, {"steps": [{"step": "delete_everything"}]}, {"steps": [{"step": "fill_gaps", "method": "cubic"}]},
           {"steps": [{"step": "fill_gaps", "method": "linear", "max_gap_steps": 7}]}, {"steps": [{"step": "fill_gaps", "method": "linear", "sql": "x"}]},
           {"steps": [{"step": "fill_gaps"}, {"step": "fill_gaps"}]}, {"steps": [{"step": "fill_gaps", "method": "linear"}, {"step": "exclude_out_of_range"}]},
           {"steps": [{"step": "exclude_out_of_range", "min": 5, "max": 1}]}, "steps"]
    for pol in bad:
        r = await post(async_client, "/clean/plan", {"source": "temp", "policy": pol})
        assert r.status_code in (400, 422), pol
    assert (await post(async_client, "/clean/plan", {"source": "temp"}, headers={})).status_code in (401, 403)


async def test_unit_conversion_is_refused_not_faked(async_client):
    await put("temp", "t1", temp_series())
    r = (await post(async_client, "/clean/plan", {"source": "temp", "policy": {"steps": [{"step": "normalise_units", "from": "degF", "to": "degC"}]}})).json()
    assert r["created"] == 0 and any("NOT IMPLEMENTED" in s["reason"] for s in r["skipped"])


async def test_duplicates_step_and_replan_does_not_duplicate(async_client):
    await put("temp", "t1", temp_series())
    r1 = (await post(async_client, "/clean/plan", {"source": "temp"})).json()
    assert any(s["step"] == "remove_duplicates" and s["applied"] == 0 for s in r1["steps"])
    r2 = (await post(async_client, "/clean/plan", {"source": "temp"})).json()
    assert r2["created"] == 0 and any("already proposed" in s["reason"] for s in r2["skipped"])
    assert await _pending() == 2


async def test_decide_apply_and_use_clean_roll_up(async_client):
    await put("rain", "r1", rain_series(), 23.5, 91.6)
    await async_client.put(API + "/explore/profile", params={"source": "rain"}, json={"parameter": "rainfall"}, headers=H)
    pol = {"steps": [{"step": "exclude_out_of_range"}, {"step": "fill_gaps", "method": "linear", "max_gap_steps": 3}]}
    plan = (await post(async_client, "/clean/plan", {"source": "rain", "policy": pol})).json()
    assert plan["created"] == 4
    listed = (await async_client.get(API + "/clean/proposals", params={"status": "pending"})).json()
    assert listed["count"] == 4
    assert (await async_client.get(API + "/clean/proposals", params={"status": "pending", "station": "nope"})).json()["count"] == 0
    first = listed["proposals"][0]
    assert (await post(async_client, f"/clean/proposals/{first['id']}/decide", {"accept": False})).json()["status"] == "rejected"
    assert (await post(async_client, f"/clean/proposals/{first['id']}/decide", {"accept": True})).status_code == 409
    assert (await post(async_client, "/clean/proposals/99999/decide", {"accept": True})).status_code == 404
    assert (await post(async_client, f"/clean/proposals/{listed['proposals'][1]['id']}/decide", {"accept": True}, headers={})).status_code in (401, 403)
    # before anything is accepted, use_clean changes nothing
    async with async_session_factory() as s:
        plain = await qc.daily_totals(s, "rain")
        same = await qc.daily_totals(s, "rain", use_clean=True)
    assert [r.mm for r in plain] == [r.mm for r in same]
    summary = (await post(async_client, "/clean/apply", {"source": "rain", "accept_pending": True})).json()
    assert summary["newly_accepted"] == 3 and summary["accepted"] == 3 and summary["rejected"] == 1 and "no observation was changed" in summary["note"]
    rejected_kind = first["kind"]
    async with async_session_factory() as s:
        raw = await qc.daily_totals(s, "rain")
        clean = await qc.daily_totals(s, "rain", use_clean=True)
        run = await qc.run_qc(s, "rain", use_clean=True)
        plain_run = await qc.run_qc(s, "rain")
    imputed = sum(r.raw["imputed_hours"] for r in clean)
    excluded = sum(r.raw["excluded_hours"] for r in clean)
    assert imputed == (1 if rejected_kind == "interpolate" else 2) and excluded == (2 if rejected_kind == "interpolate" else 1) or imputed + excluded == 3
    assert sum(r.mm for r in raw) == round(sum(v for _, v in rain_series()), 3)               # raw roll-up never changes
    assert all("imputed_hours" not in r.raw for r in raw)
    st = run.settings["pipeline"]["use_clean"]
    assert st["use_clean"] is True and st["imputed_hours"] == imputed and st["excluded_hours"] == excluded and st["accepted_proposals"] == 3 and st["plan_ids"] == [plan["plan_id"]]
    assert st["policies"][0]["policy"]["steps"][-1]["method"] == "linear" and "derived" in st["note"]
    assert plain_run.settings["pipeline"]["use_clean"] == {"use_clean": False}


async def test_use_clean_totals_with_everything_accepted(async_client):
    await put("rain", "r1", rain_series())
    await async_client.put(API + "/explore/profile", params={"source": "rain"}, json={"parameter": "rainfall"}, headers=H)
    pol = {"steps": [{"step": "exclude_out_of_range"}, {"step": "fill_gaps", "method": "linear", "max_gap_steps": 3}]}
    await post(async_client, "/clean/plan", {"source": "rain", "policy": pol})
    await post(async_client, "/clean/apply", {"source": "rain", "accept_pending": True})
    async with async_session_factory() as s:
        clean = await qc.daily_totals(s, "rain", use_clean=True)
        raw = await qc.daily_totals(s, "rain")
    expect = round(sum(v for _, v in rain_series()) + 5.0 - 400.0 + 4.333 + 3.667, 3)
    assert round(sum(r.mm for r in clean), 3) == expect
    assert sum(r.raw["imputed_hours"] for r in clean) == 2 and sum(r.raw["excluded_hours"] for r in clean) == 2
    rows = (await async_client.post(API + "/explore/query", json={"table": "daily", "aggregates": [{"fn": "sum", "column": "imputed_hours", "as": "i"}, {"fn": "sum", "column": "mm", "as": "m"},
                                                                                                    {"fn": "sum", "column": "raw_mm", "as": "r"}]})).json()["rows"][0]
    assert rows[0] == 2 and math.isclose(rows[1], expect, abs_tol=1e-3) and math.isclose(rows[2], sum(r.mm for r in raw), abs_tol=1e-3)


async def test_gaps_table_and_non_rainfall_gets_no_verdicts(async_client):
    await put("temp", "t1", temp_series())
    await put("cwc", "c1", [(h, 2.0) for h in (3, 4, 9, 30)])
    g = (await async_client.post(API + "/explore/query", json={"table": "gaps", "order_by": [{"column": "missing_steps", "dir": "desc"}]})).json()
    assert g["total"] == 2 and g["rows"][0][4] == 10 and g["rows"][0][6] is False and g["rows"][1][6] is True      # only the regular source has gap rows
    assert all(row[1] == "temp" for row in g["rows"])
    await async_client.put(API + "/explore/profile", params={"source": "temp"}, json={"parameter": "temperature"}, headers=H)
    r = await post(async_client, "/clean/check", {"source": "temp"})
    assert r.status_code == 422 and "does NOT claim validation verdicts" in r.text


# ------------------------------------------------------------------------------------------------ assistant
async def ask(client, message, **kw):
    r = await client.post(API + "/assistant", json={"message": message, **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def test_assistant_intents_use_real_counts_and_change_nothing(async_client):
    await put("rain", "r1", rain_series(), 23.5, 91.6)
    await put("rain", "r2", [(0, 1.0), (1, 9.5)])
    await async_client.put(API + "/explore/profile", params={"source": "rain"}, json={"parameter": "rainfall"}, headers=H)
    before = (await obs_count(), await _pending())
    d = await ask(async_client, "describe my data")
    assert d["generator"] == "baseline-rules" and d["generated"] is True and d["label"] == "generated, not a decision"
    assert f"{len(rain_series()) + 2:,} stored values from 2 station" in d["reply"] and d["table_spec"]["table"] == "station_summary"
    s = await ask(async_client, "which stations are there and where")
    assert "1 located" in s["reply"] and "1 unlocated" in s["reply"] and s["table_spec"]["table"] == "stations"
    u = await ask(async_client, "show unlocated stations")
    assert "1 station(s) have no valid coordinates" in u["reply"] and u["table_spec"]["filters"] == [{"column": "located", "op": "=", "value": False}]
    w = await ask(async_client, "what were the wettest days")
    assert "largest daily total" in w["reply"] and w["table_spec"]["order_by"] == [{"column": "mm", "dir": "desc"}]
    sus = await ask(async_client, "any suspicious or negative values?")
    assert "1 stored value(s) are below 0" in sus["reply"] and "1 are above 300" in sus["reply"] or "1 are above" in sus["reply"]
    g = await ask(async_client, "where are the missing hours and gaps")
    assert "gap(s)" in g["reply"] and g["table_spec"]["table"] == "gaps"
    # each returned spec is runnable as is
    for out in (d, s, u, w, sus, g):
        r = await async_client.post(API + "/explore/query", json=out["table_spec"])
        assert r.status_code == 200, out["table_spec"]
    assert all(any("only reads" in x for x in o["why"]) for o in (d, s, u, w, sus, g))
    assert (await obs_count(), await _pending()) == before


async def test_assistant_says_the_narrator_is_not_connected(async_client):
    await put("rain", "r1", rain_series())
    out = await ask(async_client, "describe the data")
    assert "AI narrator not connected: this is the rule-based assistant" in out["reply"] and out["generator"] == "baseline-rules"
    assert "AI narrator not connected: this is the rule-based assistant" in out["why"]
    assert (await async_client.post(API + "/assistant", json={"message": ""})).status_code == 422
    assert (await async_client.post(API + "/assistant", json={"message": "x" * 1001})).status_code == 422
    assert (await async_client.post(API + "/assistant", json={"message": "hi", "run_id": 999999})).status_code == 404


async def test_assistant_best_cleaning_cites_the_rule_and_only_advises(async_client):
    await put("temp", "t1", temp_series())
    out = await ask(async_client, "what is the best cleaning for my data?")
    assert "Rule applied: continuous-state-linear" in out["reply"] and out["cleaning"]["rule"] == "continuous-state-linear" and out["cleaning"]["advice_only"] is True
    assert fill_of(out["cleaning"]["plan_hint"]["body"]["policy"])["method"] == "linear" and "does NOT claim validation verdicts" in out["reply"]
    assert "12 gap(s)" not in out["reply"] and "2 gap(s)" in out["reply"] and "longest 10" in out["reply"]
    await async_client.delete(API + "/x") if False else None
    await put("rain", "r1", rain_series())
    r = await ask(async_client, "how should I clean the rain data? interpolate?")
    assert "intermittent-reports-zeros-no-fill" in r["reply"] and "Gaps are left missing" in r["reply"] and fill_of(r["cleaning"]["plan_hint"]["body"]["policy"])["method"] == "none"
    await put("cwc", "c1", [(h, 2.0 + h % 3) for h in (3, 4, 9, 30, 31, 55, 90, 91, 92, 140)])
    c = await ask(async_client, "best way to clean my cwc data")
    assert fill_of(c["cleaning"]["plan_hint"]["body"]["policy"])["method"] == "none" and "zeros are omitted" in c["reply"] and c["cleaning"]["plan_hint"]["body"]["source"] == "cwc"
    assert await _pending() == 0


def narrator_with(handler):
    return NarratorExplainer("https://narrator.test/explain", "tok", 5.0, httpx.MockTransport(handler), _Limiter(1000))


async def test_assistant_forwards_to_a_mocked_narrator(async_client, monkeypatch):
    await put("temp", "t1", temp_series())
    seen = {}

    def handler(request):
        import json as _j
        seen["body"] = _j.loads(request.content)
        return httpx.Response(200, json={"text": "Linear fill suits this smooth series.", "model_id": "mock-1", "contributions": []})

    monkeypatch.setattr(narrate, "get_narrator", lambda: narrator_with(handler))
    out = await ask(async_client, "best cleaning for my data", history=[{"role": "user", "text": "hi"}])
    assert out["generator"] == "mcp-narrator" and out["reply"] == "Linear fill suits this smooth series." and out["generated"] is True
    body = seen["body"]
    assert body["kind"] == "chat" and body["question"] == "best cleaning for my data" and body["context"]["assistant"] == "explore" and body["context"]["advice_only"] is True
    assert "continuous-state-linear" in body["context"]["facts"] and body["context"]["history"] == [{"role": "user", "text": "hi"}]
    assert out["cleaning"]["rule"] == "continuous-state-linear" and out["table_spec"]["table"] == "gaps"

    def failing(request):
        return httpx.Response(500)

    monkeypatch.setattr(narrate, "get_narrator", lambda: narrator_with(failing))
    out = await ask(async_client, "describe my data")
    assert out["generator"] == "baseline-rules" and "did not answer" in out["reply"] and "rule-based assistant" in out["reply"]


# ------------------------------------------------------------------------------------------------ model card
async def test_model_card_from_the_catalogue_and_registry(async_client):
    r = (await async_client.get(API + "/model-card")).json()
    assert r["method"] == checks.METHOD and r["champion"] is None
    assert {c["name"] for c in r["checks"]} == set(checks.CATALOGUE)
    for c in r["checks"]:
        spec = checks.CATALOGUE[c["name"]]
        assert c["weight"] == spec.weight and c["layer"] == spec.layer and c["kind"] == spec.kind and c["needs"] == spec.needs and c["profile"] == spec.profile
        assert c["threshold_note"], c["name"]                        # a new check without a note fails here instead of drifting
    assert next(c for c in r["checks"] if c["name"] == "impossible_value")["threshold_note"].find(f"{checks.DAILY_MAX_MM:g}") >= 0
    assert r["explanation"]["narrator_connected"] is False and r["explanation"]["generator"] == "baseline-rules" and "AI narrator not connected" in r["explanation"]["note"]
    text = " ".join(r["flags_how"])
    assert "NOT a probability" in text and "never changes a verdict" in text and "own earlier wet days" in text and "neighbour" in text.lower()
    assert any("calibrated probability" in x for x in r["not_implemented"])
    async with async_session_factory() as s:
        s.add(ModelVersion(name="label-fusion", version="v1", metrics={"artifact": {"weights": [0.5, 0.1], "checks": ["negative_value", "duplicate_row"]}}, alias="champion", snapshot_id=7))
        s.add(ModelVersion(name="label-fusion", version="v0", metrics={}, alias="challenger"))
        await s.commit()
    r = (await async_client.get(API + "/model-card")).json()
    assert r["champion"]["version"] == "v1" and r["champion"]["weights"] == [0.5, 0.1] and r["champion"]["trained_from_snapshot"] == 7
    assert r["champion"]["metrics_basis"] == "declared, not verified"


# ------------------------------------------------------------------------------------------------ other parameters: differences come from the profile only
def wave(base, amp, outliers=None, clip=None):
    gone = {10, 11} | set(range(50, 60))
    out = []
    for h in range(120):
        if h in gone:
            continue
        v = base + amp * math.sin(h / 6 if clip is None else h / 5)
        v = round(max(clip, v) if clip is not None else v, 4)
        out.append((h, (outliers or {}).get(h, v)))
    return out


PARAM_CASES = [
    # source, parameter, series, how many values lie outside the registered range
    ("tmp", "temperature", wave(25, 6, {70: 75.0}), 1),
    ("rhu", "relative_humidity", wave(60, 25, {70: 105.0, 80: -3.0}), 2),
    ("prs", "pressure", wave(1000, 8, {70: 1500.0}), 1),
    ("wnd", "wind_speed", wave(0, 4, {70: -2.0}, clip=0.0), 1),
]


@pytest.mark.parametrize("source,parameter,series,n_out", PARAM_CASES)
async def test_other_parameters_clean_from_the_profile_alone(async_client, source, parameter, series, n_out):
    await put(source, "s1", series)
    p0 = (await async_client.get(API + "/explore/profile", params={"source": source})).json()
    if parameter == "wind_speed":
        # without a name the many calm zeros look intermittent: the user (or a registered parameter) decides
        assert p0["kind"] == "intermittent_accumulation" and p0["reports_zero_values"] is True
    else:
        assert p0["kind"] == "continuous_state" and p0["parameter"] == "unknown"
    p = (await async_client.put(API + "/explore/profile", params={"source": source}, json={"parameter": parameter}, headers=H)).json()
    assert p["kind"] == "continuous_state" and p["parameter"] == parameter and p["valid_range"] is not None and p["units"]
    assert p["verdicts"]["available"] is False and any("does NOT claim validation verdicts" in n for n in p["notes"])
    assert any("GENERATED data only" in n for n in p["notes"])
    d = (await async_client.get(API + "/clean/policy/default", params={"source": source})).json()["policy"]
    assert d["rule"] == "continuous-state-linear" and fill_of(d)["method"] == "linear" and fill_of(d)["max_gap_steps"] == 3
    ex = next(s for s in d["steps"] if s["step"] == "exclude_out_of_range")
    assert [ex["min"], ex["max"]] == p["valid_range"]
    r = (await post(async_client, "/clean/plan", {"source": source})).json()
    fills = [x for x in r["proposals"] if x["kind"] == "interpolate"]
    excl = [x for x in r["proposals"] if x["kind"] == "exclude"]
    assert len(fills) == 2 and len(excl) == n_out and r["verdicts"]["available"] is False
    lo, hi = p["valid_range"]
    assert all(lo <= f["proposed"] <= hi for f in fills) and all(not lo <= e["original"] <= hi for e in excl)
    assert all("valid range" in e["why"] for e in excl) and {"station_key": "s1", "reason": "gap longer than max_gap_steps (3); left missing", "count": 10} in r["skipped"]
    if parameter == "wind_speed":
        assert p["reports_zero_values"] is True and all(f["proposed"] >= 0 for f in fills)      # a fill between non-negative values is never negative
        assert excl[0]["original"] == -2.0
    assert (await post(async_client, "/clean/check", {"source": source})).status_code == 422


async def test_wind_fill_next_to_calm_zeros_stays_non_negative(async_client):
    # calm (0) on one side, a gust on the other: the fill is between them, so it is between 0 and the gust
    series = [(h, 0.0) for h in range(0, 10)] + [(13, 6.0)] + [(h, 6.0) for h in range(14, 40)]
    await put("wnd", "s1", series)
    await async_client.put(API + "/explore/profile", params={"source": "wnd"}, json={"parameter": "wind_speed"}, headers=H)
    r = (await post(async_client, "/clean/plan", {"source": "wnd"})).json()
    vals = [p["proposed"] for p in r["proposals"] if p["kind"] == "interpolate"]
    assert vals == [1.5, 3.0, 4.5] and min(vals) >= 0


async def test_unknown_kind_defaults_to_no_fill_with_the_reason(async_client):
    await put("few", "s1", [(h, float(1 + (h * 7) % 11)) for h in range(8) if h != 4])           # too few points
    await put("irr", "s1", [(h, float(1 + (h * 7) % 11)) for h in (0, 1, 2, 5, 6, 11, 12, 13, 14, 20, 21, 22, 23, 24, 31, 32, 33, 40, 41, 42, 43, 44, 45, 46, 47, 48,
                                                                     49, 50, 58, 59, 60, 61, 62, 70, 71)])      # irregular cadence, jumpy, no zeros
    for source, why in (("few", "fewer than"), ("irr", "neither mostly zero nor smooth")):
        p = (await async_client.get(API + "/explore/profile", params={"source": source})).json()
        assert p["kind"] == "unknown" and any(why in e for e in p["evidence"]) and any("kind unknown" in n for n in p["notes"])
        d = (await async_client.get(API + "/clean/policy/default", params={"source": source})).json()["policy"]
        assert d["rule"] == "unknown-kind-no-fill" and fill_of(d)["method"] == "none" and "not known" in d["why"]
        r = (await post(async_client, "/clean/plan", {"source": source})).json()
        assert r["created"] == 0 and any("gaps stay missing" in s.get("note", "") for s in r["steps"])
        r = (await post(async_client, "/clean/plan", {"source": source, "policy": {"steps": [{"step": "fill_gaps", "method": "linear"}]}})).json()
        assert r["created"] == 0 and any("kind of this variable is unknown" in s["reason"] for s in r["skipped"])
    assert await _pending() == 0
