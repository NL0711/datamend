"""The migrations build the same schema as the models: upgrade a fresh SQLite file, then ask Alembic whether the models have drifted from it.
A model change without a migration makes this fail, which is the point."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, db):
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)


def test_upgrade_head_then_no_drift_and_downgrade_works(tmp_path):
    db = tmp_path / "m.db"
    up = run(["upgrade", "head"], db)
    assert up.returncode == 0, up.stderr[-800:]
    chk = run(["check"], db)
    assert chk.returncode == 0 and "No new upgrade operations" in (chk.stdout + chk.stderr), (chk.stdout + chk.stderr)[-800:]
    down = run(["downgrade", "base"], db)
    assert down.returncode == 0, down.stderr[-800:]
