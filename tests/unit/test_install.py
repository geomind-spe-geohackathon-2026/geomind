"""No file installs a project by path or as editable, and the gemini pin agrees everywhere."""

import re
import tomllib

import pytest
from packaging.requirements import Requirement

from scripts import check_release
from tests.fixtures import ROOT

INSTALL_FILES = ("Makefile", ".github/workflows/python_test.yaml", ".github/workflows/release.yaml")
PIN = (ROOT / "requirements/gemini.txt").read_text().strip()
URL = PIN.split(" @ ")[1].split("#")[0]


@pytest.mark.parametrize("file", INSTALL_FILES)
def test_no_editable_or_path_install(file):
    """A sibling checkout decides nothing about what runs."""
    text = (ROOT / file).read_text()
    assert not re.search(r"pip install[^\n]* -e\b", text)
    assert "../gemini" not in text
    assert "gemini-checkout" not in text


def test_the_pin_has_a_hash_and_uv_names_the_same_wheel():
    """Both pip and uv install one wheel, and pip checks it."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    requirement = Requirement(PIN)
    assert requirement.url.split("#sha256=")[1]
    assert pyproject["tool"]["uv"]["sources"][requirement.name]["url"] == URL


def test_the_pin_is_in_the_supported_range():
    """The pinned release satisfies the range the package declares."""
    version = re.search(r"-(\d+\.\d+\.\d+)-py3", URL).group(1)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    declared = next(
        Requirement(item) for item in project["dependencies"] if item.startswith("gemini")
    )
    assert declared.specifier.contains(version)


def test_a_release_tag_must_name_the_version(monkeypatch):
    """A tag passes only when it is ``v`` and the version both files name."""
    monkeypatch.setattr(check_release, "versions", lambda: ("1.2.3", "1.2.3"))
    check_release.main("v1.2.3")
    with pytest.raises(SystemExit):
        check_release.main("v1.2.4")
    monkeypatch.setattr(check_release, "versions", lambda: ("1.2.3", "1.2.4"))
    with pytest.raises(SystemExit):
        check_release.main("v1.2.3")


def workflow_jobs():
    """Return the jobs of the test workflow."""
    import yaml

    return yaml.safe_load((ROOT / ".github/workflows/python_test.yaml").read_text())["jobs"]


def test_every_push_and_pull_request_runs_tests():
    """The fast tier runs on every event; the slow tier everywhere but a push to ``dev``."""
    jobs = workflow_jobs()
    assert "if" not in jobs["fast"]
    assert '-m "not slow and not docker"' in jobs["fast"]["steps"][-1]["run"]
    assert jobs["slow"]["if"] == "github.event_name != 'push' || github.ref != 'refs/heads/dev'"
    assert '-m "slow and not docker"' in jobs["slow"]["steps"][-1]["run"]


def test_the_slow_shards_cover_the_slow_tier():
    """One job per shard, each naming its own index of the same count."""
    slow = workflow_jobs()["slow"]
    shards = slow["strategy"]["matrix"]["shard"]
    assert shards == list(range(len(shards)))
    assert f"--shard ${{{{ matrix.shard }}}}/{len(shards)}" in slow["steps"][-1]["run"]


def test_every_job_has_a_timeout_and_runs_to_the_end():
    """A dying runner times out and hides no other job."""
    for job in workflow_jobs().values():
        assert job["timeout-minutes"] <= 30
        assert job["strategy"]["fail-fast"] is False
        assert "-n auto" in job["steps"][-1]["run"]


def test_the_ci_matrix_is_the_supported_pythons():
    """The matrix tests every Python the package declares, and no other."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    declared = sorted(
        item.rsplit(":: ", 1)[1]
        for item in project["classifiers"]
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", item)
    )
    for job in workflow_jobs().values():
        assert sorted(job["strategy"]["matrix"]["python"]) == declared
