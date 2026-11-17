import pytest

from training.paths import resolve_data_dir, resolve_out_dir


def _rf25(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "RF25_ind2000_rfp25.nc").write_bytes(b"")
    return folder


def test_explicit_dir_holding_the_files(tmp_path, monkeypatch):
    monkeypatch.delenv("DATAMEND_DATA_DIR", raising=False)
    d = _rf25(tmp_path / "anywhere")
    assert resolve_data_dir(str(d)) == d


def test_data_root_with_rf25_subfolder(tmp_path, monkeypatch):
    monkeypatch.delenv("DATAMEND_DATA_DIR", raising=False)
    root = tmp_path / "data"
    d = _rf25(root / "rf25")
    assert resolve_data_dir(str(root)) == d


def test_env_var_may_be_the_data_root(tmp_path, monkeypatch):
    root = tmp_path / "bigdisk"
    d = _rf25(root / "rf25")
    monkeypatch.setenv("DATAMEND_DATA_DIR", str(root))
    assert resolve_data_dir(None) == d


def test_explicit_dir_without_files_falls_through_to_env(tmp_path, monkeypatch):
    d = _rf25(tmp_path / "real")
    monkeypatch.setenv("DATAMEND_DATA_DIR", str(d))
    assert resolve_data_dir(str(tmp_path / "empty")) == d


def test_out_dir_uses_env_root_for_relative_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAMEND_OUT_DIR", str(tmp_path))
    assert resolve_out_dir("run1") == str(tmp_path / "run1")
    assert resolve_out_dir(str(tmp_path / "abs")) == str(tmp_path / "abs")
