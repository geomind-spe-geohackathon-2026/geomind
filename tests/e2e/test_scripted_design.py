"""A case through ``geomind run --loop design``, offline from a scripted recording.

NOTE: the recordings are hand-written decisions in the order the design loop asks its agents (read
the plant class and the case, build, size, simulate, check, optimise, simulate and check again,
record; check once; cost; explain); every reference and number in them comes from the real gemini
tools. They check the path from the command line to a verified, costed and explained design, not a
model.
"""

from pathlib import Path

import pytest

from geomind import cli
from tests.fixtures import ROOT
from tests.fixtures.cases import example_folder

REQUEST = (
    "Design a deep-geothermal plant for the project's case, starting from the plant class "
    "HeatingHeatPumpCoolingPlant. Size the plant with the peak backup policy (a boiler that covers "
    "the whole heating peak), then optimise the levelised cost of thermal service (objective lcts) "
    "over the plant's own ranges with 30 evaluations and seed 0."
)
RECORDINGS = {
    "hackathon_2026": ROOT / "evals" / "runs" / "hackathon_scripted.jsonl",
    "shallow_district": ROOT
    / "tests"
    / "fixtures"
    / "recordings"
    / "shallow_district_scripted.jsonl",
}
PROJECTS = {
    "hackathon_2026": ROOT / "evals" / "projects" / "hackathon",
    "shallow_district": example_folder("shallow_district"),
}


@pytest.mark.parametrize("name", RECORDINGS)
def test_a_case_gives_a_verified_design_that_replays(name, monkeypatch, tmp_path, capsys):
    """The run ends verified, with capacities, energies, costs and open points, and replays."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt: "Use the project's case.")
    arguments = ["run", REQUEST, "--loop", "design", "--mode", "auto"]
    arguments += ["--project", str(PROJECTS[name]), "--recording", str(RECORDINGS[name])]
    assert cli.main(arguments) == 0
    output = capsys.readouterr().out
    run = next(path for path in Path(".runs").iterdir() if path.name != "chats")
    assert "design loop: stop: verified after round 1" in output
    for heading in ("## Capacities", "## Delivered", "## Costs", "## Open points", "LCTS"):
        assert heading in output
    assert cli.main(["replay", str(run)]) == 0
    assert capsys.readouterr().out.startswith("pass:")
