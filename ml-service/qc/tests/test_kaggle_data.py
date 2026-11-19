"""Finding the RF25 files from a Kaggle dataset link (qc/kaggle_data.py), on fake input trees."""

from pathlib import Path

import pytest

from qc.kaggle_data import DatasetNotFound, Handle, find_saved_outputs, locate_rf25, parse_dataset_link


def _files(folder: Path, n: int, first: int = 1901):
    folder.mkdir(parents=True, exist_ok=True)
    for y in range(first, first + n):
        (folder / f"RF25_ind{y}_rfp25.nc").write_bytes(b"x")


@pytest.mark.parametrize("link", [
    "https://www.kaggle.com/datasets/someone/rf25-india",
    "https://www.kaggle.com/datasets/someone/rf25-india/versions/3",
    "https://www.kaggle.com/datasets/someone/rf25-india/data?select=RF25_ind1901_rfp25.nc",
    "kaggle.com/someone/rf25-india",
    "someone/rf25-india",
    "  someone/rf25-india  ",
])
def test_link_forms(link):
    assert parse_dataset_link(link) == Handle("someone", "rf25-india")


def test_bad_links_and_local_paths():
    assert parse_dataset_link("/kaggle/input/rf25-india") is None
    for bad in ("", "https://www.kaggle.com/competitions/titanic", "not a link", "https://example.com/a/b"):
        with pytest.raises(DatasetNotFound):
            parse_dataset_link(bad)


def test_finds_the_mount_by_name_in_any_layout(tmp_path):
    for layout in ("rf25-india", "someone/rf25-india", "datasets/someone/rf25-india", "rf25-india/Rainfall_IMD_1901_2023"):
        root = tmp_path / layout.replace("/", "_")
        _files(root / layout, 5)
        got = locate_rf25("https://www.kaggle.com/datasets/someone/rf25-india", root, expected_files=5)
        assert got.is_dir() and len(list(got.glob("RF25_ind*_rfp25.nc"))) == 5


def test_a_single_other_folder_is_used_but_two_are_ambiguous(tmp_path):
    _files(tmp_path / "weird-name", 4)
    assert locate_rf25("someone/rf25-india", tmp_path).name == "weird-name"
    _files(tmp_path / "another-dataset", 4)
    with pytest.raises(DatasetNotFound, match="other folders"):
        locate_rf25("someone/rf25-india", tmp_path)
    assert locate_rf25("someone/another-dataset", tmp_path).name == "another-dataset"        # named one wins


def test_not_attached_says_how_to_attach_and_download_is_a_fallback(tmp_path):
    with pytest.raises(DatasetNotFound, match="Add Input"):
        locate_rf25("someone/rf25-india", tmp_path)
    cache = tmp_path / "downloaded"
    _files(cache / "deep", 3)
    assert locate_rf25("someone/rf25-india", tmp_path / "input", download=lambda slug: str(cache)).name == "deep"


def test_too_few_files_is_an_error_not_a_silent_partial_dataset(tmp_path):
    _files(tmp_path / "rf25-india", 60)
    with pytest.raises(DatasetNotFound, match="expected 123"):
        locate_rf25("someone/rf25-india", tmp_path, expected_files=123)


def test_local_path_link(tmp_path):
    _files(tmp_path / "mine", 3)
    assert locate_rf25(str(tmp_path / "mine")) == tmp_path / "mine"
    with pytest.raises(DatasetNotFound):
        locate_rf25(str(tmp_path / "empty"))


def test_saved_outputs_found_for_resuming(tmp_path):
    out = tmp_path / "my-run-output" / "artifacts" / "qc"
    out.mkdir(parents=True)
    assert find_saved_outputs("me/my-run-output", tmp_path) == tmp_path / "my-run-output"
    assert find_saved_outputs("me/something-else", tmp_path / "nothing") is None
