"""Wayfinder t02: measure storage, compression, ingest speed and read time of the raw observation store on a live Timescale/Tiger service.

Everything runs in a separate schema (``dm_measure``) with SYNTHETIC data and the schema is dropped at the end (also on failure).
The connection string is read from an env file or the environment into a variable and is never printed or written.

    python scripts/measure_tiger_storage.py --env-file <path to .env> --out <results.json>             # full measurement
    python scripts/measure_tiger_storage.py --env-file <path to .env> --precheck-only                  # read-only look, creates nothing

All numbers it prints are MEASURED on the machine that runs it against the service it connects to (network time is included in ingest and
read timings). The data is synthetic: the compression ratio depends on the value pattern, so two patterns are measured.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_ENV_AT_START = dict(os.environ)                                        # the real value (if exported) must be read before it is overridden below
_SCRATCH = tempfile.mkdtemp(prefix="dm_measure_")                       # the app modules build an engine at import time; point it at a scratch SQLite
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(Path(_SCRATCH) / "unused.db").replace("\\", "/")

import asyncpg                                                          # noqa: E402
import numpy as np                                                      # noqa: E402
from sqlalchemy import event                                            # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine    # noqa: E402

from backend.app.db.database import Base                               # noqa: E402
import backend.app.pipeline.models                                      # noqa: E402,F401  (registers the tables)
import backend.app.validation.models                                    # noqa: E402,F401
from backend.app.pipeline import qc, store                              # noqa: E402

SCHEMA = "dm_measure"
SOURCE = "synthetic"
COLS = ["source", "station_key", "observed_at", "value_mm", "job_id"]
BASE = datetime(2023, 1, 1, tzinfo=timezone.utc)
HOURS = [BASE + timedelta(hours=i) for i in range(8760)]
R: dict = {"synthetic": True, "note": "all data is generated; timings include network time from the machine that ran this"}


# ---------------------------------------------------------------- connection

def load_url(env_file: str, var: str) -> str:
    if _ENV_AT_START.get(var):
        return _ENV_AT_START[var]
    for line in open(env_file, encoding="utf-8"):
        line = line.strip()
        if line.startswith(var + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{var} not found in the environment or in the env file")


def pg_kwargs(url: str, search_path: str | None = None) -> dict:
    u = urlsplit(url)
    q = parse_qs(u.query)
    ssl = (q.get("ssl") or q.get("sslmode") or [None])[0]
    kw = dict(host=u.hostname, port=u.port or 5432, user=unquote(u.username or ""), password=unquote(u.password or ""),
              database=u.path.lstrip("/"), timeout=30)
    if ssl and ssl not in ("disable", "false"):
        kw["ssl"] = True if ssl == "true" else ssl
    return kw                                       # no startup parameters: a pooler in front of the service may refuse them; SET after connecting


async def connect(url: str, search_path: str | None = None):
    c = await asyncpg.connect(**pg_kwargs(url))
    await c.execute("SET statement_timeout = 0")
    if search_path:
        await c.execute(f"SET search_path = {search_path}")
    return c


def sa_url(url: str) -> str:
    url = url.replace("sslmode=", "ssl=")                  # asyncpg through SQLAlchemy takes ssl=, the Tiger CLI prints sslmode=
    for old in ("postgres://", "postgresql://"):
        if url.startswith(old):
            return "postgresql+asyncpg://" + url[len(old):]
    return url


# ---------------------------------------------------------------- data

def gen_blocks(profile: str, n_rows: int, seed: int, per_block: int = 20, start_idx: int = 0, source: str = SOURCE):
    """Yield (records, station_keys) of SYNTHETIC hourly rain. profile 'hourly': every hour of 2023 per station (92 % zeros, 8 % wet hours,
    exponential mean 2 mm, 0.1 mm steps). profile 'wet_only': only the wet hours (like the CWC files, which list non-zero hours)."""
    rng = np.random.default_rng(seed)
    produced, idx = 0, start_idx
    while produced < n_rows:
        recs, keys = [], []
        for _ in range(per_block):
            if produced >= n_rows:
                break
            key, job = f"SYN{idx:05d}", 1 + idx // 50
            wet = rng.random(8760) < 0.08
            vals = np.where(wet, np.round(rng.exponential(2.0, 8760) + 0.1, 1), 0.0)
            sel = np.nonzero(wet)[0] if profile == "wet_only" else np.arange(8760)
            sel = sel[: n_rows - produced]
            vl = vals.tolist()
            recs.extend((source, key, HOURS[h], vl[h], job) for h in sel.tolist())
            produced += len(sel)
            keys.append(key)
            idx += 1
        yield recs, keys


async def copy_load(conn, table: str, blocks):
    """COPY all blocks; returns (rows, seconds spent in COPY only, station keys)."""
    rows, secs, keys = 0, 0.0, []
    for recs, ks in blocks:
        t = time.perf_counter()
        await conn.copy_records_to_table(table, records=recs, columns=COLS, schema_name=SCHEMA)
        secs += time.perf_counter() - t
        rows += len(recs)
        keys.extend(ks)
    return rows, secs, keys


# ---------------------------------------------------------------- measurements

async def sizes(conn, table: str) -> dict:
    d = await conn.fetchrow(f"SELECT table_bytes, index_bytes, toast_bytes, total_bytes FROM hypertable_detailed_size('{table}')")
    out = {k: int(d[k] or 0) for k in ("table_bytes", "index_bytes", "toast_bytes", "total_bytes")}
    out["chunks"] = await conn.fetchval(f"SELECT count(*) FROM show_chunks('{table}')")
    out["rows"] = await conn.fetchval(f"SELECT count(*) FROM {table}")
    out["bytes_per_row_total"] = round(out["total_bytes"] / max(out["rows"], 1), 2)
    out["bytes_per_row_table"] = round(out["table_bytes"] / max(out["rows"], 1), 2)
    out["bytes_per_row_index"] = round(out["index_bytes"] / max(out["rows"], 1), 2)
    return out


async def compress_all(conn, table: str) -> dict:
    chunks = [r[0] for r in await conn.fetch(f"SELECT c::text FROM show_chunks('{table}') c")]
    t = time.perf_counter()
    for c in chunks:
        await conn.execute("SELECT compress_chunk($1::regclass, if_not_compressed => true)", c)
    out = {"chunks_compressed": len(chunks), "seconds": round(time.perf_counter() - t, 1)}
    try:
        st = await conn.fetchrow(f"SELECT * FROM hypertable_compression_stats('{table}')")
        out["stats"] = {k: (int(v) if v is not None else None) for k, v in dict(st).items()} if st else None
    except Exception as exc:
        out["stats_error"] = str(exc).splitlines()[0][:160]
    return out


async def read_station_year(conn, table: str, keys: list, reps: int = 5) -> dict:
    sql = (f"SELECT observed_at, value_mm FROM {table} WHERE source = $1 AND station_key = $2 AND observed_at >= $3 AND observed_at < $4 "
           f"ORDER BY observed_at")
    start, end = BASE, BASE + timedelta(days=365)
    rtt = []
    for _ in range(20):
        t = time.perf_counter()
        await conn.fetchval("SELECT 1")
        rtt.append((time.perf_counter() - t) * 1000)
    out = {"round_trip_ms_median": round(statistics.median(rtt), 1), "stations": {}}
    for k in keys:
        ts, n = [], 0
        for _ in range(reps):
            t = time.perf_counter()
            rows = await conn.fetch(sql, SOURCE, k, start, end)
            ts.append((time.perf_counter() - t) * 1000)
            n = len(rows)
        out["stations"][k] = {"rows": n, "ms_first": round(ts[0], 1), "ms_median": round(statistics.median(ts), 1), "ms_max": round(max(ts), 1)}
    plan = await conn.fetch("EXPLAIN (ANALYZE, TIMING OFF) " + sql.replace("$1", f"'{SOURCE}'").replace("$2", f"'{keys[0]}'")
                            .replace("$3", f"'{start.isoformat()}'").replace("$4", f"'{end.isoformat()}'"))
    out["server_planning_ms_first_station"] = next((float(r[0].split(":")[1].split()[0]) for r in plan if r[0].strip().startswith("Planning Time")), None)
    out["server_execution_ms_first_station"] = next((float(r[0].split(":")[1].split()[0]) for r in plan if r[0].strip().startswith("Execution Time")), None)
    return out


async def db_facts(conn) -> dict:
    f = {"version": await conn.fetchval("SELECT version()"),
         "timescaledb": await conn.fetchval("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"),
         "extension_schema": await conn.fetchval("SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'timescaledb'"),
         "database_bytes": int(await conn.fetchval("SELECT pg_database_size(current_database())")),
         "schemas": [r[0] for r in await conn.fetch("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema' ORDER BY 1")],
         "tables_outside_dm_measure": [f"{r[0]}.{r[1]}:{r[2]}" for r in await conn.fetch(
             "SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname <> 'dm_measure' ORDER BY 1, 2")]}
    try:
        f["license"] = await conn.fetchval("SHOW timescaledb.license")
    except Exception:
        f["license"] = None
    return f


async def variant(conn, name: str, profile: str, n_rows: int, chunk_days: int, seed: int) -> dict:
    """One throwaway hypertable shaped like pipeline_observations: load, size, compress, size, read, drop."""
    await conn.execute(f"CREATE TABLE {SCHEMA}.{name} (LIKE {SCHEMA}.pipeline_observations INCLUDING ALL)")
    await conn.execute(f"SELECT create_hypertable('{SCHEMA}.{name}', 'observed_at', chunk_time_interval => INTERVAL '{chunk_days} days')")
    await conn.execute(f"ALTER TABLE {SCHEMA}.{name} SET (timescaledb.compress, timescaledb.compress_segmentby = 'source, station_key')")
    rows, secs, keys = await copy_load(conn, name, gen_blocks(profile, n_rows, seed))
    out = {"profile": profile, "chunk_days": chunk_days, "copy_rows": rows, "copy_seconds": round(secs, 1), "copy_rows_per_s": round(rows / secs),
           "uncompressed": await sizes(conn, name)}
    out["compression"] = await compress_all(conn, name)
    out["compressed"] = await sizes(conn, name)
    out["compression_ratio"] = round(out["uncompressed"]["total_bytes"] / max(out["compressed"]["total_bytes"], 1), 1)
    out["read_station_year_compressed"] = await read_station_year(conn, name, keys[:1], reps=3) if profile == "hourly" else None
    await conn.execute(f"DROP TABLE {SCHEMA}.{name}")
    return out


# ---------------------------------------------------------------- main

async def main(args) -> None:
    url = load_url(args.env_file, args.var)
    admin = await connect(url)
    try:
        R["before"] = await db_facts(admin)
        exists = await admin.fetchval("SELECT 1 FROM pg_namespace WHERE nspname = $1", SCHEMA)
        R["schema_existed_before"] = bool(exists)
        print(json.dumps({"before": R["before"]}, indent=1, default=str))
        if args.precheck_only:
            return
        if exists:
            raise SystemExit(f"schema {SCHEMA} already exists; refusing to touch it")
        if R["before"]["database_bytes"] > args.max_existing_mb * 1024 * 1024 and not args.force_size:
            raise SystemExit(f"database already holds {R['before']['database_bytes'] / 1e6:.0f} MB (limit {args.max_existing_mb} MB); not loading 4 M rows on top")
        await admin.execute(f"CREATE SCHEMA {SCHEMA}")
    finally:
        await admin.close()

    engine = create_async_engine(sa_url(url))

    @event.listens_for(engine.sync_engine, "connect")
    def _set_path(dbapi_conn, _rec):                       # after connecting, not as a startup parameter
        cur = dbapi_conn.cursor()
        cur.execute(f"SET search_path = {SCHEMA},public")
        cur.execute("SET statement_timeout = 0")
        cur.close()

    conn = None
    try:
        # 1. tables, then the real ensure_timescale once (unqualified names resolve to dm_measure through the search path)
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all, checkfirst=False)
        cap: list = []

        class _H(logging.Handler):
            def emit(self, rec):
                cap.append(rec.getMessage())
        logging.getLogger("backend.app.pipeline.store").addHandler(_H())
        t = time.perf_counter()
        done = await store.ensure_timescale(engine)
        R["ensure_timescale"] = {"steps_succeeded": done, "of": ["extension", "hypertable", "chunk_interval", "compression", "compression_policy"], "warnings": cap,
                                 "seconds": round(time.perf_counter() - t, 1)}
        print("ensure_timescale:", R["ensure_timescale"], flush=True)

        conn = await connect(url, f"{SCHEMA},public")
        R["hypertable_info"] = {
            "hypertable": [dict(r) for r in await conn.fetch("SELECT hypertable_schema, hypertable_name, compression_enabled FROM timescaledb_information.hypertables WHERE hypertable_schema = $1", SCHEMA)],
            "dimension": [dict(r) for r in await conn.fetch("SELECT column_name, time_interval FROM timescaledb_information.dimensions WHERE hypertable_schema = $1", SCHEMA)],
            "compression_settings": [dict(r) for r in await conn.fetch("SELECT * FROM timescaledb_information.compression_settings WHERE hypertable_schema = $1", SCHEMA)],
            "jobs": [dict(r) for r in await conn.fetch("SELECT job_id, proc_name, schedule_interval, config FROM timescaledb_information.jobs WHERE hypertable_schema = $1", SCHEMA)],
            "column_types": {r[0]: r[1] for r in await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = $1 AND table_name = 'pipeline_observations'", SCHEMA)}}
        print("hypertable:", json.dumps(R["hypertable_info"], default=str), flush=True)
        # the 7-day policy would compress chunks in the background while measuring; remove it, the measurement compresses by hand
        if R["ensure_timescale"]["steps_succeeded"][-1:] == ["compression_policy"]:
            await conn.execute("SELECT remove_compression_policy('pipeline_observations')")
            R["policy_removed_for_measurement"] = True

        # 2. ingest speed on 100,000 rows: COPY versus the application path (store.insert_observations, 2,000 rows per statement)
        sample = 100_000
        if not args.qc_only:
            rows, secs, _ = await copy_load(conn, "pipeline_observations", gen_blocks("hourly", sample, 1, source="copytest"))
            R["ingest_100k"] = {"copy_rows_per_s": round(rows / secs), "copy_seconds": round(secs, 1)}
            await conn.execute("TRUNCATE pipeline_observations")
            recs = [dict(zip(COLS, r)) for blk, _ in gen_blocks("hourly", sample, 1, source="insertpath") for r in blk]
            t = time.perf_counter()
            async with AsyncSession(engine) as s:
                await store.insert_observations(s, recs)
                await s.commit()
            secs = time.perf_counter() - t
            R["ingest_100k"].update({"app_insert_rows_per_s": round(sample / secs), "app_insert_seconds": round(secs, 1)})
            await conn.execute("TRUNCATE pipeline_observations")
            print("ingest_100k:", R["ingest_100k"], flush=True)

        # 3. the 4,000,000-row load by COPY and the uncompressed size
        t0 = time.perf_counter()
        rows, secs, keys = await copy_load(conn, "pipeline_observations", gen_blocks("hourly", args.rows, 42))
        R["load_main"] = {"rows": rows, "stations": len(keys), "copy_seconds": round(secs, 1), "copy_rows_per_s": round(rows / secs),
                          "wall_seconds_with_generation": round(time.perf_counter() - t0, 1)}
        print("load_main:", R["load_main"], flush=True)
        await conn.execute("ANALYZE pipeline_observations")
        R["main_uncompressed"] = await sizes(conn, "pipeline_observations")
        print("main_uncompressed:", R["main_uncompressed"], flush=True)
        read_keys = [keys[0], keys[len(keys) // 2], keys[-2]]
        R["read_uncompressed"] = await read_station_year(conn, "pipeline_observations", read_keys)
        print("read_uncompressed:", R["read_uncompressed"], flush=True)

        # 4. compression
        R["main_compress"] = await compress_all(conn, "pipeline_observations")
        R["main_compressed"] = await sizes(conn, "pipeline_observations")
        R["compression_ratio"] = round(R["main_uncompressed"]["total_bytes"] / max(R["main_compressed"]["total_bytes"], 1), 1)
        print("main_compressed:", R["main_compress"], R["main_compressed"], R["compression_ratio"], flush=True)
        R["read_compressed"] = await read_station_year(conn, "pipeline_observations", read_keys)
        print("read_compressed:", R["read_compressed"], flush=True)

        # 5. idempotent re-ingest into compressed chunks (ON CONFLICT DO NOTHING): same keys with other values must not change anything
        idem: dict = {}
        first = [dict(zip(COLS, r)) for r in next(gen_blocks("hourly", 2000, 42))[0]]
        before_n = await conn.fetchval("SELECT count(*) FROM pipeline_observations")
        before_v = await conn.fetchval("SELECT sum(value_mm) FROM pipeline_observations WHERE station_key = $1", first[0]["station_key"])
        try:
            changed = [dict(r, value_mm=r["value_mm"] + 1000.0) for r in first]
            t = time.perf_counter()
            async with AsyncSession(engine) as s:
                await store.insert_observations(s, changed)
                await s.commit()
            idem["conflicting_reinsert_seconds"] = round(time.perf_counter() - t, 2)
            idem["rows_after_conflicting_reinsert_unchanged"] = (await conn.fetchval("SELECT count(*) FROM pipeline_observations")) == before_n
            idem["values_after_conflicting_reinsert_unchanged"] = (await conn.fetchval("SELECT sum(value_mm) FROM pipeline_observations WHERE station_key = $1", first[0]["station_key"])) == before_v
        except Exception as exc:
            idem["conflicting_reinsert_error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"
        try:
            new = [dict(r, station_key="SYNNEW00", source=SOURCE) for r in first]
            async with AsyncSession(engine) as s:
                await store.insert_observations(s, new)
                await s.commit()
            idem["new_rows_into_compressed_range_inserted"] = (await conn.fetchval("SELECT count(*) FROM pipeline_observations WHERE station_key = 'SYNNEW00'")) == 2000
        except Exception as exc:
            idem["new_rows_error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"
        R["idempotent_reingest_on_compressed_chunks"] = idem
        print("idempotent:", idem, flush=True)

        # 6. current run and result tables: run the real qc on the first N stations (read back through the ORM, from compressed chunks)
        n = args.qc_stations
        rng = np.random.default_rng(7)
        st_rows = [{"station_key": k, "source": SOURCE, "name": f"synthetic {k}", "state": "SYNTHETIC", "district": None,
                    "latitude": float(22 + rng.random() * 1.5), "longitude": float(78 + rng.random() * 1.5)} for k in keys[:n]]
        async with AsyncSession(engine) as s:
            await store.upsert_stations(s, st_rows)
            await s.commit()
        t = time.perf_counter()
        try:
            async with AsyncSession(engine, expire_on_commit=False) as s:
                run = await qc.run_qc(s, SOURCE)
                run_id, n_rows = run.id, run.n_rows
            qc_secs = time.perf_counter() - t
            tbl = {}
            for name in ("validation_runs", "validation_results", "validation_check_hits"):
                r = await conn.fetchrow(f"SELECT count(*) AS n, pg_table_size('{name}') AS tbl, pg_indexes_size('{name}') AS idx, pg_total_relation_size('{name}') AS total FROM {name}")
                tbl[name] = {"rows": r["n"], "table_bytes": int(r["tbl"]), "index_bytes": int(r["idx"]), "total_bytes": int(r["total"]),
                             "bytes_per_row_total": round(r["total"] / max(r["n"], 1), 1)}
            res_total = sum(tbl[k]["total_bytes"] for k in tbl)
            R["qc_tables"] = {"stations": n, "result_rows": n_rows, "seconds": round(qc_secs, 1), "tables": tbl, "all_three_bytes": res_total,
                              "bytes_per_station_day_all_three": round(res_total / max(n_rows, 1), 1),
                              "hours_per_result_row": round(R["load_main"]["rows"] / R["load_main"]["stations"] * n / max(n_rows, 1), 1)}
            print("qc_tables:", R["qc_tables"], flush=True)
        except Exception as exc:
            R["qc_error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
            print("qc_error:", R["qc_error"], flush=True)

        # 7. other value pattern and chunk length (1,000,000 rows each, throwaway tables)
        R["variants"] = {}
        if args.variants:                                   # e.g. "wet_only:30,wet_only:90"
            plan = [(f"v_{p.split(':')[0]}{p.split(':')[1]}", p.split(":")[0], int(p.split(":")[1])) for p in args.variants.split(",")]
        else:
            plan = [] if args.qc_only else [("v_wet7", "wet_only", 7), ("v_wet365", "wet_only", 365), ("v_hourly365", "hourly", 365)]
        for name, profile, days in plan:
            R["variants"][name] = await variant(conn, name, profile, 1_000_000, days, 11)
            print(name, R["variants"][name], flush=True)
    finally:
        if conn is not None:
            await conn.close()
        await engine.dispose()
        fin = await connect(url)
        try:
            await fin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
            R["after"] = await db_facts(fin)
            R["schema_dropped"] = not await fin.fetchval("SELECT 1 FROM pg_namespace WHERE nspname = $1", SCHEMA)
            R["jobs_left_for_schema"] = await fin.fetchval("SELECT count(*) FROM timescaledb_information.jobs WHERE hypertable_schema = $1", SCHEMA)
        finally:
            await fin.close()
        if args.out:
            Path(args.out).write_text(json.dumps(R, indent=1, default=str), encoding="utf-8")
        print("schema_dropped:", R.get("schema_dropped"), "jobs_left:", R.get("jobs_left_for_schema"), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--var", default="DATABASE_URL")
    ap.add_argument("--out")
    ap.add_argument("--rows", type=int, default=4_000_000)
    ap.add_argument("--qc-stations", type=int, default=60)
    ap.add_argument("--max-existing-mb", type=int, default=150)
    ap.add_argument("--force-size", action="store_true")
    ap.add_argument("--precheck-only", action="store_true")
    ap.add_argument("--variants", help="profile:chunk_days list of 1M-row variants to measure instead of the default three")
    ap.add_argument("--qc-only", action="store_true", help="skip the 100k ingest comparison and the 1M-row variants (use with a small --rows)")
    a = ap.parse_args()
    try:
        asyncio.run(main(a))
    except SystemExit:
        raise
    except Exception as exc:                                  # never echo more than the first line of an error (no connection strings)
        print(f"FAILED: {type(exc).__name__}: {str(exc).splitlines()[0][:300]}")
        sys.exit(1)
