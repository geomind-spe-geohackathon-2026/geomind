"""``.env`` files: read into the environment, with the real environment winning."""

import os

from geomind.utils.envfile import load_env_files, read_env_file


def test_a_file_gives_its_names_and_values(tmp_path):
    """Blank lines, comments and quotes are handled; ``export`` is allowed."""
    path = tmp_path / ".env"
    path.write_text("# a comment\n\nA=1\nexport B=\"two\"\nC='three'\nD=\n")
    assert read_env_file(path) == {"A": "1", "B": "two", "C": "three", "D": ""}


def test_the_real_environment_and_the_first_file_win(tmp_path, monkeypatch):
    """A set variable is kept, and an earlier file comes before a later one."""
    first, second = tmp_path / "first.env", tmp_path / "second.env"
    first.write_text("GEOMIND_TEST_X=first\nGEOMIND_TEST_Y=first\n")
    second.write_text("GEOMIND_TEST_X=second\nGEOMIND_TEST_Z=second\n")
    monkeypatch.setenv("GEOMIND_TEST_Y", "real")
    for name in ("GEOMIND_TEST_X", "GEOMIND_TEST_Z"):
        monkeypatch.delenv(name, raising=False)
    loaded = load_env_files([first, tmp_path / "missing.env", second])
    assert os.environ["GEOMIND_TEST_X"] == "first"
    assert os.environ["GEOMIND_TEST_Y"] == "real"
    assert os.environ["GEOMIND_TEST_Z"] == "second"
    assert loaded == ["GEOMIND_TEST_X", "GEOMIND_TEST_Z"]
    for name in loaded:
        monkeypatch.delenv(name)


def test_an_empty_value_does_not_set_a_variable(tmp_path, monkeypatch):
    """``OPENROUTER_API_KEY=`` in a template sets nothing."""
    path = tmp_path / ".env"
    path.write_text("GEOMIND_TEST_EMPTY=\n")
    monkeypatch.delenv("GEOMIND_TEST_EMPTY", raising=False)
    assert load_env_files([path]) == []
    assert "GEOMIND_TEST_EMPTY" not in os.environ
