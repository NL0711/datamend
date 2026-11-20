"""Explore step: dynamic tables over the stored data, a declarative allowlisted query, and the located stations.

The query is a plain object (table, columns, filters, group_by, aggregates, order_by, limit). Every name is checked against the allowlist in ``TABLES``
and ``OPS`` / ``FUNCS``; values are only ever bound parameters (SQL) or compared as Python values (derived tables); there is no raw SQL string anywhere.
``hourly`` can hold millions of rows, so it is queried in the database (SQLAlchemy Core, SQLite and PostgreSQL alike); the other tables are small or
derived (roll-ups, gaps, flags) and are built in memory, capped at ``MAX_MATERIALISED`` rows, then queried with the same semantics.

Nothing here is specific to rainfall: the column ``mm`` is the stored value column; its meaning and units come from the dataset profile (profile.py).
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline import cleaning, profile as profile_svc
from backend.app.pipeline.models import Observation, PipelineStation
from backend.app.places import imd, lookup
from backend.app.places.grid import GridError
from backend.app.validation.models import ValidationCheckHit, ValidationResult

OPS = ("=", "!=", "<", "<=", ">", ">=", "in", "contains", "is_null")
FUNCS = ("count", "sum", "avg", "min", "max")
DEFAULT_LIMIT, MAX_LIMIT = 100, 500
MAX_MATERIALISED = 300_000
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")


class QueryError(ValueError):
    """A request that names something outside the allowlist, or a value of the wrong type. The API answers 400."""


def _t(label: str, description: str, cols: Sequence[Tuple[str, str, str]]) -> Dict[str, Any]:
    return {"label": label, "description": description, "columns": [{"name": n, "type": t, "description": d} for n, t, d in cols]}


TABLES: Dict[str, Dict[str, Any]] = {
    "stations": _t("Stations", "Every station of every imported dataset, with its coordinates when the file gave them (never guessed).", [
        ("station_key", "text", "stable id of the station"), ("source", "text", "dataset it came from"), ("name", "text", "station name"),
        ("state", "text", "state, if given"), ("district", "text", "district, if given"), ("latitude", "number", "degrees north, or empty"),
        ("longitude", "number", "degrees east, or empty"), ("located", "bool", "true when valid coordinates were given")]),
    "hourly": _t("Stored values", "The raw store, one row per station and reported step, exactly as imported (never changed). Column mm is the stored value; "
                 "its parameter and units are in the dataset profile.", [
        ("source", "text", "dataset"), ("station", "text", "station id"), ("time", "datetime", "UTC time of the value"), ("mm", "number", "the stored value"),
        ("job", "integer", "ingest job that stored it")]),
    "daily": _t("Rain-day totals", "Totals per station and rain day (03 UTC to 03 UTC), built from the stored values. mm includes ACCEPTED cleaning (imputed values "
                "are derived, not measured); raw_mm is the sum without any cleaning.", [
        ("station", "text", "station id"), ("source", "text", "dataset"), ("day", "date", "rain day, labelled by the date it ends"),
        ("mm", "number", "total including accepted cleaning"), ("raw_mm", "number", "total of the stored values only"),
        ("hours_reported", "integer", "steps that were actually reported"), ("max_hour_mm", "number", "largest single step in the day"),
        ("imputed_hours", "integer", "steps filled in by accepted cleaning (derived, not measured)"),
        ("excluded_hours", "integer", "steps removed by accepted cleaning")]),
    "gaps": _t("Gaps", "Missing steps between two consecutive reported values. Only datasets with a regular cadence have gap rows (a gap needs an expected step). "
               "interpolation_allowed says whether the dataset profile permits filling at all, not that it is recommended.", [
        ("station", "text", "station id"), ("source", "text", "dataset"), ("gap_start", "datetime", "last reported value before the gap"),
        ("gap_end", "datetime", "first reported value after the gap"), ("missing_steps", "integer", "expected steps with no value"),
        ("step_minutes", "number", "expected step from the profile cadence"), ("interpolation_allowed", "bool", "the profile permits filling and the gap is short enough"),
        ("reason", "text", "why filling is or is not permitted")]),
    "station_summary": _t("Station summary", "One row per station: counts, first and last time, total of the stored values.", [
        ("station", "text", "station id"), ("source", "text", "dataset"), ("name", "text", "station name"), ("n_observations", "integer", "stored values"),
        ("first", "datetime", "first stored time"), ("last", "datetime", "last stored time"), ("total_mm", "number", "sum of the stored values"),
        ("located", "bool", "valid coordinates known")]),
    "flags": _t("Flagged station-days", "Station-days of ONE check run (run_id required) whose verdict is SUSPECT or UNCERTAIN, with the checks that fired. The rule score "
                "is an uncalibrated ordering, not a probability.", [
        ("station", "text", "station id"), ("day", "text", "rain day"), ("mm", "number", "daily total"), ("verdict", "text", "SUSPECT or UNCERTAIN"),
        ("rule_score", "number", "uncalibrated rule score"), ("severity", "text", "band of the rule score"), ("checks", "text", "names of the checks that fired")]),
}


def table_list() -> Dict[str, Any]:
    return {"tables": [{"id": k, "label": v["label"], "description": v["description"], "columns": v["columns"]} for k, v in TABLES.items()]}


def _ctypes(table: str) -> Dict[str, str]:
    return {c["name"]: c["type"] for c in TABLES[table]["columns"]}


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)


def _iso(t: datetime) -> str:
    return _utc(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ser(v: Any) -> Any:
    if isinstance(v, datetime):
        return _iso(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _coerce(ctype: str, v: Any, where: str) -> Any:
    if ctype in ("number", "integer"):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise QueryError(f"{where}: expected a finite number")
        return v
    if ctype == "text":
        if not isinstance(v, str) or len(v) > 200:
            raise QueryError(f"{where}: expected text of at most 200 characters")
        return v
    if ctype == "bool":
        if not isinstance(v, bool):
            raise QueryError(f"{where}: expected true or false")
        return v
    try:
        if ctype == "datetime":
            return _utc(datetime.fromisoformat(str(v).replace("Z", "+00:00")))
        if ctype == "date":
            return date.fromisoformat(str(v)[:10])
    except ValueError:
        pass
    raise QueryError(f"{where}: expected an ISO {ctype}")


# ------------------------------------------------------------------------------------------------ parsing the spec
def parse(body: Dict[str, Any]) -> Dict[str, Any]:
    table = body.get("table")
    if table not in TABLES:
        raise QueryError(f"unknown table {table!r}; allowed: " + ", ".join(TABLES))
    types = _ctypes(table)

    def col(name: Any, where: str) -> str:
        if not isinstance(name, str) or name not in types:
            raise QueryError(f"{where}: unknown column {name!r} for table {table}; allowed: " + ", ".join(types))
        return name

    filters = []
    for i, f in enumerate(body.get("filters") or []):
        if not isinstance(f, dict):
            raise QueryError("a filter must be an object {column, op, value}")
        c, op = col(f.get("column"), f"filters[{i}]"), f.get("op")
        if op not in OPS:
            raise QueryError(f"filters[{i}]: unknown op {op!r}; allowed: " + ", ".join(OPS))
        ct, v = types[c], f.get("value")
        if op == "is_null":
            v = True if v is None else _coerce("bool", v, f"filters[{i}].value")
        elif op == "in":
            if not isinstance(v, list) or not 1 <= len(v) <= 200:
                raise QueryError(f"filters[{i}]: 'in' needs a list of 1 to 200 values")
            v = [_coerce(ct, x, f"filters[{i}].value") for x in v]
        elif op == "contains":
            if ct != "text":
                raise QueryError(f"filters[{i}]: 'contains' works on text columns only")
            v = _coerce("text", v, f"filters[{i}].value")
        else:
            if ct == "bool" and op not in ("=", "!="):
                raise QueryError(f"filters[{i}]: a true/false column supports only = and !=")
            v = _coerce(ct, v, f"filters[{i}].value")
        filters.append((c, op, v))
    group_by = [col(c, "group_by") for c in (body.get("group_by") or [])]
    aggs = []
    for i, a in enumerate(body.get("aggregates") or []):
        fn = a.get("fn")
        if fn not in FUNCS:
            raise QueryError(f"aggregates[{i}]: unknown function {fn!r}; allowed: " + ", ".join(FUNCS))
        c = a.get("column")
        if c in (None, "*"):
            if fn != "count":
                raise QueryError(f"aggregates[{i}]: {fn} needs a column")
            c = None
        else:
            c = col(c, f"aggregates[{i}]")
            if fn in ("sum", "avg") and types[c] not in ("number", "integer"):
                raise QueryError(f"aggregates[{i}]: {fn} works on number columns only")
            if fn in ("min", "max") and types[c] == "bool":
                raise QueryError(f"aggregates[{i}]: {fn} does not work on true/false columns")
        name = a.get("as") or f"{fn}_{c or 'rows'}"
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise QueryError(f"aggregates[{i}]: 'as' must be a plain name (letters, digits, underscore)")
        otype = "integer" if fn == "count" else ("number" if fn in ("sum", "avg") else types[c])
        aggs.append((fn, c, name, otype))
    grouping = bool(group_by or aggs)
    columns = [col(c, "columns") for c in (body.get("columns") or [])]
    if grouping and columns:
        raise QueryError("'columns' cannot be combined with group_by or aggregates (the output is the group columns and the aggregates)")
    if grouping:
        outs = [(c, types[c]) for c in group_by] + [(n, t) for _, _, n, t in aggs]
    else:
        outs = [(c, types[c]) for c in (columns or list(types))]
    names = [n for n, _ in outs]
    if len(set(names)) != len(names):
        raise QueryError("output names must be unique (an aggregate 'as' collides with another column)")
    order = []
    for i, o in enumerate(body.get("order_by") or []):
        c, d = o.get("column"), (o.get("dir") or "asc")
        if c not in names:
            raise QueryError(f"order_by[{i}]: {c!r} is not an output column; allowed: " + ", ".join(names))
        if d not in ("asc", "desc"):
            raise QueryError(f"order_by[{i}]: dir must be asc or desc")
        order.append((c, d))
    limit = body.get("limit")
    limit = DEFAULT_LIMIT if limit is None else limit
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise QueryError("limit must be a whole number of at least 1")
    limit = min(limit, MAX_LIMIT)
    spec = {"table": table, "columns": columns, "filters": [{"column": c, "op": op, "value": _ser(v) if not isinstance(v, list) else [_ser(x) for x in v]}
                                                             for c, op, v in filters],
            "group_by": group_by, "aggregates": [{"fn": fn, "column": c, "as": n} for fn, c, n, _ in aggs],
            "order_by": [{"column": c, "dir": d} for c, d in order], "limit": limit, "run_id": body.get("run_id")}
    return {"table": table, "types": types, "filters": filters, "group_by": group_by, "aggs": aggs, "outs": outs, "order": order, "limit": limit,
            "grouping": grouping, "spec": spec, "run_id": body.get("run_id")}


# ------------------------------------------------------------------------------------------------ in-memory executor
def _cmp(op: str, a: Any, b: Any) -> bool:
    if op == "is_null":
        return (a is None) == b
    if a is None:
        return False
    if op == "=":
        return a == b
    if op == "!=":
        return a != b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "in":
        return a in b
    if op == "contains":
        return b.lower() in str(a).lower()
    return False


def _agg(fn: str, vals: List[Any], n_rows: int) -> Any:
    if fn == "count":
        return n_rows if vals is None else len(vals)
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    if fn == "sum":
        return round(sum(vals), 6)
    if fn == "avg":
        return round(sum(vals) / len(vals), 6)
    return min(vals) if fn == "min" else max(vals)


def run_memory(plan: Dict[str, Any], rows: List[Tuple[Any, ...]]) -> Dict[str, Any]:
    names = list(plan["types"])
    ix = {n: i for i, n in enumerate(names)}
    for c, op, v in plan["filters"]:
        rows = [r for r in rows if _cmp(op, r[ix[c]], v)]
    if plan["grouping"]:
        groups: Dict[Tuple[Any, ...], List[Tuple[Any, ...]]] = {}
        for r in rows:
            groups.setdefault(tuple(r[ix[c]] for c in plan["group_by"]), []).append(r)
        if not plan["group_by"]:
            groups = {(): rows}
        out = []
        for key, rs in groups.items():
            vals = list(key)
            for fn, c, _, _ in plan["aggs"]:
                vals.append(_agg(fn, None if c is None else [r[ix[c]] for r in rs], len(rs)))
            out.append(tuple(vals))
        oidx = {n: i for i, (n, _) in enumerate(plan["outs"])}
    else:
        oidx = {n: i for i, (n, _) in enumerate(plan["outs"])}
        out = [tuple(r[ix[n]] for n, _ in plan["outs"]) for r in rows]
    for c, d in reversed(plan["order"]):
        out.sort(key=lambda r, i=oidx[c]: (r[i] is None, r[i] if r[i] is not None else 0), reverse=(d == "desc"))
    total = len(out)
    return {"rows": out[:plan["limit"]], "total": total}


# ------------------------------------------------------------------------------------------------ database executor (hourly)
HOURLY_COLS = {"source": Observation.source, "station": Observation.station_key, "time": Observation.observed_at, "mm": Observation.value_mm, "job": Observation.job_id}


async def run_sql_hourly(session: AsyncSession, plan: Dict[str, Any]) -> Dict[str, Any]:
    conds = []
    for c, op, v in plan["filters"]:
        e = HOURLY_COLS[c]
        if op == "is_null":
            conds.append(e.is_(None) if v else e.is_not(None))
        elif op == "in":
            conds.append(e.in_(v))
        elif op == "contains":
            conds.append(e.icontains(v, autoescape=True))
        else:
            conds.append({"=": e == v, "!=": e != v, "<": e < v, "<=": e <= v, ">": e > v, ">=": e >= v}[op])
    exprs: Dict[str, Any] = {}
    if plan["grouping"]:
        for c in plan["group_by"]:
            exprs[c] = HOURLY_COLS[c]
        for fn, c, n, _ in plan["aggs"]:
            e = HOURLY_COLS[c] if c else None
            exprs[n] = func.count() if (fn == "count" and e is None) else getattr(func, fn)(e)
    else:
        for n, _ in plan["outs"]:
            exprs[n] = HOURLY_COLS[n]
    q = select(*[e.label(n) for n, e in exprs.items()]).where(*conds)
    if plan["group_by"]:
        q = q.group_by(*[HOURLY_COLS[c] for c in plan["group_by"]])
    total = (await session.execute(select(func.count()).select_from(q.order_by(None).subquery()))).scalar_one()
    for c, d in plan["order"]:
        q = q.order_by(exprs[c].desc() if d == "desc" else exprs[c].asc())
    rows = (await session.execute(q.limit(plan["limit"]))).all()
    return {"rows": [tuple(r) for r in rows], "total": int(total)}


# ------------------------------------------------------------------------------------------------ derived tables
def _has_coords(lat: Optional[float], lon: Optional[float]) -> bool:
    return (lat is not None and lon is not None and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180)


async def _cap(rows: List[Any], what: str) -> List[Any]:
    if len(rows) > MAX_MATERIALISED:
        raise QueryError(f"the {what} table would have more than {MAX_MATERIALISED:,} rows; use the hourly or stations table, or narrow the data")
    return rows


async def t_stations(session: AsyncSession, plan: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    sts = (await session.execute(select(PipelineStation).order_by(PipelineStation.station_key))).scalars().all()
    return [(s.station_key, s.source, s.name, s.state, s.district, s.latitude, s.longitude, _has_coords(s.latitude, s.longitude)) for s in sts]


async def t_station_summary(session: AsyncSession, plan: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    o = Observation
    agg = (await session.execute(select(o.source, o.station_key, func.count(), func.min(o.observed_at), func.max(o.observed_at), func.sum(o.value_mm))
                                 .group_by(o.source, o.station_key).order_by(o.source, o.station_key))).all()
    st = {s.station_key: s for s in (await session.execute(select(PipelineStation))).scalars().all()}
    out = []
    for src, key, n, first, last, tot in agg:
        s = st.get(key)
        out.append((key, src, s.name if s else None, int(n), _utc(first), _utc(last), round(float(tot or 0), 3), bool(s and _has_coords(s.latitude, s.longitude))))
    return await _cap(out, "station_summary")


async def t_daily(session: AsyncSession, plan: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    from backend.app.pipeline import qc
    out = []
    for src in await profile_svc.sources_present(session):
        raw = await qc.daily_totals(session, src, use_clean=False)
        clean = {(r.station_id, r.day): r for r in await qc.daily_totals(session, src, use_clean=True)} if await cleaning.load_accepted(session, src) else None
        for r in raw:
            c = clean.get((r.station_id, r.day)) if clean is not None else r
            out.append((r.station_id, src, r.day, c.mm if c is not None else None, r.mm, int(r.raw["hours_reported"]), float(r.raw["max_hour_mm"]),
                        int(c.raw.get("imputed_hours", 0)) if (c is not None and clean is not None) else 0,
                        int(c.raw.get("excluded_hours", 0)) if (c is not None and clean is not None) else 0))
        await _cap(out, "daily")
    return out


async def t_gaps(session: AsyncSession, plan: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    out = []
    for src in await profile_svc.sources_present(session):
        prof = await profile_svc.get_profile(session, src)
        step = cleaning._step_minutes(prof)
        if step is None:
            continue
        ok_fill, why_not, _ = cleaning.fill_decision(prof, {"method": "linear"})
        cap = cleaning.DEFAULT_GAP
        keys = [r[0] for r in (await session.execute(select(Observation.station_key).where(Observation.source == src).distinct().order_by(Observation.station_key))).all()]
        for k in keys:
            ts = [_utc(r[0]) for r in (await session.execute(select(Observation.observed_at).where(Observation.source == src, Observation.station_key == k)
                                                             .order_by(Observation.observed_at))).all()]
            for a, b in zip(ts, ts[1:]):
                d = (b - a).total_seconds() / 60.0 / step
                if d < 1.5:
                    continue
                miss = round(d) - 1
                if abs(d - round(d)) > 0.01:
                    allowed, reason = False, "the interval is not a whole number of steps"
                elif not ok_fill:
                    allowed, reason = False, why_not
                elif miss > cap:
                    allowed, reason = False, f"longer than {cap} steps"
                else:
                    allowed, reason = True, "the profile permits filling this short gap (the default policy still leaves gaps missing unless it is switched on)" if prof["kind"] != "continuous_state" else "the profile permits filling this short gap"
                out.append((k, src, a, b, miss, step, allowed, reason))
            await _cap(out, "gaps")
    return out


async def t_flags(session: AsyncSession, plan: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    run_id = plan["run_id"]
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        raise QueryError("the flags table needs a run_id (the check run to read)")
    rs = (await session.execute(select(ValidationResult).where(ValidationResult.run_id == run_id, ValidationResult.verdict.in_(("SUSPECT", "UNCERTAIN")))
                                .order_by(ValidationResult.rule_score.desc(), ValidationResult.id))).scalars().all()
    hits: Dict[int, List[str]] = {}
    for rid, name in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check).where(ValidationCheckHit.run_id == run_id)
                                            .order_by(ValidationCheckHit.weight.desc()))).all():
        hits.setdefault(rid, []).append(name)
    return await _cap([(r.station_id, r.time_key, r.mm, r.verdict, r.rule_score, r.severity, ", ".join(hits.get(r.id, []))) for r in rs], "flags")


BUILDERS: Dict[str, Callable[..., Any]] = {"stations": t_stations, "station_summary": t_station_summary, "daily": t_daily, "gaps": t_gaps, "flags": t_flags}


async def run_query(session: AsyncSession, body: Dict[str, Any]) -> Dict[str, Any]:
    """Run a declarative query. Raises QueryError (400) for anything outside the allowlist."""
    plan = parse(body)
    if plan["table"] == "hourly":
        res = await run_sql_hourly(session, plan)
    else:
        res = run_memory(plan, await BUILDERS[plan["table"]](session, plan))
    rows = [[_ser(v) for v in r] for r in res["rows"]]
    return {"columns": [{"name": n, "type": t} for n, t in plan["outs"]], "rows": rows, "total": res["total"], "truncated": res["total"] > len(rows),
            "spec": plan["spec"]}


# ------------------------------------------------------------------------------------------------ located stations
async def stations_view(session: AsyncSession) -> Dict[str, Any]:
    """Stations with their RF25 cell and nearest IMD station when coordinates exist; the rest are listed as unlocated, never guessed."""
    o = Observation
    counts = {k: (int(n), f, l) for k, n, f, l in (await session.execute(select(o.station_key, func.count(), func.min(o.observed_at), func.max(o.observed_at))
                                                                       .group_by(o.station_key))).all()}
    sts = (await session.execute(select(PipelineStation).order_by(PipelineStation.station_key))).scalars().all()
    out, n_loc = [], 0
    for s in sts:
        located = _has_coords(s.latitude, s.longitude)
        rf25 = nearest = None
        if located:
            n_loc += 1
            try:
                loc = lookup.locate(s.latitude, s.longitude)
                rf25 = {"row": loc["cell"]["row"], "col": loc["cell"]["col"], "lat": loc["cell"]["lat"], "lon": loc["cell"]["lon"], "grid": loc["cell"]["grid"],
                        "is_land": loc["is_land"], "client_region": loc["client_region"]}
            except GridError:
                rf25 = None                       # outside the RF25 domain: located, but no grid cell
            nearest = imd.nearest(s.latitude, s.longitude)
        n, f, l = counts.get(s.station_key, (0, None, None))
        out.append({"station_key": s.station_key, "source": s.source, "name": s.name, "state": s.state, "district": s.district,
                    "latitude": s.latitude if located else None, "longitude": s.longitude if located else None, "located": located, "rf25": rf25,
                    "nearest_imd": nearest, "n_observations": n, "first": _iso(f) if f else None, "last": _iso(l) if l else None})
    return {"stations": out, "located": n_loc, "unlocated": len(out) - n_loc,
            "note": "A station is located only when its file gave valid coordinates; stations without them are listed as unlocated and are never placed by guessing. "
                    "The RF25 cell and the nearest listed IMD (NOAA ISD) station are derived from the coordinates."}
