"""Pushing small notebook results to a separate branch (qc/kaggle_sync.py), against a local bare repository."""

import subprocess
from pathlib import Path

import pytest

from qc.kaggle_sync import SyncError, sync_results


def git(cwd, *a):
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def remote_and_clone(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "ml-training", str(bare)], check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(bare), str(work)], check=True, capture_output=True)
    git(work, "config", "user.name", "dev")
    git(work, "config", "user.email", "dev@example.com")
    (work / "code.py").write_text("print(1)\n")
    (work / "docs").mkdir()
    (work / "docs" / "qc-evaluation-protocol.md").write_text("budgets: not fixed\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "code")
    git(work, "push", "origin", "ml-training")
    return bare, work


def test_results_go_to_their_own_branch_and_the_code_branch_is_untouched(remote_and_clone, tmp_path):
    bare, work = remote_and_clone
    (work / "docs" / "qc-evaluation-protocol.md").write_text("budgets: not fixed\nbudgets chosen: 1 / 5\n")   # as set-budgets would
    rep = tmp_path / "report.md"; rep.write_text("# report\n")
    fig = tmp_path / "f.png"; fig.write_bytes(b"png")
    sha = sync_results(work, str(bare), "base", {rep: "paper/report.md", fig: "paper/figures/f.png"},
                       tracked_text={"docs/qc-evaluation-protocol.md": "budgets: not fixed\nbudgets chosen: 1 / 5\n"})
    assert sha
    assert git(bare, "rev-parse", "--short", "ml-training") != sha                        # the code branch did not move
    tree = git(bare, "ls-tree", "-r", "--name-only", "kaggle-results").split()
    assert "docs/results/base/paper/report.md" in tree and "docs/results/base/paper/figures/f.png" in tree
    assert "code.py" in tree                                                                  # built on the code, not an orphan
    assert "budgets chosen" in git(bare, "show", "kaggle-results:docs/qc-evaluation-protocol.md")
    assert git(bare, "log", "-1", "--format=%an %ae", "kaggle-results") == "datamend-notebook datamend-notebook@users.noreply.github.com"


def test_second_sync_builds_on_the_first_and_nothing_new_is_a_no_op(remote_and_clone, tmp_path):
    bare, work = remote_and_clone
    a = tmp_path / "a.json"; a.write_text("{}")
    first = sync_results(work, str(bare), "base", {a: "a.json"})
    assert sync_results(work, str(bare), "base", {a: "a.json"}) is None                     # same content: nothing to commit
    b = tmp_path / "b.json"; b.write_text("[1]")
    other = tmp_path / "other"                                                                # a fresh clone, as a new notebook session
    subprocess.run(["git", "clone", "--branch", "ml-training", str(bare), str(other)], check=True, capture_output=True)
    second = sync_results(other, str(bare), "base", {b: "b.json"})
    assert second and second != first
    tree = git(bare, "ls-tree", "-r", "--name-only", "kaggle-results").split()
    assert "docs/results/base/a.json" in tree and "docs/results/base/b.json" in tree        # fetched and extended, not replaced
    assert int(git(bare, "rev-list", "--count", "kaggle-results")) == int(git(bare, "rev-list", "--count", "ml-training")) + 2


def test_big_files_are_refused_and_the_token_never_appears_in_errors(remote_and_clone, tmp_path):
    bare, work = remote_and_clone
    big = tmp_path / "big.bin"; big.write_bytes(b"0" * 2_000_000)
    with pytest.raises(SyncError, match="larger than"):
        sync_results(work, str(bare), "base", {big: "big.bin"}, max_mb=1.0)
    with pytest.raises(SyncError) as e:
        small = tmp_path / "s.txt"; small.write_text("x")
        sync_results(work, "https://SECRET123@invalid.invalid/none.git", "base", {small: "s.txt"}, secret="SECRET123")
    assert "SECRET123" not in str(e.value)
