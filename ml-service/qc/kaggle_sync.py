"""Push the small results of a notebook run back to the git repository, so the code and the results are coordinated
through git (used by ``notebooks/datamend_qc_kaggle.ipynb``, opt-in).

Rules this module keeps:
  * Results go to their own branch (default ``kaggle-results``) under ``docs/results/<run>/``. The branch that holds the
    code (``ml-training``) is never written to.
  * Never a force push. If the remote branch exists it is fetched first and the new commit is built on top of it.
  * Only the files it is given are added (reports, metrics, tables, figures, the budget log), never checkpoints, scores
    or data. Each file must be under ``max_mb``.
  * The access token is only used inside the remote URL for one command and is replaced by *** in everything raised
    or returned. The commit author is a generic notebook identity.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

IDENTITY = ("datamend-notebook", "datamend-notebook@users.noreply.github.com")


class SyncError(RuntimeError):
    pass


def _git(repo: Path, args, secret: str = "", check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if secret:
        out = out.replace(secret, "***")
    if check and r.returncode:
        shown = " ".join(args)
        raise SyncError(f"git {shown.replace(secret, '***') if secret else shown} failed: {out[-600:]}")
    return out if r.returncode == 0 else ""


def sync_results(repo: Path, remote_url: str, run: str, files: Dict[Path, str], branch: str = "kaggle-results",
                 tracked_text: Optional[Dict[str, str]] = None, message: Optional[str] = None, secret: str = "",
                 max_mb: float = 50.0) -> Optional[str]:
    """Commit ``files`` (source path -> path relative to ``docs/results/<run>/``) and ``tracked_text`` (repo-relative
    path -> text, e.g. the protocol document with the budget log) to ``branch`` and push it. Returns the commit hash, or
    None if there was nothing new."""
    repo = Path(repo)
    for src in files:
        if Path(src).stat().st_size > max_mb * 1e6:
            raise SyncError(f"{src} is larger than {max_mb} MB: not adding it to git")
    _git(repo, ["config", "user.name", IDENTITY[0]])
    _git(repo, ["config", "user.email", IDENTITY[1]])
    # fetch the results branch if it already exists, so the new commit sits on top of it
    exists = _git(repo, ["ls-remote", "--heads", remote_url, branch], secret, check=False).strip() != ""
    saved = {rel: text for rel, text in (tracked_text or {}).items()}
    if exists:
        _git(repo, ["fetch", remote_url, branch], secret)
        _git(repo, ["checkout", "-f", "-B", branch, "FETCH_HEAD"], secret)
    else:
        _git(repo, ["checkout", "-f", "-B", branch], secret)
    dest_root = repo / "docs" / "results" / run
    added = []
    for src, rel in files.items():
        dst = dest_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        added.append(str(dst.relative_to(repo)))
    for rel, text in saved.items():
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        added.append(rel)
    if not added:
        return None
    _git(repo, ["add", "--", *added], secret)
    if not _git(repo, ["status", "--porcelain"], secret, check=False).strip():
        return None
    _git(repo, ["commit", "-m", message or f"results: notebook run {run}"], secret)
    sha = _git(repo, ["rev-parse", "--short", "HEAD"], secret)
    _git(repo, ["push", remote_url, f"HEAD:refs/heads/{branch}"], secret)        # never --force
    return sha
