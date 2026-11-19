import pytest

from training.tests.fakedata import write_fake_archive


@pytest.fixture()
def archive_dir(tmp_path):
    return write_fake_archive(tmp_path)
