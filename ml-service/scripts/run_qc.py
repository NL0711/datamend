"""Run the rainfall QC pipeline on one machine (any OS) with the RF25 data fetched from Kaggle.

From ml-service/:
    python scripts/run_qc.py check                       # GPU, packages, data download and the 125-file check; no training
    python scripts/run_qc.py phase1 --smoke              # tiny end-to-end wiring run (3 training years, 15 min caps, one seed)
    python scripts/run_qc.py phase1                      # prepare, benchmark, untrained, train, federated, fusion, ablate
    python scripts/run_qc.py budgets --final 1.0 --review 5.0
                                                         # fixes and logs the budgets; then commit the protocol log
    python scripts/run_qc.py test --confirm-test-score   # scores the test years ONCE, builds the paper outputs

Phase 1 stops after the validation curves on purpose. The budgets are fixed from them and cannot change afterwards, and the
test years can be scored only once. Every step is the same `python -m qc <step>` command the Kaggle notebook runs, with the
`single-gpu` profile; finished steps resume or skip. Results go to $DATAMEND_OUT_DIR (default ml-service/artifacts).
Environment: DATAMEND_RF25_DIR is set from the download; DATAMEND_DATA_DIR (splits, benchmark, cache) defaults to ml-service/data.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def qc(step: str, *args: str, profile: str, run: str, extra: list[str]) -> None:
    cmd = [sys.executable, "-u", "-m", "qc", step, *args, "--profile", profile, "--set", f"name={run}"]
    for s in extra:
        cmd += ["--set", s]
    print("\n$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env=os.environ.copy())
    if r.returncode:
        raise SystemExit(f"step '{step}' failed with exit code {r.returncode}")


def setup_data(slug: str, expected: int, copy_to: str | None) -> Path:
    from fetch_rf25 import fetch
    folder = fetch(slug, expected, Path(copy_to) if copy_to else None)
    os.environ["DATAMEND_RF25_DIR"] = str(folder)
    print(f"RF25 folder: {folder}")
    return folder


def hardware() -> str:
    try:
        import torch
    except ImportError:
        print("torch is not installed: install PyTorch for your GPU first (https://pytorch.org), then requirements-train.txt")
        return "single-gpu"
    n = torch.cuda.device_count()
    print(f"torch {torch.__version__} | cuda available: {torch.cuda.is_available()} | GPUs: {n} "
          f"{[torch.cuda.get_device_name(i) for i in range(n)]}")
    if not torch.cuda.is_available():
        print("WARNING: no GPU found; the single-gpu profile falls back to CPU and will be very slow")
    return "single-gpu"          # the kaggle profile is for two T4s driven by --shard; one machine uses single-gpu


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("phase", choices=["check", "phase1", "budgets", "test"])
    ap.add_argument("--slug", default="nathashalewis/majorproj-rainfall", help="Kaggle dataset owner/name")
    ap.add_argument("--expected", type=int, default=125, help="RF25 files that must be present (1901-2025 = 125)")
    ap.add_argument("--copy-to", default=None, help="copy the dataset here instead of using the kagglehub cache")
    ap.add_argument("--run", default="base", help="run name (the smoke run always uses 'smoke')")
    ap.add_argument("--smoke", action="store_true", help="tiny wiring run; the test years are never scored")
    ap.add_argument("--seeds", type=int, nargs="+", default=None, help="default: train.seeds from the config")
    ap.add_argument("--time-cap-hours", type=float, default=None)
    ap.add_argument("--federated", nargs="*", default=["fedpers", "fedavg", "fedft", "local"],
                    help="federated variants to run; pass --federated with no value to skip them")
    ap.add_argument("--no-ablate", action="store_true")
    ap.add_argument("--final", type=float, default=None, help="budgets: final-flag budget, false alerts per 1,000 clean cell-days")
    ap.add_argument("--review", type=float, default=None, help="budgets: review-flag budget (larger than --final)")
    ap.add_argument("--confirm-test-score", action="store_true", help="test: I understand the test years are scored once")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="extra config overrides")
    a = ap.parse_args(argv)

    profile = hardware()
    setup_data(a.slug, a.expected, a.copy_to)
    if a.phase == "check":
        print("check complete: data present and hardware reported. Nothing was trained.")
        return 0

    run = "smoke" if a.smoke else a.run
    seeds = (["--seeds"] + [str(s) for s in a.seeds]) if a.seeds else (["--seeds", "0"] if a.smoke else [])
    cap = (["--max-train-years", "3", "--time-cap-hours", "0.25"] if a.smoke
           else (["--time-cap-hours", str(a.time_cap_hours)] if a.time_cap_hours else []))
    k = dict(profile=profile, run=run, extra=a.set)

    if a.phase == "phase1":
        qc("prepare", **k)
        qc("benchmark", **k)
        qc("untrained", **k)
        qc("train", *seeds, *cap, **k)
        if a.federated:
            qc("federated", "--variants", *a.federated, *seeds, *cap, **k)
        qc("fusion", *seeds, **k)
        if "fedpers" in a.federated:
            qc("fusion", "--on", "fedpers", *seeds, **k)
        if not a.no_ablate:
            qc("ablate", "--seed", str((a.seeds or [0])[0]), **k)
        print(f"\nPhase 1 done. Look at artifacts/qc/{run}/fusion/validation/ (curves_s0.png and curves_s0.json), choose the two "
              "budgets, then run the 'budgets' phase. The budgets cannot be changed after the test years are scored.")
        return 0

    if a.smoke:
        raise SystemExit(f"{a.phase} is refused for a smoke run: the test years are never scored in smoke mode")
    if a.phase == "budgets":
        if a.final is None or a.review is None:
            raise SystemExit("budgets needs --final and --review (false alerts per 1,000 clean cell-days; review larger than final)")
        if not a.review > a.final:
            raise SystemExit("--review must be larger than --final")
        qc("set-budgets", "--final", str(a.final), "--review", str(a.review), "--seed", "0", **k)
        print("\nBudgets are logged in docs/qc-evaluation-protocol.md. COMMIT AND PUSH THAT FILE NOW, then run the 'test' phase. "
              "No test year has been scored yet.")
        return 0
    if not a.confirm_test_score:
        raise SystemExit("test scores the test years ONCE with the budgets already fixed. Re-run with --confirm-test-score to go ahead.")
    qc("test-score", *seeds, **k)
    qc("paper", **k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
