"""Every code path in the contract map exists, so the map cannot go stale."""

import re

from tests.fixtures import ROOT

DOCUMENT = ROOT / ".claude/docs/contracts.md"


def test_every_mapped_path_exists():
    """Each ``swarmax/``, ``tests/`` and ``examples/`` path in the tables is a real file."""
    paths = re.findall(r"`((?:swarmax|tests|examples)/[\w/.]+\.py)`", DOCUMENT.read_text())
    assert len(paths) > 40
    assert [path for path in paths if not (ROOT / path).is_file()] == []
