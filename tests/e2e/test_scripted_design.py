"""A case through ``geomind run --loop design``, offline from a scripted recording.

NOTE: the recordings are hand-written decisions in the order the design loop asks its agents (read
the plant class and the case, build, size, simulate, check, optimise, simulate and check again,
record; check once; cost; explain); every reference and number in them comes from the real gemini
tools. They check the path from the command line to a verified, costed and explained design, not a
model.
"""

import re
from pathlib import Path

import pytest

from geomind import cli
from geomind.engine import replay
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
    original = FileRunStore(run.parent).load_events(run.name)
    text = check_export(run)
    stores = []

    class Capturing(replay._ReplayStore):
        """Keep the store a replay writes, to read the replayed tree."""

        def __init__(self, *arguments):
            """Register this store."""
            super().__init__(*arguments)
            stores.append(self)

    monkeypatch.setattr(replay, "_ReplayStore", Capturing)
    assert cli.main(["replay", str(run), "--project", str(PROJECTS[name])]) == 0
    assert capsys.readouterr().out.startswith("pass:")
    replayed = stores[0].load_events(run.name)
    assert calls_of(replayed) == calls_of(original)
    manifest = read_json(run / "run_manifest.json")
    assert normalised(render_export(replayed, manifest)) == normalised(text)


def calls_of(events):
    """Return the completions and tool results of a log with their run's agent, in log order."""
    runs = {e.run_id: e.agent for e in events if e.type == "run.started"}
    found = []
    for e in events:
        if e.type == "llm.completed":
            found.append((runs[e.run_id], e.index, e.completion.text, e.completion.tool_calls))
        if e.type == "tool.result":
            found.append((runs[e.run_id], e.index, e.tool, e.input, e.output))
    return found


def normalised(text):
    """Return an export without run ids, timestamps and durations."""
    text = re.sub(r"[0-9a-f]{32}", "<id>", text)
    text = re.sub(r"\d{4}-\d\d-\d\d[T ][\d:.+Z-]+", "<time>", text)
    return text


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
