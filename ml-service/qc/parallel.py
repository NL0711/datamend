"""Run several commands at once and stream their output with a prefix (used by the Kaggle notebook to run one
``python -m qc train --shard I/N`` per GPU). The commands are independent, so a failure in one does not stop the others;
all return codes are reported."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence


def run_parallel(commands: Sequence[Sequence[str]], cwd: Optional[Path] = None, labels: Optional[Sequence[str]] = None,
                 write: Callable[[str], None] = lambda s: (sys.stdout.write(s), sys.stdout.flush())) -> List[int]:
    """Start every command, print each output line as ``[label] line``, wait for all, return the exit codes in order."""
    labels = list(labels) if labels else [f"proc{i}" for i in range(len(commands))]
    lock = threading.Lock()
    procs = [subprocess.Popen(list(c), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
             for c in commands]

    def pump(p, label):
        for line in p.stdout:
            with lock:
                write(f"[{label}] {line}" if line.endswith("\n") else f"[{label}] {line}\n")

    threads = [threading.Thread(target=pump, args=(p, lab), daemon=True) for p, lab in zip(procs, labels)]
    for t in threads:
        t.start()
    codes = [p.wait() for p in procs]
    for t in threads:
        t.join()
    return codes
