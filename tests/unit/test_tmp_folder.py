"""``.tmp/`` holds worktrees and caches, and nothing in it is ever tracked."""

import subprocess

from tests.fixtures import ROOT


def test_no_path_under_tmp_is_tracked():
    """A forced add under ``.tmp/`` fails here."""
    tracked = subprocess.run(
        ["git", "ls-files", ".tmp"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert tracked.stdout == ""


def test_gitignore_ignores_tmp():
    """The folder is ignored, so worktrees under it never show as changes."""
    assert ".tmp/" in (ROOT / ".gitignore").read_text().splitlines()
