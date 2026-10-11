from pathlib import Path

from warrant.config import data_dir

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_data_dir_follows_the_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("WARRANT_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path


def test_default_data_dir_is_outside_the_repo(monkeypatch):
    monkeypatch.delenv("WARRANT_DATA_DIR", raising=False)
    assert not data_dir().resolve().is_relative_to(REPO_ROOT)
