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
from geomind.export import render_export
from geomind.stores.run import FileRunStore
from geomind.utils.json import read_json
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
    (tmp_path / "again").mkdir()
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
    text = check_export(run)
    monkeypatch.chdir(tmp_path / "again")
    assert cli.main(arguments) == 0
    again = next(path for path in Path(".runs").iterdir() if path.name != "chats")
    assert check_export(again) == text


def check_export(run):
    """Check that the export holds every part in order, and return it."""
    events = FileRunStore(run.parent).load_events(run.name)
    manifest = read_json(run / "run_manifest.json")
    text = render_export(events, manifest)
    parts = ["## Request", "Models by role:", "## LLM calls", "## Appendix: system prompts"]
    parts += ["## Tokens by agent", "## Tokens by step", "## Totals"]
    positions = [text.index(part) for part in parts]
    assert positions == sorted(positions)
    assert f"gemini version: {manifest['gemini']['version']}" in text
    assert text.count("### Call ") == text.count("Tokens: ") == 20
    for agent in ("designer", "verifier", "economist", "explainer"):
        assert text.count(f"### {agent}\n") == 1
    assert "- build_plant(" in text and "(0 cached)" in text
    return text
