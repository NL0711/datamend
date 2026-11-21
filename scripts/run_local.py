"""Start DataMend locally with the AI narrator (the MCP service in mcp-service/) already connected: backend on 8000, narrator on 8790, and the
dashboard dev server on 5199. Uses your .env (database, Weather Union key and so on) like a normal start.

    python scripts/run_local.py            # backend + narrator + dashboard
    python scripts/run_local.py --no-web   # without the dashboard dev server

The narrator reads the platform through its REST API, so it needs a credential: ADMIN_TOKEN from your .env is used when set, otherwise a random
one is made for this run and given to both processes (environment variables outrank .env). The narrator runs in grounded mode unless
ANTHROPIC_API_KEY is set (then a model writes the answers; evidence leaves your machine, see mcp-service/README.md). Ctrl+C stops all three.
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dotenv_value(name: str) -> str:
    env = ROOT / ".env"
    if not env.is_file():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-web", action="store_true", help="do not start the dashboard dev server")
    ap.add_argument("--backend-port", type=int, default=8000)
    ap.add_argument("--narrator-port", type=int, default=8790)
    args = ap.parse_args()

    admin = os.environ.get("ADMIN_TOKEN") or dotenv_value("ADMIN_TOKEN") or secrets.token_urlsafe(32)
    narrator_token = os.environ.get("NARRATOR_TOKEN") or dotenv_value("NARRATOR_TOKEN") or secrets.token_urlsafe(32)
    base = f"http://127.0.0.1:{args.backend_port}"

    backend_env = {**os.environ, "ADMIN_TOKEN": admin, "NARRATOR_URL": f"http://127.0.0.1:{args.narrator_port}/narrate",
                   "NARRATOR_TOKEN": narrator_token, "NARRATOR_ALLOW_PRIVATE": "true"}
    narrator_env = {**os.environ, "DATAMEND_BASE_URL": base, "DATAMEND_ADMIN_TOKEN": admin, "NARRATOR_BEARER_TOKEN": narrator_token,
                    "NARRATOR_PORT": str(args.narrator_port)}
    procs = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(args.backend_port)], cwd=ROOT, env=backend_env),
        subprocess.Popen([sys.executable, "-m", "datamend_mcp", "narrator"], cwd=ROOT / "mcp-service", env=narrator_env),
    ]
    if not args.no_web:
        npm = shutil.which("npm")
        if npm is None:
            print("npm not found: the dashboard dev server is not started (use --no-web to silence this)")
        else:
            procs.append(subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "frontend"))
    print(f"backend {base}  narrator http://127.0.0.1:{args.narrator_port}  dashboard http://localhost:5199/#/login   (Ctrl+C stops all)")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("a process exited; stopping the others")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
