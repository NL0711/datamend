"""End-to-end smoke of a LOCAL DataMend: backend + AI narrator (MCP) on throwaway ports and a throwaway SQLite database, then every feature through HTTP.

    python scripts/smoke_local.py

Nothing here touches your .env, your database or a real service: the environment is built from scratch (no Weather Union key, no Gemini or
Anthropic key, no Kaggle or S3 call). It prints PASS or FAIL per check and exits 1 on any FAIL. Standard library only.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "smoke-admin-token"
NARRATOR_TOKEN = "smoke-narrator-token"
RESULTS: list = []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(base, method, path, body=None, files=None, token=ADMIN_TOKEN, raw=False):
    headers = {"X-Admin-Token": token} if token else {}
    data = None
    if files is not None:
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in (body or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for k, (name, content) in files.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\nContent-Type: text/csv\r\n\r\n'.encode() + content + b"\r\n")
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload or b"null"))
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, payload.decode(errors="replace")[:200]


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))


def daily_csv() -> bytes:
    """Four years of daily rain at four stations with a shared wet pattern, one huge spike and a stuck stretch. GENERATED."""
    rng = random.Random(3)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["station_id", "day", "rain_mm", "latitude", "longitude"])
    st = [("A1", 12.97, 77.59), ("A2", 13.02, 77.62), ("B1", 19.07, 72.87), ("B2", 19.11, 72.90)]
    d0 = date(2021, 1, 1)
    for i in range(1000):
        d = d0 + timedelta(days=i)
        season = 1 + math.sin((d.timetuple().tm_yday - 150) / 365 * 2 * math.pi)
        shared = rng.random() < 0.25 * max(season, 0.05)
        for sid, la, lo in st:
            mm = round(rng.expovariate(1 / 8), 1) if shared and rng.random() < 0.85 else 0.0
            if sid == "A1" and i == 700:
                mm = 600.0                                      # a spike no neighbour agrees with
            if sid == "B2" and 300 <= i < 330:
                mm = 4.0                                        # a stuck value
            w.writerow([sid, d.isoformat(), mm, la, lo])
    return out.getvalue().encode()


def reading_csv() -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["station_id", "timestamp", "rain_accumulation", "rain_intensity"])
    for i in range(60):
        w.writerow(["R1", f"2026-03-01T{(i // 4):02d}:{(i % 4) * 15:02d}:00Z", round(i * 0.1, 1), 0.2])
    return out.getvalue().encode()


def wait_up(url, secs=60):
    end = time.time() + secs
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="datamend_smoke_"))
    bport, nport = free_port(), free_port()
    base = f"http://127.0.0.1:{bport}"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("WEATHER_UNION", "GEMINI", "ANTHROPIC", "KAGGLE", "FEED_HISTORY", "NARRATOR", "ADMIN_", "EVIDENCE"))}
    env.update(DATABASE_URL="sqlite+aiosqlite:///" + (tmp / "smoke.db").as_posix(), RUNTIME_SETTINGS_PATH=str(tmp / "rt.json"),
               FEED_HISTORY_PATH=str(tmp / "feed.db"), ADMIN_TOKEN=ADMIN_TOKEN, ADMIN_EMAIL="smoke@example.com",
               ADMIN_PASSWORD="smoke-pass", NARRATOR_URL=f"http://127.0.0.1:{nport}/narrate", NARRATOR_TOKEN=NARRATOR_TOKEN, NARRATOR_ALLOW_PRIVATE="true",
               PYTHONUNBUFFERED="1")
    # .env is read by the backend too, and an environment variable that is merely absent does not stop it: blank every secret and service setting
    # (as tests/conftest.py does) so a real key, a real feed or a hosted database can never be used by this script.
    env.update({name: "" for name in ("WEATHER_UNION_API_KEY", "WEATHER_UNION_CITY", "GEMINI_API_KEY", "FEED_HISTORY_URL", "KAGGLE_USERNAME", "KAGGLE_KEY",
                                      "EVIDENCE_API_TOKEN", "SCORE_EXPORT_PATH")})
    nenv = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC", "DATAMEND_", "NARRATOR", "MCP_"))}
    nenv.update(DATAMEND_BASE_URL=base, DATAMEND_ADMIN_TOKEN=ADMIN_TOKEN, NARRATOR_BEARER_TOKEN=NARRATOR_TOKEN, NARRATOR_PORT=str(nport),
                MCP_AUDIT_LOG=str(tmp / "mcp_audit.jsonl"), PYTHONUNBUFFERED="1")
    logs = {n: open(tmp / f"{n}.log", "w") for n in ("backend", "narrator")}
    backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(bport)], cwd=ROOT, env=env, stdout=logs["backend"], stderr=subprocess.STDOUT)
    narrator = subprocess.Popen([sys.executable, "-m", "datamend_mcp", "narrator"], cwd=ROOT / "mcp-service", env=nenv, stdout=logs["narrator"], stderr=subprocess.STDOUT)
    try:
        check("backend starts", wait_up(base + "/"), f"see {tmp / 'backend.log'}")
        check("narrator starts", wait_up(f"http://127.0.0.1:{nport}/health"), f"see {tmp / 'narrator.log'}")
        s, body = call(base, "GET", "/api/validation/runs", token="")
        check("signed-out reads are refused", s == 401, str(s))
        s, body = call(base, "POST", "/api/auth/login", {"email": "smoke@example.com", "password": "smoke-pass"}, token="")
        check("sign-in works", s == 200 and "token" in body, str(body)[:100])

        # data import
        s, run = call(base, "POST", "/api/validation/runs", {"profile": "daily", "synthetic": "true"}, files={"file": ("daily.csv", daily_csv())})
        check("daily CSV upload makes a run", s == 201 and run.get("n_rows") == 4000 and run.get("status") == "completed", f"{s} {str(run)[:150]}")
        rid = run.get("id")
        s, r2 = call(base, "POST", "/api/validation/runs", {"profile": "reading", "accumulation_mode": "cumulative"}, files={"file": ("reading.csv", reading_csv())})
        check("reading CSV upload makes a run", s == 201 and r2.get("n_rows") == 60, f"{s} {str(r2)[:150]}")
        s, bad = call(base, "POST", "/api/validation/runs", {"profile": "daily"}, files={"file": ("bad.csv", b"x,y\n1,2\n")})
        check("a file with the wrong columns is rejected with a reason", s == 422, f"{s} {str(bad)[:120]}")
        s, k = call(base, "POST", "/api/validation/runs/kaggle", {"url": "https://example.com/not-kaggle", "profile": "daily"})
        check("a non-Kaggle link is refused", s in (400, 422), f"{s} {str(k)[:120]}")

        # reading back
        s, runs = call(base, "GET", "/api/validation/runs")
        check("runs list", s == 200 and len(runs["runs"]) >= 2)
        s, rows = call(base, "GET", f"/api/validation/runs/{rid}/rows?scope=all&page_size=50")
        check("rows page", s == 200 and rows["total"] == 4000, str(rows)[:100])
        s, flagged = call(base, "GET", f"/api/validation/runs/{rid}/rows?page_size=5")
        row_id = flagged["rows"][0]["id"] if s == 200 and flagged["rows"] else None
        check("the checks flag something in the generated data", row_id is not None, f"flagged total {flagged.get('total') if isinstance(flagged, dict) else flagged}")
        if row_id:
            s, ev = call(base, "GET", f"/api/validation/runs/{rid}/rows/{row_id}/evidence")
            check("evidence of a flagged row", s == 200 and ev["evidence"], str(ev)[:100])
            s, ex = call(base, "POST", f"/api/validation/runs/{rid}/rows/{row_id}/explain", {"generator": "baseline"})
            check("baseline explanation", s == 201 and ex["explanations"][0]["generated"] is True, f"{s} {str(ex)[:120]}")
            s, nx = call(base, "POST", f"/api/validation/runs/{rid}/rows/{row_id}/explain", {"generator": "narrator"})
            check("AI narrator explanation through MCP", s == 201 and nx["explanations"][0]["generator"] == "mcp-narrator", f"{s} {str(nx)[:200]}")
            s, ch = call(base, "POST", f"/api/validation/runs/{rid}/chat", {"message": "How many rows were flagged in this run?", "row_id": row_id})
            check("AI chat answers a question about the run", s == 201 and ch.get("text"), f"{s} {str(ch)[:200]}")
            s, rv = call(base, "POST", f"/api/validation/runs/{rid}/rows/{row_id}/review", {"decision": "needs_followup", "note": "smoke"})
            check("a review is saved (admin)", s == 201, f"{s} {str(rv)[:100]}")
            s, rv = call(base, "POST", f"/api/validation/runs/{rid}/rows/{row_id}/review", {"decision": "needs_followup"}, token="wrong")
            check("a review without the admin token is refused", s in (401, 403), str(s))
        s, st_ = call(base, "GET", "/api/validation/narrator")
        check("narrator status says connected", s == 200 and st_.get("connected") is True, str(st_)[:120])
        s, ser = call(base, "GET", f"/api/validation/runs/{rid}/series?station=A1")
        check("station series", s == 200 and ser.get("points"), str(ser)[:100])
        for path, name in ((f"/api/validation/runs/{rid}/export.json", "JSON export"), (f"/api/validation/runs/{rid}/export.csv", "CSV export")):
            s, b = call(base, "GET", path, raw=True)
            check(name, s == 200 and len(b) > 100, str(s))

        # the weather provider setting (no city, so no feed starts and nothing is fetched)
        s, st = call(base, "GET", "/api/settings")
        check("settings list both weather providers", s == 200 and {p["id"] for p in st["providers"]} == {"weather_union", "open_meteo"}, str(st)[:120])
        s, st = call(base, "PUT", "/api/settings", {"weather_provider": "open_meteo"})
        check("the weather provider can be switched to Open-Meteo without a key", s == 200 and st["weather_union"]["provider"] == "open_meteo" and st["weather_union"]["key_required"] is False, f"{s} {str(st)[:150]}")
        s, st = call(base, "PUT", "/api/settings", {"weather_provider": "weather_union"})
        check("and back to Weather Union", s == 200 and st["weather_union"]["provider"] == "weather_union", str(s))

        # the platform's own MCP endpoint, used by a real MCP client over a real socket (Anshu's HttpMcpClient)
        s, tok = call(base, "POST", "/api/settings/mcp/tokens", {"label": "smoke agent"})
        check("an MCP access token is made in Settings", s == 201 and tok.get("token", "").startswith("dmcp_"), f"{s} {str(tok)[:100]}")
        sys.path.insert(0, str(ROOT / "mcp-service"))
        from datamend_mcp import security as mcp_sec
        from datamend_mcp.mcp_client import HttpMcpClient, McpClientError, vet_tools
        agent = HttpMcpClient(base + "/api/mcp", tok.get("token", ""), 20.0)
        try:
            info = agent.connect()
            check("an external MCP client connects and initializes", info["serverInfo"]["name"] == "datamend-mcp", str(info)[:100])
            tools = vet_tools(agent.list_tools(), mcp_sec.load_lock(str(ROOT / "mcp-service" / "tool_manifest.lock.json")))
            check("its 12 tools match the pinned lock", len(tools) == 12, str(len(tools)))
            runs_text = agent.call_tool("list_runs", {"limit": 5})["text"]
            check("it reads the platform's runs through the tool", f'"id":{rid}' in runs_text.replace(" ", ""), runs_text[:120])
            if row_id:
                ev = agent.call_tool("get_row_evidence", {"run_id": rid, "row_id": row_id})["text"]
                check("it reads a flagged row's evidence", '"check"' in ev, ev[:120])
        except Exception as e:
            check("the MCP session works end to end", False, f"{type(e).__name__}: {e}")
        finally:
            agent.close()
        try:
            HttpMcpClient(base + "/api/mcp", "dmcp_not_a_real_token", 20.0).connect()
            check("a wrong MCP token is refused", False, "connected")
        except McpClientError:
            check("a wrong MCP token is refused", True)
        s, _ = call(base, "DELETE", f"/api/settings/mcp/tokens/{tok.get('id')}")
        try:
            HttpMcpClient(base + "/api/mcp", tok.get("token", ""), 20.0).connect()
            check("a revoked MCP token stops working", False, "connected")
        except McpClientError:
            check("a revoked MCP token stops working", s == 200)

        # the rest of the surface
        for path, name in (("/api/validation/overview", "overview"), ("/api/validation/stations", "station cycle"), ("/api/validation/review/summary", "review summary"),
                           ("/api/validation/review/queue", "review queue"), ("/api/validation/lab/options", "lab options"), ("/api/places/stations", "gauge catalogue"),
                           ("/api/places/map", "map layers"), ("/api/settings", "settings")):
            s, b = call(base, "GET", path)
            check(name, s == 200, f"{s} {str(b)[:100]}")
        s, ins = call(base, "GET", f"/api/validation/insights?run_id={rid}&granularity=month")
        check("insights", s == 200 and all(ins[k].get("enough") for k in ("anomaly", "correlation", "climate", "verdict_mix", "heavy_rain")), f"{s} {[ (k, ins[k].get('reason')) for k in ins if isinstance(ins[k], dict) and ins[k].get('enough') is False]}")
        s, g = call(base, "GET", "/api/rainfall/gauges")
        check("gauge file is off without a feed (503, not a crash)", s == 503, str(s))
        s, f = call(base, "GET", "/api/rainfall/stations")
        check("live feed is off without a key (503, not a crash)", s == 503, str(s))
    finally:
        for p in (backend, narrator):
            p.terminate()
        for p in (backend, narrator):
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        for f in logs.values():
            f.close()
    bad = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)} passed, {len(bad)} failed. logs: {tmp}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
