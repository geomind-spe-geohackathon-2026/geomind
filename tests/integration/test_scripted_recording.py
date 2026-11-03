"""``evals/scripted.py`` writes the recording of ``alternatives/three_families`` again, offline."""

import json

import pytest

from evals import scripted
from evals.run import ROOT

RECORDING = ROOT / "recordings" / "alternatives" / "three_families.jsonl"


def moves(path):
    """Return the tools each completion of a recording calls, in order."""
    lines = path.read_text().splitlines()
    return [[call["name"] for call in json.loads(line)["tool_calls"]] for line in lines]


def test_the_plan_names_the_families_and_the_search():
    """The first moves read the plants and the case, then record the three families."""
    assert [call.name for call in scripted.plan(0).tool_calls] == ["list_plants", "set_case"]
    changes = scripted.plan(1).tool_calls[0].input["changes"]
    assert [item["id"] for item in changes[0]["value"]] == list(scripted.FAMILIES)
    assert changes[1]["value"] == scripted.SEARCH


@pytest.mark.slow
def test_the_script_writes_the_checked_in_recording_again(tmp_path):
    """Run offline, the task passes and the moves are those of the checked-in recording.

    NOTE: slow, because each family is sized, optimised and simulated for a whole year. The moves
    are compared, not the bytes: a reference names a stored result by its content.
    """
    written = tmp_path / "three_families.jsonl"
    outcome = scripted.record(written)
    assert outcome.problems == []
    assert moves(written) == moves(RECORDING)
